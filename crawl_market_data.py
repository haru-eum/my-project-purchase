"""
크롤링·스크래핑 보조 수집기 실행 후 SQLite 업서트.
앱(streamlit)은 자동 실행하지 않으며, 배치/수동으로 실행합니다.

  python crawl_market_data.py
"""

from __future__ import annotations

import io
import os
import sqlite3
import sys

# Windows 콘솔 한글 깨짐 방지
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd
from dotenv import load_dotenv

from db_io import ensure_upsert_schema, upsert_price_series
from scrapers.asian_metal import fetch_gallium_series, fetch_indium_series
from scrapers.lithium_investing import fetch_lithium_snapshot_usd
from scrapers.optional_sources import (
    fetch_pharmexcil_stub,
    fetch_pvc_monthly_stub,
    fetch_steel_stub,
)
from scrapers.silicon_usgs import fetch_silicon_daily_usd_from_usgs

DB_PATH = "scm_dashboard.db"


def _material_map(conn: sqlite3.Connection) -> dict[str, int]:
    frame = pd.read_sql("SELECT material_id, name_kr FROM RawMaterials", conn)
    return {str(row["name_kr"]): int(row["material_id"]) for _, row in frame.iterrows()}


def main() -> None:
    load_dotenv()
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError("scm_dashboard.db 없음. 먼저 python init_db.py 실행.")

    conn = sqlite3.connect(DB_PATH)
    ensure_upsert_schema(conn)
    name_to_id = _material_map(conn)
    total = 0
    lines: list[str] = []

    def run_one(label: str, kr_name: str, series: pd.Series, source: str) -> None:
        nonlocal total
        mid = name_to_id.get(kr_name)
        if mid is None:
            lines.append(f"[SKIP] {label}: RawMaterials에 '{kr_name}' 없음")
            return
        n = upsert_price_series(conn, mid, series, source)
        total += n
        lines.append(f"[{label}] rows={n} source={source}")

    # ① 리튬 Investing (스냅샷 1일)
    try:
        s_li, msg_li = fetch_lithium_snapshot_usd()
        lines.append(f"리튬: {msg_li}")
        if not s_li.empty:
            run_one("리튬", "리튬", s_li, "CRAWL_INVESTING")
    except Exception as exc:
        lines.append(f"[WARN] 리튬 크롤링 실패 (계속): {exc}")

    # ④ 실리콘 USGS
    try:
        s_si, msg_si = fetch_silicon_daily_usd_from_usgs()
        lines.append(f"실리콘: {msg_si}")
        if not s_si.empty:
            run_one("실리콘", "실리콘 웨이퍼", s_si, "CRAWL_USGS")
    except Exception as exc:
        lines.append(f"[WARN] 실리콘 크롤링 실패 (계속): {exc}")

    # ③ 갈륨·인듐
    try:
        s_ga, msg_ga = fetch_gallium_series()
        lines.append(f"갈륨: {msg_ga}")
        if not s_ga.empty:
            run_one("갈륨", "갈륨", s_ga, "CRAWL_ASIANMETAL")
    except Exception as exc:
        lines.append(f"[WARN] 갈륨 크롤링 실패 (계속): {exc}")

    try:
        s_in, msg_in = fetch_indium_series()
        lines.append(f"인듐: {msg_in}")
        if not s_in.empty:
            run_one("인듐", "인듐", s_in, "CRAWL_ASIANMETAL")
    except Exception as exc:
        lines.append(f"[WARN] 인듐 크롤링 실패 (계속): {exc}")

    # ② PVC (환경변수 URL 있을 때)
    try:
        s_pvc, msg_pvc = fetch_pvc_monthly_stub()
        lines.append(f"PVC: {msg_pvc}")
        if not s_pvc.empty:
            run_one("PVC", "포장재 PVC", s_pvc, "CRAWL_KPIA")
    except Exception as exc:
        lines.append(f"[WARN] PVC 크롤링 실패 (계속): {exc}")

    # 열연강판 스텁
    try:
        s_st, msg_st = fetch_steel_stub()
        lines.append(f"열연강판: {msg_st}")
        if not s_st.empty:
            run_one("열연강판", "열연강판", s_st, "CRAWL_STEEL")
    except Exception as exc:
        lines.append(f"[WARN] 열연강판 크롤링 실패 (계속): {exc}")

    # 제약 API PDF 스텁
    try:
        s_ph, msg_ph = fetch_pharmexcil_stub()
        lines.append(f"Pharmexcil: {msg_ph}")
        if not s_ph.empty:
            run_one("API", "API 인덱스", s_ph, "CRAWL_PHARMEXCIL")
    except Exception as exc:
        lines.append(f"[WARN] Pharmexcil 크롤링 실패 (계속): {exc}")

    conn.close()
    print("\n".join(lines))
    print(f"[OK] 총 업서트 행 수(근사): {total}")


if __name__ == "__main__":
    main()
