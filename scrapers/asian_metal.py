"""
Asian Metal 공개 테이블 파싱(사이트 구조 변경 시 실패 가능).
"""

from __future__ import annotations

import os
import random
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]


def fetch_asian_metal_table(url: str, sleep_sec: float = 2.0) -> tuple[pd.Series, str]:
    """
    테이블에서 날짜·가격(중간값)을 추출해 USD 시리즈로 반환.
    """
    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": random.choice(["en-US,en;q=0.9", "ko-KR,ko;q=0.9,en-US;q=0.8", "en-GB,en;q=0.9"]),
    }
    time.sleep(random.uniform(sleep_sec, sleep_sec + 3.0))
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        return pd.Series(dtype=float), f"요청 실패: {exc}"

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", class_=re.compile("price", re.I))
    if table is None:
        table = soup.find("table", {"class": "price"})
    if table is None:
        table = soup.find("table")

    if table is None:
        return pd.Series(dtype=float), "가격 테이블을 찾지 못했습니다(로그인·구조 변경 가능)."

    records: list[tuple[pd.Timestamp, float]] = []
    for row in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        # 날짜 형식 가정: YYYY-MM-DD 또는 유사
        date_str = cells[0]
        try:
            ts = pd.to_datetime(date_str, errors="coerce")
        except (ValueError, TypeError):
            ts = pd.NaT
        if pd.isna(ts):
            continue
        # low/high 중간 또는 두 번째 숫자 열
        nums = []
        for cell in cells[1:4]:
            try:
                nums.append(float(cell.replace(",", "")))
            except (ValueError, AttributeError):
                continue
        if not nums:
            continue
        mid = sum(nums) / len(nums)
        records.append((pd.Timestamp(ts.date()), mid))

    if not records:
        return pd.Series(dtype=float), "파싱된 행이 없습니다."

    series = pd.Series(
        [p for _, p in records],
        index=[d for d, _ in records],
    ).sort_index()
    return series, "OK"


def fetch_gallium_series() -> tuple[pd.Series, str]:
    url = os.getenv(
        "ASIANMETAL_GALLIUM_URL",
        "http://www.asianmetal.com/price/GalliumPrice.am",
    )
    return fetch_asian_metal_table(url)


def fetch_indium_series() -> tuple[pd.Series, str]:
    url = os.getenv(
        "ASIANMETAL_INDIUM_URL",
        "http://www.asianmetal.com/price/IndiumPrice.am",
    )
    return fetch_asian_metal_table(url)
