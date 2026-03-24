"""SQLite connection helper."""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "scm_dashboard.db")

_conn: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError(
                f"DB 파일({DB_PATH})이 없습니다. `python init_db.py`를 먼저 실행하세요."
            )
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn
