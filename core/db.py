# core/db.py — Singleton DuckDB connection and shared warehouse helpers.
# One nexus_warehouse.duckdb file; all Bronze tables carry last_fetched TIMESTAMPTZ for TTL checks.
import threading
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent.parent / "nexus_warehouse.duckdb"
_lock = threading.Lock()


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    """Single shared DuckDB connection for the whole app lifecycle."""
    conn = duckdb.connect(str(DB_PATH), read_only=False)
    conn.execute("PRAGMA threads=4")
    return conn


def execute(sql: str, params=None):
    """Execute DML/DDL with optional params."""
    conn = get_connection()
    with _lock:
        conn.execute(sql, params) if params else conn.execute(sql)


def query_df(sql: str, params=None) -> pd.DataFrame:
    """Run SELECT and return a DataFrame."""
    conn = get_connection()
    with _lock:
        return conn.execute(sql, params).df() if params else conn.execute(sql).df()


def fetchone(sql: str, params=None):
    """Run SELECT and return first row tuple (or None)."""
    conn = get_connection()
    with _lock:
        return conn.execute(sql, params).fetchone() if params else conn.execute(sql).fetchone()


def table_exists(table_name: str) -> bool:
    """Return True if table exists in the main schema."""
    row = fetchone(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ?",
        [table_name],
    )
    return bool(row and row[0] > 0)


def is_stale(table_name: str, filter_col: str, filter_val: str, ttl_hours: float = 1.0) -> bool:
    """Return True when no fresh row exists for the key (missing, or older than ttl_hours)."""
    if not table_exists(table_name):
        return True
    try:
        conn = get_connection()
        with _lock:
            row = conn.execute(
                f"SELECT max(last_fetched) FROM {table_name} WHERE {filter_col} = ?",
                [filter_val],
            ).fetchone()
        if row is None or row[0] is None:
            return True
        last = row[0]
        if hasattr(last, "tzinfo") and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).total_seconds() / 3600 >= ttl_hours
    except Exception:
        return True


def last_fetched_str(table_name: str, filter_col: str | None = None, filter_val: str | None = None) -> str:
    """Return human-readable last-fetched timestamp string, or 'Never'."""
    if not table_exists(table_name):
        return "Never"
    try:
        if filter_col and filter_val:
            row = fetchone(f"SELECT max(last_fetched) FROM {table_name} WHERE {filter_col} = ?", [filter_val])
        else:
            row = fetchone(f"SELECT max(last_fetched) FROM {table_name}")
        if row and row[0] and hasattr(row[0], "strftime"):
            return row[0].strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        pass
    return "Never"


def warehouse_stats(since: datetime | None = None) -> pd.DataFrame:
    """
    Row counts and last-fetched per table.
    `since`: if provided, only counts rows with last_fetched >= since (session scoping).
    """
    conn = get_connection()
    with _lock:
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()

    since_clause = " WHERE last_fetched >= ?" if since else ""
    since_params: list = [since] if since else []

    rows = []
    for (tbl,) in tables:
        try:
            with _lock:
                cnt = conn.execute(
                    f"SELECT count(*) FROM {tbl}{since_clause}",
                    since_params or None,
                ).fetchone()[0]
            if cnt == 0:
                continue
            try:
                ts_row = fetchone(
                    f"SELECT max(last_fetched) FROM {tbl}{since_clause}",
                    since_params or None,
                )
                last = ts_row[0].strftime("%Y-%m-%d %H:%M UTC") if (ts_row and ts_row[0]) else "—"
            except Exception:
                last = "—"
            parts = tbl.split("_", 2)
            rows.append({
                "table": tbl,
                "domain": parts[1] if len(parts) > 1 else "—",
                "layer": parts[0] if parts else tbl,
                "rows": cnt,
                "last_fetched": last,
            })
        except Exception:
            pass
    return pd.DataFrame(rows)


def distinct_entities(since: datetime | None = None) -> dict:
    """
    Count distinct explored entities per domain key.
    `since`: if provided, restricts to entities fetched >= since.
    """
    checks = {
        "cities":       ("bronze_weather",        "city_key"),
        "coins":        ("bronze_crypto_markets",  "coin_id"),
        "currencies":   ("bronze_fx_rates",        "base_currency"),
        "countries":    ("bronze_worldbank",        "country_id"),
        "categories":   ("bronze_retail_products", "category"),
        "food_queries": ("bronze_food_search",     "query"),
        "topics":       ("bronze_news",            "topic"),
        "repos":        ("bronze_github_repo",     "repo_full_name"),
    }
    since_clause = " AND last_fetched >= ?" if since else ""
    since_params = [since] if since else []
    result = {}
    for label, (tbl, col) in checks.items():
        if table_exists(tbl):
            try:
                row = fetchone(
                    f"SELECT count(DISTINCT {col}) FROM {tbl} WHERE 1=1{since_clause}",
                    since_params or None,
                )
                result[label] = row[0] if row else 0
            except Exception:
                result[label] = 0
        else:
            result[label] = 0
    return result
