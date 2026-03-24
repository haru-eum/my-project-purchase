"""가격 데이터 로딩 + 환율 보간 서비스."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd


def load_price_data(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    material_ids: list[int],
) -> pd.DataFrame:
    if not material_ids:
        return pd.DataFrame()

    placeholders = ",".join("?" * len(material_ids))
    query = f"""
    SELECT
        ph.price_date  AS date,
        rm.material_id AS material_id,
        rm.name_kr     AS name_kr,
        rm.name_en     AS name_en,
        rm.category    AS category,
        rm.unit        AS unit,
        ROUND(ph.price_usd, 3) AS price_usd,
        er.usd_krw     AS exchange_rate_raw,
        COALESCE(ph.source, 'DUMMY') AS price_source,
        COALESCE(er.source, 'DUMMY') AS exchange_source
    FROM v_price_daily_best ph
    JOIN RawMaterials rm ON rm.material_id = ph.material_id
    LEFT JOIN v_exchange_daily_best er ON er.rate_date = ph.price_date
    WHERE ph.price_date BETWEEN ? AND ?
      AND ph.material_id IN ({placeholders})
    ORDER BY ph.price_date, rm.material_id
    """
    params: list[object] = [start_date, end_date, *material_ids]
    frame = pd.read_sql(query, conn, params=params)

    if frame.empty:
        return frame

    frame["date"] = pd.to_datetime(frame["date"])

    # 환율 보간: 날짜 기준 환율 테이블 별도 구성 → ffill → 매핑
    exchange_raw = pd.read_sql(
        "SELECT rate_date AS date, usd_krw FROM v_exchange_daily_best "
        "WHERE rate_date BETWEEN ? AND ? ORDER BY rate_date",
        conn,
        params=[start_date, end_date],
    )
    exchange_raw["date"] = pd.to_datetime(exchange_raw["date"])

    all_dates = frame[["date"]].drop_duplicates().sort_values("date")
    exchange_map = all_dates.merge(exchange_raw, on="date", how="left").sort_values("date")
    exchange_map["usd_krw"] = exchange_map["usd_krw"].ffill().bfill()
    exchange_map["usd_krw"] = exchange_map["usd_krw"].round(2)
    date_to_rate = dict(zip(exchange_map["date"], exchange_map["usd_krw"]))

    frame["exchange_rate"] = frame["date"].map(date_to_rate)
    frame["price_krw"] = (frame["price_usd"] * frame["exchange_rate"]).round(0)
    frame.drop(columns=["exchange_rate_raw"], inplace=True)
    return frame


def compute_metrics(price_df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for material, group in price_df.groupby("name_kr"):
        sub = group.sort_values("date").copy()
        if sub.empty:
            continue

        latest = sub.iloc[-1]
        prev = sub.iloc[-2] if len(sub) > 1 else latest

        prev_krw = float(prev["price_krw"]) if pd.notna(prev["price_krw"]) else 0.0
        latest_krw = float(latest["price_krw"]) if pd.notna(latest["price_krw"]) else 0.0
        daily_delta = float((latest_krw - prev_krw) / prev_krw * 100) if prev_krw != 0 else 0.0

        start_px = float(sub.iloc[0]["price_krw"]) if pd.notna(sub.iloc[0]["price_krw"]) else 0.0
        end_px = latest_krw
        period_change = ((end_px - start_px) / start_px * 100) if start_px != 0 else 0.0

        vol = (
            float(sub["price_krw"].pct_change().dropna().std() * np.sqrt(252) * 100)
            if len(sub) > 2
            else 0.0
        )

        rows.append(
            {
                "name_kr": material,
                "category": latest["category"],
                "unit": latest["unit"],
                "current_price_krw": end_px,
                "current_price_usd": float(latest["price_usd"]),
                "exchange_rate": float(latest["exchange_rate"]),
                "daily_delta_pct": round(daily_delta, 2),
                "period_change_pct": round(period_change, 2),
                "annualized_volatility_pct": round(vol, 1),
            }
        )

    rows.sort(key=lambda r: r["period_change_pct"], reverse=True)
    return rows


def build_coverage_report(
    price_df: pd.DataFrame,
    query_start: str,
    query_end: str,
    selected_material_ids: list[int],
    id_to_kr: dict[int, str],
) -> list[dict]:
    from datetime import date, timedelta

    start_d = date.fromisoformat(query_start)
    end_d = date.fromisoformat(query_end)

    # 영업일 수 계산
    expected = 0
    d = start_d
    while d <= end_d:
        if d.weekday() < 5:
            expected += 1
        d += timedelta(days=1)

    rows: list[dict] = []
    for mid in sorted(selected_material_ids):
        kr = id_to_kr.get(mid, str(mid))
        if "material_id" in price_df.columns:
            sub = price_df[price_df["material_id"] == mid]
        else:
            sub = price_df[price_df["name_kr"] == kr]

        n_obs = int(sub["date"].dt.normalize().nunique()) if not sub.empty else 0
        ratio = (n_obs / expected * 100.0) if expected > 0 else 0.0

        if n_obs == 0:
            status, note = "없음", "해당 기간·환율 JOIN 조건으로 표시할 가격 행이 없습니다."
        elif ratio < 50.0:
            status, note = "부분", "스냅샷·월별·누락일 등으로 영업일 대비 관측이 적습니다."
        elif ratio < 90.0:
            status, note = "부분", "대부분 채워졌으나 일부 영업일 누락 가능."
        else:
            status, note = "양호", ""

        rows.append(
            {
                "name_kr": kr,
                "expected_business_days": expected,
                "observed_days": n_obs,
                "coverage_pct": round(ratio, 1),
                "status": status,
                "note": note,
            }
        )
    return rows
