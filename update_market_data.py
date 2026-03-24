"""
update_market_data.py
──────────────────────────────────────────────────
외부 API/보조데이터를 SQLite에 업서트하는 데이터 업그레이드 스크립트
──────────────────────────────────────────────────
"""

import io
import os
import sqlite3
import sys

# Windows 콘솔 한글 깨짐 방지
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime

import pandas as pd
import requests
import yfinance as yf
from fredapi import Fred
from dotenv import load_dotenv
from db_io import (
    ensure_upsert_schema as ensure_observation_schema,
    upsert_exchange_series,
    upsert_price_series,
)

DB_PATH = "scm_dashboard.db"


def ensure_upsert_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_price_unique_mat_date
            ON PriceHistory(material_id, price_date);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_rate_unique_date
            ON ExchangeRates(rate_date);
        """
    )
    conn.commit()


def material_id_map(conn: sqlite3.Connection) -> dict[str, int]:
    df = pd.read_sql("SELECT material_id, name_kr FROM RawMaterials", conn)
    return {str(row["name_kr"]): int(row["material_id"]) for _, row in df.iterrows()}


def fetch_fred_series(api_key: str, start: str) -> dict[str, pd.Series]:
    fred = Fred(api_key=api_key)
    series_map = {
        "구리": "PCOPPUSDM",
        "알루미늄": "PALUMUSDM",
        "니켈": "PNICKUSDM",
        "API 인덱스": "WPU0613",
    }
    result: dict[str, pd.Series] = {}
    for material_name, sid in series_map.items():
        monthly = fred.get_series(sid, observation_start=start)
        monthly.index = pd.to_datetime(monthly.index)
        daily = monthly.resample("D").interpolate(method="linear")
        result[material_name] = daily.rename(material_name).astype(float)
    return result


def _yf_close(ticker: str, start: str) -> pd.Series:
    """yfinance에서 Close 시리즈를 안전하게 추출 (MultiIndex 대응)."""
    frame = yf.download(ticker, start=start, progress=False, auto_adjust=False)
    if frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        close = frame["Close"].iloc[:, 0].dropna()
    else:
        close = frame["Close"].dropna()
    close.index = pd.to_datetime(close.index)
    return close.astype(float)


def fetch_yfinance_series(start: str) -> dict[str, pd.Series]:
    ticker_map = {
        "구리": "HG=F",
        "니켈": "NICK.L",  # NI=F 상장 폐지 → 런던 니켈 ETF
        "원유": "CL=F",
        "천연가스": "NG=F",
    }
    result: dict[str, pd.Series] = {}
    for material_name, ticker in ticker_map.items():
        close = _yf_close(ticker, start)
        if close.empty:
            continue
        close.name = material_name
        result[material_name] = close
    return result


def fetch_yfinance_exchange(start: str) -> pd.Series:
    """yfinance에서 USD/KRW 환율을 가져옴 (BOK API 키가 없을 때 폴백)."""
    close = _yf_close("KRW=X", start)
    if close.empty:
        return pd.Series(dtype=float)
    close.name = "usd_krw"
    return close


def fetch_eia_series(api_key: str) -> dict[str, pd.Series]:
    series_map = {
        "원유": "PET.RWTC.D",
        "천연가스": "NG.RNGWHHD.D",
    }
    result: dict[str, pd.Series] = {}

    for material_name, series_id in series_map.items():
        url = (
            f"https://api.eia.gov/v2/seriesid/{series_id}"
            f"?api_key={api_key}&data[]=value&frequency=daily"
            "&sort[0][column]=period&sort[0][direction]=desc&length=5000"
        )
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()["response"]["data"]
        frame = pd.DataFrame(data)
        frame["period"] = pd.to_datetime(frame["period"])
        frame["value"] = frame["value"].astype(float)
        series = frame.set_index("period")["value"].sort_index()
        result[material_name] = series.rename(material_name)
    return result


def fetch_bok_exchange(api_key: str, start: str, end: str) -> pd.Series:
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr"
        f"/1/10000/731Y001/DD/{start}/{end}/0000001"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("StatisticSearch", {}).get("row", [])
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.Series(dtype=float)
    frame["TIME"] = pd.to_datetime(frame["TIME"], format="%Y%m%d")
    frame["DATA_VALUE"] = frame["DATA_VALUE"].astype(float)
    return frame.set_index("TIME")["DATA_VALUE"].rename("usd_krw")


def upsert_price(conn: sqlite3.Connection, material_id: int, series: pd.Series, source: str) -> int:
    rows = [
        (material_id, str(idx.date()), float(value), source)
        for idx, value in series.dropna().items()
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO PriceHistory (material_id, price_date, price_usd, source)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(material_id, price_date) DO UPDATE SET
            price_usd = excluded.price_usd,
            source = excluded.source
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def upsert_exchange(conn: sqlite3.Connection, series: pd.Series, source: str) -> int:
    rows = [
        (str(idx.date()), float(value), source)
        for idx, value in series.dropna().items()
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO ExchangeRates (rate_date, usd_krw, source)
        VALUES (?, ?, ?)
        ON CONFLICT(rate_date) DO UPDATE SET
            usd_krw = excluded.usd_krw,
            source = excluded.source
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def main() -> None:
    load_dotenv()
    fred_key = os.getenv("FRED_API_KEY", "").strip()
    eia_key = os.getenv("EIA_API_KEY", "").strip()
    bok_key = os.getenv("BOK_API_KEY", "").strip() or os.getenv("EXCHANGE_RATE_API_KEY", "").strip()

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError("scm_dashboard.db 파일이 없습니다. 먼저 python init_db.py 실행이 필요합니다.")

    conn = sqlite3.connect(DB_PATH)
    ensure_observation_schema(conn)
    mat_map = material_id_map(conn)

    # 소스별 증분 업데이트: 각 소스의 마지막 날짜 이후부터만 수집 (데이터 구멍 방지)
    FALLBACK_START = "2024-01-01"
    cur = conn.cursor()

    def get_source_start(source: str, material_id: int | None = None) -> str:
        """소스별(+원자재별) DB 마지막 날짜를 조회하여 증분 시작일을 반환."""
        if material_id is not None:
            row = cur.execute(
                "SELECT MAX(price_date) FROM price_observations WHERE source_code = ? AND material_id = ?",
                (source, material_id),
            ).fetchone()
        else:
            row = cur.execute(
                "SELECT MAX(price_date) FROM price_observations WHERE source_code = ?", (source,)
            ).fetchone()
        return row[0] if row and row[0] else FALLBACK_START

    def get_exchange_start(source: str) -> str:
        """소스별로 환율 테이블의 마지막 날짜를 조회."""
        row = cur.execute(
            "SELECT MAX(rate_date) FROM exchange_rate_observations WHERE source_code = ?",
            (source,),
        ).fetchone()
        return row[0] if row and row[0] else FALLBACK_START

    today = datetime.now().strftime("%Y%m%d")
    inserted_count = 0

    if fred_key:
        try:
            fred_start = get_source_start("FRED")
            fred_data = fetch_fred_series(fred_key, fred_start)
            for material_name, series in fred_data.items():
                material_id = mat_map.get(material_name)
                if material_id is not None:
                    inserted_count += upsert_price_series(conn, material_id, series, "FRED")
        except Exception as exc:
            print(f"[WARN] FRED 수집 실패 (다음 소스로 계속): {exc}")

    # yfinance는 보조 데이터로만 사용 (원자재별 증분 시작일 적용)
    # 니켈(NI=F)은 상장폐지, NICK.L ETF는 LME 가격과 안정적 변환 불가하여 제외
    yf_ticker_map = {
        "구리": "HG=F",
        "원유": "CL=F",
        "천연가스": "NG=F",
    }
    # 단위 변환 계수: yfinance 원시값 × factor = USD/MT (또는 표준 단위)
    # 구리 HG=F: USD/pound → USD/metric ton (1 MT = 2204.62 lbs)
    YF_UNIT_FACTOR = {
        "구리": 2204.62,
    }
    for yf_name, yf_ticker in yf_ticker_map.items():
        try:
            yf_mid = mat_map.get(yf_name)
            yf_start = get_source_start("YFINANCE", yf_mid)
            close = _yf_close(yf_ticker, yf_start)
            if close.empty:
                continue
            factor = YF_UNIT_FACTOR.get(yf_name)
            if factor is not None:
                close = close * factor
            close.name = yf_name
            if yf_mid is not None:
                inserted_count += upsert_price_series(conn, yf_mid, close, "YFINANCE")
        except Exception as exc:
            print(f"[WARN] yfinance {yf_name}({yf_ticker}) 수집 실패 (계속): {exc}")

    if eia_key:
        try:
            eia_start = get_source_start("EIA")
            eia_data = fetch_eia_series(eia_key)
            for material_name, series in eia_data.items():
                material_id = mat_map.get(material_name)
                if material_id is not None:
                    inserted_count += upsert_price_series(conn, material_id, series, "EIA")
        except Exception as exc:
            print(f"[WARN] EIA 수집 실패 (다음 소스로 계속): {exc}")

    if bok_key:
        try:
            bok_start = get_exchange_start("BOK")
            exchange_series = fetch_bok_exchange(
                api_key=bok_key,
                start=bok_start.replace("-", ""),
                end=today,
            )
            inserted_count += upsert_exchange_series(conn, exchange_series, "BOK")
        except Exception as exc:
            print(f"[WARN] BOK 환율 수집 실패 (다음 소스로 계속): {exc}")

    # BOK 키가 없거나 실패한 경우 yfinance 환율로 폴백
    try:
        fx_start = get_exchange_start("YFINANCE")
        yf_fx = fetch_yfinance_exchange(fx_start)
        if not yf_fx.empty:
            inserted_count += upsert_exchange_series(conn, yf_fx, "YFINANCE")
    except Exception as exc:
        print(f"[WARN] yfinance 환율 수집 실패: {exc}")

    conn.close()
    print(f"[OK] 업서트 완료 행 수: {inserted_count}")


if __name__ == "__main__":
    main()
