# domains/macro_lens.py — Crypto (CoinGecko), FX rates (Frankfurter), World Bank indicators.
import json
from datetime import datetime, timezone

import pandas as pd

from core.db import execute, fetchone, is_stale, last_fetched_str, query_df, table_exists
from core.fetch import fetch_json

_CG_BASE = "https://api.coingecko.com/api/v3"
_FX_BASE = "https://api.frankfurter.app"
_WB_BASE = "https://api.worldbank.org/v2"

# Fallback set used when the user hasn't selected indicators or the API is unreachable
_WB_DEFAULT_INDICATORS = {
    "NY.GDP.MKTP.CD": "GDP (current US$)",
    "NY.GDP.PCAP.CD": "GDP per capita (US$)",
    "SP.POP.TOTL":    "Population, total",
    "FP.CPI.TOTL.ZG": "Inflation, consumer prices (annual %)",
    "SL.UEM.TOTL.ZS": "Unemployment, total (% of total labor force)",
}


def _init_tables():
    execute("""CREATE TABLE IF NOT EXISTS bronze_crypto_coins_list (
        cache_key VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_crypto_coins_list (
        coin_id VARCHAR, symbol VARCHAR, name VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_crypto_markets (
        coin_id VARCHAR, vs_currency VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_crypto_markets (
        coin_id VARCHAR, symbol VARCHAR, name VARCHAR, vs_currency VARCHAR,
        price DOUBLE, market_cap DOUBLE, volume_24h DOUBLE,
        change_24h DOUBLE, ath DOUBLE, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_crypto_markets (
        coin_id VARCHAR, symbol VARCHAR, name VARCHAR, vs_currency VARCHAR,
        price DOUBLE, market_cap DOUBLE, volume_24h DOUBLE,
        change_24h DOUBLE, price_local DOUBLE, local_currency VARCHAR,
        last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_fx_rates (
        base_currency VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_fx_rates (
        base_currency VARCHAR, target_currency VARCHAR, rate DOUBLE,
        rate_date VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_fx_rates (
        base_currency VARCHAR, target_currency VARCHAR, rate DOUBLE,
        rate_date VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_worldbank (
        country_id VARCHAR, indicator_id VARCHAR, raw_json VARCHAR,
        last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_worldbank (
        country_id VARCHAR, country_name VARCHAR, indicator_id VARCHAR,
        indicator_name VARCHAR, year INT, value DOUBLE, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_worldbank (
        country_id VARCHAR, country_name VARCHAR, indicator_id VARCHAR,
        indicator_name VARCHAR, latest_year INT, latest_value DOUBLE,
        last_fetched TIMESTAMPTZ)""")
    # Indicator catalogue (World Development Indicators)
    execute("""CREATE TABLE IF NOT EXISTS bronze_wb_indicator_list (
        cache_key VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_wb_indicator_list (
        indicator_id VARCHAR, indicator_name VARCHAR, source_note VARCHAR,
        last_fetched TIMESTAMPTZ)""")


def fetch_coin_list(force: bool = False) -> list[dict]:
    """Top-250 coins by market cap from CoinGecko, cached 1 h."""
    _init_tables()
    cache_key = "top250_usd"
    if not (force or is_stale("bronze_crypto_coins_list", "cache_key", cache_key)):
        return _read_coin_list()
    try:
        data = fetch_json(f"{_CG_BASE}/coins/markets", params={
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": 250, "page": 1, "sparkline": "false",
        })
        now = datetime.now(timezone.utc)
        execute("DELETE FROM bronze_crypto_coins_list WHERE cache_key=?", [cache_key])
        execute("INSERT INTO bronze_crypto_coins_list VALUES (?,?,?)", [cache_key, json.dumps(data), now])
        execute("DELETE FROM silver_crypto_coins_list")
        for coin in data:
            execute("INSERT INTO silver_crypto_coins_list VALUES (?,?,?,?)", [
                coin.get("id"), coin.get("symbol", "").upper(), coin.get("name"), now,
            ])
    except Exception as e:
        print(f"[macro_lens] coin list: {e}")
    return _read_coin_list()


def _read_coin_list() -> list[dict]:
    if not table_exists("silver_crypto_coins_list"):
        return []
    return query_df("SELECT coin_id, symbol, name FROM silver_crypto_coins_list ORDER BY name").to_dict("records")


def fetch_crypto_markets(coin_id: str, vs_currency: str = "usd", force: bool = False) -> None:
    _init_tables()
    if not (force or is_stale("bronze_crypto_markets", "coin_id", coin_id)):
        return
    try:
        data = fetch_json(f"{_CG_BASE}/coins/markets", params={
            "vs_currency": vs_currency, "ids": coin_id,
            "sparkline": "false", "price_change_percentage": "24h",
        })
        if not data:
            return
        coin = data[0]
        now  = datetime.now(timezone.utc)
        execute("DELETE FROM bronze_crypto_markets WHERE coin_id=? AND vs_currency=?", [coin_id, vs_currency])
        execute("INSERT INTO bronze_crypto_markets VALUES (?,?,?,?)", [coin_id, vs_currency, json.dumps(coin), now])
        execute("DELETE FROM silver_crypto_markets WHERE coin_id=? AND vs_currency=?", [coin_id, vs_currency])
        execute("INSERT INTO silver_crypto_markets VALUES (?,?,?,?,?,?,?,?,?,?)", [
            coin_id, coin.get("symbol", "").upper(), coin.get("name"),
            vs_currency, coin.get("current_price"), coin.get("market_cap"),
            coin.get("total_volume"), coin.get("price_change_percentage_24h"),
            coin.get("ath"), now,
        ])
        _build_gold_crypto(coin_id, vs_currency, now)
    except Exception as e:
        print(f"[macro_lens] crypto markets: {e}")


def _build_gold_crypto(coin_id, vs_currency, now):
    """Populate Gold crypto table (price_local = price in vs_currency by default)."""
    execute("DELETE FROM gold_crypto_markets WHERE coin_id=? AND vs_currency=?", [coin_id, vs_currency])
    try:
        execute("""
            INSERT INTO gold_crypto_markets
            SELECT s.coin_id, s.symbol, s.name, s.vs_currency,
                   s.price, s.market_cap, s.volume_24h, s.change_24h,
                   s.price AS price_local, s.vs_currency AS local_currency,
                   s.last_fetched
            FROM silver_crypto_markets s
            WHERE s.coin_id=? AND s.vs_currency=?
        """, [coin_id, vs_currency])
    except Exception as e:
        print(f"[macro_lens] gold crypto: {e}")


def get_gold_crypto(coin_id: str) -> pd.DataFrame:
    if not table_exists("gold_crypto_markets"):
        return pd.DataFrame()
    return query_df(
        "SELECT * FROM gold_crypto_markets WHERE coin_id=? ORDER BY last_fetched DESC LIMIT 1",
        [coin_id],
    )


def fetch_currency_list() -> dict[str, str]:
    """Return {code: name} from Frankfurter."""
    try:
        return fetch_json(f"{_FX_BASE}/currencies")
    except Exception:
        return {}


def fetch_fx_rates(base: str, force: bool = False) -> None:
    _init_tables()
    if not (force or is_stale("bronze_fx_rates", "base_currency", base)):
        return
    try:
        data = fetch_json(f"{_FX_BASE}/latest", params={"from": base})
        now  = datetime.now(timezone.utc)
        execute("DELETE FROM bronze_fx_rates WHERE base_currency=?", [base])
        execute("INSERT INTO bronze_fx_rates VALUES (?,?,?)", [base, json.dumps(data), now])
        execute("DELETE FROM silver_fx_rates WHERE base_currency=?", [base])
        rate_date = data.get("date", "")
        for target, rate in data.get("rates", {}).items():
            execute("INSERT INTO silver_fx_rates VALUES (?,?,?,?,?)", [base, target, rate, rate_date, now])
        execute("DELETE FROM gold_fx_rates WHERE base_currency=?", [base])
        execute("""
            INSERT INTO gold_fx_rates
            SELECT base_currency, target_currency, rate, rate_date, max(last_fetched)
            FROM silver_fx_rates WHERE base_currency=?
            GROUP BY base_currency, target_currency, rate, rate_date
        """, [base])
    except Exception as e:
        print(f"[macro_lens] fx rates: {e}")


def get_gold_fx(base: str) -> pd.DataFrame:
    if not table_exists("gold_fx_rates"):
        return pd.DataFrame()
    return query_df(
        "SELECT target_currency, rate, rate_date FROM gold_fx_rates "
        "WHERE base_currency=? ORDER BY rate DESC",
        [base],
    )


def fetch_country_list() -> list[dict]:
    """World Bank country list (filters out non-country aggregates)."""
    try:
        data = fetch_json(f"{_WB_BASE}/country", params={"format": "json", "per_page": 300})
        countries = []
        if isinstance(data, list) and len(data) > 1:
            for c in data[1] or []:
                if c.get("capitalCity"):  # skip regional/income aggregates
                    countries.append({
                        "id":     c.get("id"),
                        "name":   c.get("name"),
                        "region": c.get("region", {}).get("value", ""),
                        "income": c.get("incomeLevel", {}).get("value", ""),
                    })
        return sorted(countries, key=lambda x: x["name"])
    except Exception as e:
        print(f"[macro_lens] country list: {e}")
        return []


def fetch_indicator_list(force: bool = False) -> list[dict]:
    """Fetch all World Development Indicators (WDI) from World Bank source=2, cached 24 h."""
    _init_tables()
    cache_key = "wdi_indicators"
    if not (force or is_stale("bronze_wb_indicator_list", "cache_key", cache_key, ttl_hours=24.0)):
        return _read_indicator_list()
    indicators = []
    page = 1
    while True:
        try:
            data = fetch_json(f"{_WB_BASE}/source/2/indicator", params={
                "format": "json", "per_page": 1000, "page": page,
            })
            if not isinstance(data, list) or len(data) < 2:
                break
            meta, records = data[0], data[1] or []
            indicators.extend(records)
            if page >= meta.get("pages", 1):
                break
            page += 1
        except Exception as e:
            print(f"[macro_lens] indicator list page {page}: {e}")
            break
    if not indicators:
        # Fallback to defaults if API unreachable
        return [{"indicator_id": k, "indicator_name": v} for k, v in _WB_DEFAULT_INDICATORS.items()]
    now = datetime.now(timezone.utc)
    execute("DELETE FROM bronze_wb_indicator_list WHERE cache_key=?", [cache_key])
    execute("INSERT INTO bronze_wb_indicator_list VALUES (?,?,?)",
            [cache_key, json.dumps([{"id": i.get("id"), "name": i.get("name")} for i in indicators]), now])
    execute("DELETE FROM silver_wb_indicator_list")
    for ind in indicators:
        execute("INSERT INTO silver_wb_indicator_list VALUES (?,?,?,?)", [
            ind.get("id"), ind.get("name", ""),
            (ind.get("sourceNote") or "")[:300], now,
        ])
    return _read_indicator_list()


def _read_indicator_list() -> list[dict]:
    if not table_exists("silver_wb_indicator_list"):
        return []
    return query_df(
        "SELECT indicator_id, indicator_name FROM silver_wb_indicator_list ORDER BY indicator_name"
    ).to_dict("records")


def fetch_worldbank(country_id: str, indicators: dict | None = None, force: bool = False) -> None:
    """Fetch World Bank data for selected indicators. Falls back to defaults if indicators is None."""
    _init_tables()
    ind_map = indicators if indicators else _WB_DEFAULT_INDICATORS
    now = datetime.now(timezone.utc)
    for ind_id, ind_name in ind_map.items():
        cache_key = f"{country_id}_{ind_id}"
        if not (force or is_stale("bronze_worldbank", "country_id", cache_key)):
            continue
        try:
            data = fetch_json(f"{_WB_BASE}/country/{country_id}/indicator/{ind_id}", params={
                "format": "json", "per_page": 20, "mrv": 20,
            })
            if not isinstance(data, list) or len(data) < 2:
                continue
            records = data[1] or []
            execute("DELETE FROM bronze_worldbank WHERE country_id=? AND indicator_id=?", [cache_key, ind_id])
            execute("INSERT INTO bronze_worldbank VALUES (?,?,?,?)", [cache_key, ind_id, json.dumps(records), now])
            execute("DELETE FROM silver_worldbank WHERE country_id=? AND indicator_id=?", [country_id, ind_id])
            for rec in records:
                if rec.get("value") is None:
                    continue
                execute("INSERT INTO silver_worldbank VALUES (?,?,?,?,?,?,?)", [
                    country_id,
                    rec.get("country", {}).get("value", country_id),
                    ind_id, ind_name,
                    int(rec["date"]) if rec.get("date") else None,
                    float(rec["value"]), now,
                ])
            execute("DELETE FROM gold_worldbank WHERE country_id=? AND indicator_id=?", [country_id, ind_id])
            execute("""
                INSERT INTO gold_worldbank
                SELECT country_id, country_name, indicator_id, indicator_name,
                       year AS latest_year, value AS latest_value, max(last_fetched)
                FROM (
                    SELECT *, row_number() OVER (
                        PARTITION BY country_id, indicator_id ORDER BY year DESC
                    ) AS rn
                    FROM silver_worldbank
                    WHERE country_id=? AND indicator_id=? AND value IS NOT NULL
                ) t WHERE rn = 1
                GROUP BY country_id, country_name, indicator_id, indicator_name,
                         latest_year, latest_value
            """, [country_id, ind_id])
        except Exception as e:
            print(f"[macro_lens] worldbank {ind_id}: {e}")


def get_silver_worldbank(country_id: str, indicator_ids: list | None = None) -> pd.DataFrame:
    if not table_exists("silver_worldbank"):
        return pd.DataFrame()
    if indicator_ids:
        placeholders = ",".join(["?"] * len(indicator_ids))
        return query_df(
            f"SELECT indicator_name, year, value FROM silver_worldbank "
            f"WHERE country_id=? AND value IS NOT NULL "
            f"AND indicator_id IN ({placeholders}) ORDER BY indicator_id, year",
            [country_id, *indicator_ids],
        )
    return query_df(
        "SELECT indicator_name, year, value FROM silver_worldbank "
        "WHERE country_id=? AND value IS NOT NULL ORDER BY indicator_id, year",
        [country_id],
    )


def get_gold_worldbank(country_id: str, indicator_ids: list | None = None) -> pd.DataFrame:
    if not table_exists("gold_worldbank"):
        return pd.DataFrame()
    if indicator_ids:
        placeholders = ",".join(["?"] * len(indicator_ids))
        return query_df(
            f"SELECT indicator_name, latest_year, latest_value FROM gold_worldbank "
            f"WHERE country_id=? AND indicator_id IN ({placeholders}) ORDER BY indicator_name",
            [country_id, *indicator_ids],
        )
    return query_df(
        "SELECT indicator_name, latest_year, latest_value FROM gold_worldbank "
        "WHERE country_id=? ORDER BY indicator_name",
        [country_id],
    )


def last_fetched(coin_id: str, base: str, country_id: str) -> str:
    times = [
        last_fetched_str("bronze_crypto_markets", "coin_id", coin_id),
        last_fetched_str("bronze_fx_rates", "base_currency", base),
        last_fetched_str("bronze_worldbank", "country_id", country_id),
    ]
    valid = [t for t in times if t != "Never"]
    return valid[0] if valid else "Never"
