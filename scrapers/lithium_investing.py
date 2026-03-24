"""
Investing.com 리튬 페이지 스냅샷(최신 호가 1건). 일별 시계열은 제공하지 않음.
"""

from __future__ import annotations

import os
import re
from datetime import date

import pandas as pd

# Selenium은 선택 의존성: 미설치 시 명확히 안내


def _parse_usd_per_kg_from_text(raw: str) -> float | None:
    """표시 텍스트에서 숫자만 추출(통화 기호 제거)."""
    cleaned = raw.replace(",", "").strip()
    match = re.search(r"[-+]?\d*\.?\d+", cleaned)
    if not match:
        return None
    return float(match.group(0))


def fetch_lithium_snapshot_usd() -> tuple[pd.Series, str]:
    """
    Selenium으로 현재 페이지의 마지막 가격 1건을 USD로 저장 가능한 시리즈로 반환.
    반환: (일자 인덱스 1개짜리 Series, 메시지)
    """
    url = os.getenv(
        "INVESTING_LITHIUM_URL",
        "https://www.investing.com/commodities/lithium",
    )
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as exc:
        return (
            pd.Series(dtype=float),
            f"selenium/webdriver-manager 미설치: {exc}",
        )

    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        price_el = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-test="instrument-price-last"]')
            )
        )
        price_txt = price_el.text
        px = _parse_usd_per_kg_from_text(price_txt)
        if px is None:
            return pd.Series(dtype=float), "리튬 가격 파싱 실패(셀렉터·페이지 변경 가능)"
        today = date.today()
        series = pd.Series([px], index=[pd.Timestamp(today)])
        return series, "OK: 스냅샷 1건(당일 날짜로 저장, 과거 일자는 미제공)"
    finally:
        driver.quit()
