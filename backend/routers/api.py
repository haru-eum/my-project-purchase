"""모든 API 엔드포인트를 하나의 라우터에 통합."""

from __future__ import annotations

from fastapi import APIRouter, Query

import pandas as pd

from db import get_db
from models import (
    CoverageRow,
    DataSourceRow,
    DateBounds,
    ExchangeRow,
    Material,
    MetricRow,
    PriceRow,
)
from services.price_service import build_coverage_report, compute_metrics, load_price_data

router = APIRouter(prefix="/api")


@router.get("/date-bounds", response_model=DateBounds)
def get_date_bounds():
    conn = get_db()
    row = pd.read_sql(
        "SELECT MIN(rate_date) AS min_date, MAX(rate_date) AS max_date FROM v_exchange_daily_best",
        conn,
    ).iloc[0]
    if row["min_date"] is None:
        from datetime import date

        today = date.today()
        return DateBounds(min_date=today, max_date=today)
    return DateBounds(
        min_date=pd.to_datetime(row["min_date"]).date(),
        max_date=pd.to_datetime(row["max_date"]).date(),
    )


@router.get("/materials", response_model=list[Material])
def get_materials():
    conn = get_db()
    df = pd.read_sql(
        "SELECT material_id, name_kr, name_en, unit, category, base_price_usd "
        "FROM RawMaterials ORDER BY category, material_id",
        conn,
    )
    return df.to_dict(orient="records")


@router.get("/prices", response_model=list[PriceRow])
def get_prices(
    start_date: str = Query(...),
    end_date: str = Query(...),
    material_ids: str = Query(..., description="comma-separated material IDs"),
):
    ids = [int(x.strip()) for x in material_ids.split(",") if x.strip()]
    conn = get_db()
    df = load_price_data(conn, start_date, end_date, ids)
    if df.empty:
        return []
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df.to_dict(orient="records")


@router.get("/metrics", response_model=list[MetricRow])
def get_metrics(
    start_date: str = Query(...),
    end_date: str = Query(...),
    material_ids: str = Query(...),
):
    ids = [int(x.strip()) for x in material_ids.split(",") if x.strip()]
    conn = get_db()
    df = load_price_data(conn, start_date, end_date, ids)
    if df.empty:
        return []
    return compute_metrics(df)


@router.get("/coverage", response_model=list[CoverageRow])
def get_coverage(
    start_date: str = Query(...),
    end_date: str = Query(...),
    material_ids: str = Query(...),
):
    ids = [int(x.strip()) for x in material_ids.split(",") if x.strip()]
    conn = get_db()
    df = load_price_data(conn, start_date, end_date, ids)

    mat_df = pd.read_sql("SELECT material_id, name_kr FROM RawMaterials", conn)
    id_to_kr = dict(zip(mat_df["material_id"].tolist(), mat_df["name_kr"].tolist()))

    return build_coverage_report(df, start_date, end_date, ids, id_to_kr)


@router.get("/exchange", response_model=list[ExchangeRow])
def get_exchange(
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    conn = get_db()
    df = pd.read_sql(
        "SELECT rate_date AS date, ROUND(usd_krw, 2) AS usd_krw "
        "FROM v_exchange_daily_best WHERE rate_date BETWEEN ? AND ? ORDER BY rate_date",
        conn,
        params=[start_date, end_date],
    )
    return df.to_dict(orient="records")


@router.get("/data-sources", response_model=list[DataSourceRow])
def get_data_sources(
    start_date: str = Query(...),
    end_date: str = Query(...),
    material_ids: str = Query(...),
):
    ids = [int(x.strip()) for x in material_ids.split(",") if x.strip()]
    conn = get_db()
    df = load_price_data(conn, start_date, end_date, ids)
    if df.empty:
        return []
    src_df = (
        df.groupby(["name_kr", "price_source"], as_index=False)
        .size()
        .rename(columns={"price_source": "source", "size": "row_count"})
    )
    return src_df.to_dict(orient="records")
