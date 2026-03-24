"""
웹·파일 기반 보조 수집기(스크래핑). 이용약관·로봇 배제 준수는 사용자 책임입니다.
"""

from .asian_metal import fetch_asian_metal_table, fetch_gallium_series, fetch_indium_series
from .lithium_investing import fetch_lithium_snapshot_usd
from .optional_sources import fetch_pharmexcil_stub, fetch_pvc_monthly_stub, fetch_steel_stub
from .silicon_usgs import fetch_silicon_daily_usd_from_usgs

__all__ = [
    "fetch_lithium_snapshot_usd",
    "fetch_silicon_daily_usd_from_usgs",
    "fetch_asian_metal_table",
    "fetch_gallium_series",
    "fetch_indium_series",
    "fetch_pvc_monthly_stub",
    "fetch_steel_stub",
    "fetch_pharmexcil_stub",
]
