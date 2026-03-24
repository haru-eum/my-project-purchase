"""
init_db.py
──────────────────────────────────────────────────
산업군 리스크 대시보드 DB 초기화 스크립트
역할: SQLite 스키마 생성 + 더미 데이터 시드
──────────────────────────────────────────────────
"""

import os
import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
from db_io import ensure_upsert_schema, upsert_exchange_series, upsert_price_series

DB_PATH = "scm_dashboard.db"
# 시드 데이터: 시작은 과거·종료는 실행일 기준(최근 구간 분석에 맞춤)
START_DATE = date(2022, 1, 3)
END_DATE = date.today()
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# (id, name_en, name_kr, unit, base_price_usd, category)
MATERIALS = [
    (1, "Copper", "구리", "MT", 8500, "Automotive"),
    (2, "Aluminum", "알루미늄", "MT", 2400, "Automotive"),
    (3, "Nickel", "니켈", "MT", 17000, "Automotive"),
    (4, "Lithium Carbonate", "리튬", "MT", 15000, "Automotive"),
    (5, "Crude Oil", "원유", "BBL", 80, "Energy"),
    (6, "Natural Gas", "천연가스", "MMBTU", 3, "Energy"),
    (7, "Silicon", "실리콘 웨이퍼", "WAFER", 21, "Energy"),
    (8, "Chemical PPI Proxy", "API 인덱스", "INDEX", 100, "Pharma"),
    (9, "PVC Resin", "포장재 PVC", "MT", 1200, "Pharma"),
    (10, "Pharma Aluminum Foil", "포장재 알루미늄", "MT", 3200, "Pharma"),
    (11, "Steel HRC", "열연강판", "MT", 650, "Automotive"),
    (12, "Gallium", "갈륨", "KG", 350, "Energy"),
    (13, "Indium", "인듐", "KG", 280, "Energy"),
]

PRICE_PARAMS = {
    1: {"mu": 0.03, "sigma": 0.18},
    2: {"mu": 0.02, "sigma": 0.15},
    3: {"mu": -0.05, "sigma": 0.28},
    4: {"mu": -0.10, "sigma": 0.45},
    5: {"mu": 0.00, "sigma": 0.25},
    6: {"mu": -0.10, "sigma": 0.40},
    7: {"mu": 0.04, "sigma": 0.22},
    8: {"mu": 0.02, "sigma": 0.10},
    9: {"mu": 0.01, "sigma": 0.14},
    10: {"mu": 0.02, "sigma": 0.12},
    11: {"mu": 0.01, "sigma": 0.12},
    12: {"mu": 0.04, "sigma": 0.30},
    13: {"mu": 0.04, "sigma": 0.30},
}


def generate_price_series(base: float, n_days: int, mu: float, sigma: float) -> np.ndarray:
    dt = 1 / 252
    daily_returns = np.random.normal(
        loc=(mu - 0.5 * sigma**2) * dt,
        scale=sigma * np.sqrt(dt),
        size=n_days,
    )
    series = base * np.exp(np.cumsum(daily_returns))
    return np.round(series, 3)


def generate_exchange_rates(n_days: int) -> np.ndarray:
    base_rate = 1300.0
    dt = 1 / 252
    mu, sigma = 0.02, 0.08
    daily_returns = np.random.normal(
        loc=(mu - 0.5 * sigma**2) * dt,
        scale=sigma * np.sqrt(dt),
        size=n_days,
    )
    rates = base_rate * np.exp(np.cumsum(daily_returns))
    return np.round(rates, 2)


def get_date_range() -> list[date]:
    dates: list[date] = []
    day = START_DATE
    while day <= END_DATE:
        if day.weekday() < 5:
            dates.append(day)
        day += timedelta(days=1)
    return dates


def init_db() -> None:
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(f"[OK] 기존 DB 삭제: {DB_PATH}")
        except PermissionError:
            print(f"[WARN] DB 파일 잠금으로 삭제를 건너뜁니다: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(
        """
        DROP VIEW IF EXISTS v_price_daily_best;
        DROP VIEW IF EXISTS v_exchange_daily_best;
        DROP TABLE IF EXISTS exchange_rate_observations;
        DROP TABLE IF EXISTS price_observations;
        DROP TABLE IF EXISTS data_sources;
        DROP TABLE IF EXISTS PriceHistory;
        DROP TABLE IF EXISTS ExchangeRates;
        DROP TABLE IF EXISTS RawMaterials;
        """
    )

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS RawMaterials (
            material_id      INTEGER PRIMARY KEY,
            name_en          TEXT NOT NULL,
            name_kr          TEXT NOT NULL,
            unit             TEXT NOT NULL,
            category         TEXT NOT NULL,
            base_price_usd   REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS PriceHistory (
            price_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id      INTEGER NOT NULL REFERENCES RawMaterials(material_id),
            price_date       TEXT NOT NULL,
            price_usd        REAL NOT NULL,
            source           TEXT DEFAULT 'DUMMY'
        );

        CREATE TABLE IF NOT EXISTS ExchangeRates (
            rate_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            rate_date        TEXT NOT NULL UNIQUE,
            usd_krw          REAL NOT NULL,
            source           TEXT DEFAULT 'DUMMY'
        );

        CREATE INDEX IF NOT EXISTS idx_price_date_mat ON PriceHistory(price_date, material_id);
        CREATE INDEX IF NOT EXISTS idx_rate_date ON ExchangeRates(rate_date);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_price_unique_mat_date ON PriceHistory(material_id, price_date);
        CREATE INDEX IF NOT EXISTS idx_material_category ON RawMaterials(category);
        """
    )
    print("[OK] 기본 테이블 생성 완료")
    ensure_upsert_schema(conn)
    print("[OK] 관측 테이블/뷰 생성 완료")

    cur.executemany(
        """
        INSERT INTO RawMaterials (
            material_id, name_en, name_kr, unit, base_price_usd, category
        ) VALUES (?,?,?,?,?,?)
        """,
        MATERIALS,
    )

    dates = get_date_range()
    n_days = len(dates)
    date_strs = [str(d) for d in dates]
    print(f"[OK] 영업일 수: {n_days}일 ({START_DATE} ~ {END_DATE})")

    rates = generate_exchange_rates(n_days)
    rate_rows = [(date_strs[i], float(rates[i]), "DUMMY") for i in range(n_days)]
    cur.executemany(
        "INSERT INTO ExchangeRates (rate_date, usd_krw, source) VALUES (?,?,?)",
        rate_rows,
    )
    rate_series = pd.Series(
        data=[float(v) for v in rates],
        index=pd.to_datetime(date_strs),
        dtype=float,
    )
    upsert_exchange_series(conn, rate_series, "DUMMY")

    for material_id, _, _, _, base_price, _ in MATERIALS:
        params = PRICE_PARAMS[material_id]
        prices = generate_price_series(base_price, n_days, params["mu"], params["sigma"])
        price_series = pd.Series(
            data=[float(v) for v in prices],
            index=pd.to_datetime(date_strs),
            dtype=float,
        )
        upsert_price_series(conn, material_id, price_series, "DUMMY")

    conn.commit()
    conn.close()
    print(f"[OK] DB 초기화 완료: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    check_df = pd.read_sql(
        """
        SELECT
            rm.category AS 카테고리,
            rm.name_kr AS 원자재,
            COUNT(ph.price_id) AS 데이터수,
            ROUND(MIN(ph.price_usd), 2) AS 최저가_USD,
            ROUND(MAX(ph.price_usd), 2) AS 최고가_USD
        FROM PriceHistory ph
        JOIN RawMaterials rm ON rm.material_id = ph.material_id
        GROUP BY rm.material_id
        ORDER BY rm.material_id
        """,
        conn,
    )
    conn.close()
    print(check_df.to_string(index=False))


if __name__ == "__main__":
    init_db()