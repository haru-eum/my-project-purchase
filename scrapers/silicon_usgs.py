"""
USGS 연간 실리콘 가격 엑셀 → 일별 선형 보간(참고용).
"""

from __future__ import annotations

import os
import random
import re
from io import BytesIO

import pandas as pd
import requests

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def fetch_silicon_daily_usd_from_usgs() -> tuple[pd.Series, str]:
    url = os.getenv(
        "USGS_SILICON_XLSX_URL",
        "https://pubs.usgs.gov/periodicals/mcs2024/mcs2024-silicon.xlsx",
    )
    try:
        response = requests.get(url, headers={"User-Agent": random.choice(_USER_AGENTS)}, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        return pd.Series(dtype=float), f"USGS 다운로드 실패: {exc}"

    raw = pd.read_excel(BytesIO(response.content), sheet_name=0, header=None)
    year_col = None
    price_col = None
    for j in range(raw.shape[1]):
        col_vals = raw.iloc[:, j].astype(str).str.lower()
        if col_vals.str.contains("year", na=False).any():
            year_col = j
        if col_vals.str.contains("price", na=False).any() and col_vals.str.contains(
            "kg", na=False
        ).any():
            price_col = j
    if year_col is None or price_col is None:
        # 대체: 숫자 4자리 연도 열 + 실수 가격 열 탐색
        for j in range(raw.shape[1]):
            sample = raw.iloc[5:30, j].dropna()
            if sample.empty:
                continue
            if year_col is None and sample.astype(str).str.match(r"^\d{4}$").mean() > 0.5:
                year_col = j
            if price_col is None and pd.to_numeric(sample, errors="coerce").notna().mean() > 0.5:
                if year_col is not None and j != year_col:
                    price_col = j
    if year_col is None or price_col is None:
        return pd.Series(dtype=float), "USGS 엑셀에서 Year/Price 열을 자동 탐지하지 못했습니다."

    years = []
    prices = []
    for _, row in raw.iterrows():
        y = row.iloc[year_col]
        p = row.iloc[price_col]
        if pd.isna(y) or pd.isna(p):
            continue
        ys = str(y).strip()
        if not re.match(r"^\d{4}$", ys):
            continue
        try:
            price_val = float(p)
        except (TypeError, ValueError):
            continue
        years.append(pd.Timestamp(int(ys), 1, 1))
        prices.append(price_val)

    if len(years) < 2:
        return pd.Series(dtype=float), "USGS에서 유효한 연도·가격 행이 부족합니다."

    annual = pd.Series(prices, index=pd.DatetimeIndex(years)).sort_index()
    daily_index = pd.date_range(annual.index.min(), annual.index.max(), freq="D")
    daily = annual.reindex(daily_index).interpolate(method="linear")
    return daily.rename("silicon_usd_per_kg"), "OK: 연간→일별 보간(참고)"
