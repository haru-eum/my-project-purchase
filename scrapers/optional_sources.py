"""
KPIA PVC, 철강협회, Pharmexcil 등은 URL·로그인·PDF 구조가 수시로 바뀌므로
환경변수로 URL을 줄 때만 시도하고, 없으면 빈 시리즈를 반환합니다.
"""

from __future__ import annotations

import os
import random
from io import BytesIO

import pandas as pd
import requests

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]


def fetch_pvc_monthly_stub() -> tuple[pd.Series, str]:
    """한국석유화학협회 엑셀 URL이 있을 때만 월별 → 일 보간."""
    url = os.getenv("KPIA_PVC_EXCEL_URL", "").strip()
    if not url:
        return (
            pd.Series(dtype=float),
            "KPIA_PVC_EXCEL_URL 미설정: PVC 엑셀 URL을 .env에 넣은 뒤 컬럼 매핑을 scrapers/optional_sources.py에 맞춰 주세요.",
        )
    try:
        response = requests.get(
            url,
            headers={"User-Agent": random.choice(_USER_AGENTS)},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return pd.Series(dtype=float), f"PVC 엑셀 다운로드 실패: {exc}"

    try:
        df = pd.read_excel(BytesIO(response.content), sheet_name=0)
    except OSError:
        return pd.Series(dtype=float), "PVC 엑셀 파싱 실패(openpyxl 확인)."

    # 사용자 환경에 맞게 컬럼명 수정 필요
    date_col = os.getenv("KPIA_PVC_DATE_COL", "날짜")
    price_col = os.getenv("KPIA_PVC_PRICE_COL", "PVC")
    if date_col not in df.columns or price_col not in df.columns:
        return (
            pd.Series(dtype=float),
            f"엑셀에 컬럼 '{date_col}', '{price_col}'이 없습니다. 환경변수로 지정하세요.",
        )
    pair = df[[date_col, price_col]].dropna()
    pair[date_col] = pd.to_datetime(pair[date_col])
    s = pair.set_index(date_col)[price_col].astype(float).sort_index()
    daily = s.resample("D").interpolate(method="linear")
    return daily, "OK: KPIA PVC(월→일 보간)"


def fetch_steel_stub() -> tuple[pd.Series, str]:
    url = os.getenv("STEEL_HRC_PAGE_URL", "").strip()
    if not url:
        return (
            pd.Series(dtype=float),
            "STEEL_HRC_PAGE_URL 미설정: 철강협회 페이지·로그인 방식 확인 후 구현 확장.",
        )
    return pd.Series(dtype=float), "열연강판: URL은 설정됐으나 파서 미구현(사이트 전용 작업 필요)."


def fetch_pharmexcil_stub() -> tuple[pd.Series, str]:
    pdf_url = os.getenv("PHARMEXCIL_PDF_URL", "").strip()
    if not pdf_url:
        return (
            pd.Series(dtype=float),
            "PHARMEXCIL_PDF_URL 미설정: PDF URL과 camelot 의존성 확인.",
        )
    try:
        import camelot  # noqa: F401
    except ImportError:
        return pd.Series(dtype=float), "camelot-py 미설치: pip install camelot-py[cv]"
    return pd.Series(dtype=float), "Pharmexcil: PDF 파서는 사이트별로 별도 구현이 필요합니다."
