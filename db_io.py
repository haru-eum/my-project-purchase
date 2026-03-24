"""
SQLite 데이터 계층 유틸.
기존(PriceHistory/ExchangeRates) + 신규 관측 테이블을 함께 유지한다.
"""

from __future__ import annotations

import sqlite3

import pandas as pd


def ensure_upsert_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS data_sources (
            source_code   TEXT PRIMARY KEY,
            source_type   TEXT NOT NULL,
            trust_level   INTEGER NOT NULL DEFAULT 50,
            priority      INTEGER NOT NULL DEFAULT 50,
            is_synthetic  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS price_observations (
            observation_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id        INTEGER NOT NULL,
            price_date         TEXT NOT NULL,
            price_usd          REAL NOT NULL,
            source_code        TEXT NOT NULL,
            collected_at_utc   TEXT NOT NULL DEFAULT (datetime('now')),
            raw_value          TEXT,
            normalized_value   REAL,
            unit               TEXT,
            is_synthetic       INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(material_id) REFERENCES RawMaterials(material_id),
            FOREIGN KEY(source_code) REFERENCES data_sources(source_code)
        );

        CREATE TABLE IF NOT EXISTS exchange_rate_observations (
            observation_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            rate_date          TEXT NOT NULL,
            usd_krw            REAL NOT NULL,
            source_code        TEXT NOT NULL,
            collected_at_utc   TEXT NOT NULL DEFAULT (datetime('now')),
            raw_value          TEXT,
            normalized_value   REAL,
            is_synthetic       INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(source_code) REFERENCES data_sources(source_code)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_price_unique_mat_date
            ON PriceHistory(material_id, price_date);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_rate_unique_date
            ON ExchangeRates(rate_date);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_price_obs_unique_key
            ON price_observations(material_id, price_date, source_code);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fx_obs_unique_key
            ON exchange_rate_observations(rate_date, source_code);
        CREATE INDEX IF NOT EXISTS idx_price_obs_lookup
            ON price_observations(price_date, material_id);
        CREATE INDEX IF NOT EXISTS idx_fx_obs_lookup
            ON exchange_rate_observations(rate_date);
        """
    )
    cur.executescript(
        """
        CREATE VIEW IF NOT EXISTS v_price_daily_best AS
        SELECT
            po.material_id,
            po.price_date,
            po.price_usd,
            po.source_code AS source
        FROM price_observations po
        JOIN data_sources ds ON ds.source_code = po.source_code
        WHERE po.observation_id IN (
            SELECT po2.observation_id
            FROM price_observations po2
            JOIN data_sources ds2 ON ds2.source_code = po2.source_code
            WHERE po2.material_id = po.material_id
              AND po2.price_date = po.price_date
            ORDER BY ds2.priority DESC, ds2.trust_level DESC, po2.collected_at_utc DESC
            LIMIT 1
        );

        CREATE VIEW IF NOT EXISTS v_exchange_daily_best AS
        SELECT
            eo.rate_date,
            eo.usd_krw,
            eo.source_code AS source
        FROM exchange_rate_observations eo
        JOIN data_sources ds ON ds.source_code = eo.source_code
        WHERE eo.observation_id IN (
            SELECT eo2.observation_id
            FROM exchange_rate_observations eo2
            JOIN data_sources ds2 ON ds2.source_code = eo2.source_code
            WHERE eo2.rate_date = eo.rate_date
            ORDER BY ds2.priority DESC, ds2.trust_level DESC, eo2.collected_at_utc DESC
            LIMIT 1
        );
        """
    )
    cur.executemany(
        """
        INSERT INTO data_sources (source_code, source_type, trust_level, priority, is_synthetic)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_code) DO UPDATE SET
            source_type = excluded.source_type,
            trust_level = excluded.trust_level,
            priority = excluded.priority,
            is_synthetic = excluded.is_synthetic
        """,
        [
            ("DUMMY", "SEED", 5, 1, 1),
            ("FRED", "API", 90, 95, 0),
            ("EIA", "API", 90, 94, 0),
            ("BOK", "API", 95, 98, 0),
            ("YFINANCE", "API", 60, 60, 0),
            ("CRAWL_INVESTING", "CRAWL", 50, 55, 0),
            ("CRAWL_USGS", "CRAWL", 70, 72, 0),
            ("CRAWL_ASIANMETAL", "CRAWL", 65, 68, 0),
            ("CRAWL_KPIA", "CRAWL", 70, 74, 0),
            ("CRAWL_STEEL", "CRAWL", 60, 62, 0),
            ("CRAWL_PHARMEXCIL", "CRAWL", 65, 69, 0),
        ],
    )
    cur.executescript(
        """
        INSERT INTO price_observations (material_id, price_date, price_usd, source_code, raw_value, normalized_value, is_synthetic)
        SELECT ph.material_id, ph.price_date, ph.price_usd, COALESCE(ph.source, 'DUMMY'),
               CAST(ph.price_usd AS TEXT), ph.price_usd,
               CASE WHEN COALESCE(ph.source, 'DUMMY') = 'DUMMY' THEN 1 ELSE 0 END
        FROM PriceHistory ph
        WHERE NOT EXISTS (
            SELECT 1
            FROM price_observations po
            WHERE po.material_id = ph.material_id
              AND po.price_date = ph.price_date
              AND po.source_code = COALESCE(ph.source, 'DUMMY')
        );

        INSERT INTO exchange_rate_observations (rate_date, usd_krw, source_code, raw_value, normalized_value, is_synthetic)
        SELECT er.rate_date, er.usd_krw, COALESCE(er.source, 'DUMMY'),
               CAST(er.usd_krw AS TEXT), er.usd_krw,
               CASE WHEN COALESCE(er.source, 'DUMMY') = 'DUMMY' THEN 1 ELSE 0 END
        FROM ExchangeRates er
        WHERE NOT EXISTS (
            SELECT 1
            FROM exchange_rate_observations eo
            WHERE eo.rate_date = er.rate_date
              AND eo.source_code = COALESCE(er.source, 'DUMMY')
        );
        """
    )
    conn.commit()


def _register_source(conn: sqlite3.Connection, source: str) -> None:
    source_code = (source or "DUMMY").strip() or "DUMMY"
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO data_sources (source_code, source_type, trust_level, priority, is_synthetic)
        VALUES (?, 'CUSTOM', 50, 50, ?)
        ON CONFLICT(source_code) DO NOTHING
        """,
        (source_code, 1 if source_code == "DUMMY" else 0),
    )


def upsert_price_series(
    conn: sqlite3.Connection,
    material_id: int,
    series: pd.Series,
    source: str,
) -> int:
    source_code = (source or "DUMMY").strip() or "DUMMY"
    _register_source(conn, source_code)
    rows = [
        (material_id, str(idx.date()), float(value), source_code)
        for idx, value in series.dropna().items()
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO PriceHistory (material_id, price_date, price_usd, source)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(material_id, price_date) DO UPDATE SET
            price_usd = excluded.price_usd,
            source = excluded.source
        """,
        rows,
    )
    obs_rows = [
        (material_id, price_date, price_usd, source_code, str(price_usd), price_usd, 1 if source_code == "DUMMY" else 0)
        for material_id, price_date, price_usd, source_code in rows
    ]
    conn.executemany(
        """
        INSERT INTO price_observations (
            material_id, price_date, price_usd, source_code, raw_value, normalized_value, is_synthetic
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(material_id, price_date, source_code) DO UPDATE SET
            price_usd = excluded.price_usd,
            raw_value = excluded.raw_value,
            normalized_value = excluded.normalized_value,
            collected_at_utc = datetime('now'),
            is_synthetic = excluded.is_synthetic
        """,
        obs_rows,
    )
    conn.commit()
    return len(rows)


def upsert_exchange_series(
    conn: sqlite3.Connection,
    series: pd.Series,
    source: str,
) -> int:
    source_code = (source or "DUMMY").strip() or "DUMMY"
    _register_source(conn, source_code)
    rows = [
        (str(idx.date()), float(value), source_code)
        for idx, value in series.dropna().items()
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO ExchangeRates (rate_date, usd_krw, source)
        VALUES (?, ?, ?)
        ON CONFLICT(rate_date) DO UPDATE SET
            usd_krw = excluded.usd_krw,
            source = excluded.source
        """,
        rows,
    )
    obs_rows = [
        (rate_date, usd_krw, source_code, str(usd_krw), usd_krw, 1 if source_code == "DUMMY" else 0)
        for rate_date, usd_krw, source_code in rows
    ]
    conn.executemany(
        """
        INSERT INTO exchange_rate_observations (
            rate_date, usd_krw, source_code, raw_value, normalized_value, is_synthetic
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(rate_date, source_code) DO UPDATE SET
            usd_krw = excluded.usd_krw,
            raw_value = excluded.raw_value,
            normalized_value = excluded.normalized_value,
            collected_at_utc = datetime('now'),
            is_synthetic = excluded.is_synthetic
        """,
        obs_rows,
    )
    conn.commit()
    return len(rows)
