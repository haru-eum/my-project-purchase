"""Pydantic response models."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DateBounds(BaseModel):
    min_date: date
    max_date: date


class Material(BaseModel):
    material_id: int
    name_kr: str
    name_en: str
    unit: str
    category: str
    base_price_usd: float


class PriceRow(BaseModel):
    date: date
    material_id: int
    name_kr: str
    name_en: str
    category: str
    unit: str
    price_usd: float
    exchange_rate: float
    price_krw: float
    price_source: str
    exchange_source: str


class MetricRow(BaseModel):
    name_kr: str
    category: str
    unit: str
    current_price_krw: float
    current_price_usd: float
    exchange_rate: float
    daily_delta_pct: float
    period_change_pct: float
    annualized_volatility_pct: float


class CoverageRow(BaseModel):
    name_kr: str
    expected_business_days: int
    observed_days: int
    coverage_pct: float
    status: str
    note: str


class ExchangeRow(BaseModel):
    date: date
    usd_krw: float


class DataSourceRow(BaseModel):
    name_kr: str
    source: str
    row_count: int
