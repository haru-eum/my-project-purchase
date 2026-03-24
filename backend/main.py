"""FastAPI backend entry point."""

import sys
import os

# 프로젝트 루트의 db_io.py 등을 import 할 수 있도록 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import get_db
from db.migrations import ensure_material_category_integrity
from routers.api import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB 초기화 시 ensure_upsert_schema 호출
    conn = get_db()
    try:
        from db_io import ensure_upsert_schema
        ensure_upsert_schema(conn)
    except ImportError:
        pass
    ensure_material_category_integrity(conn)
    yield


app = FastAPI(title="SCM 원자재 리스크 대시보드 API", lifespan=lifespan)

_cors_raw = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
_cors_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip()
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
if _cors_raw.strip() == "*":
    _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex or None,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    _reload = os.getenv("UVICORN_RELOAD", "1").lower() in ("1", "true", "yes")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=_reload)
