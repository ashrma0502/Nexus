# domains/retail_iq.py — FakeStore products + OpenFoodFacts nutrition.
import json
from datetime import datetime, timezone
import pandas as pd

from core.db import execute, is_stale, last_fetched_str, query_df, table_exists
from core.fetch import fetch_json

_FAKESTORE_BASE = "https://fakestoreapi.com"
_OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"


def _init_tables():
    execute("""CREATE TABLE IF NOT EXISTS bronze_retail_products (
        category VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_retail_products (
        category VARCHAR, product_id VARCHAR, title VARCHAR,
        price DOUBLE, rating DOUBLE, rating_count INT,
        description VARCHAR, image_url VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_retail_products (
        category VARCHAR, product_count BIGINT, avg_price DOUBLE,
        avg_rating DOUBLE, min_price DOUBLE, max_price DOUBLE,
        last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_food_search (
        query VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_food_search (
        query VARCHAR, product_name VARCHAR, brands VARCHAR,
        energy_kcal DOUBLE, proteins DOUBLE, fat DOUBLE,
        carbohydrates DOUBLE, fiber DOUBLE, salt DOUBLE,
        nutriscore VARCHAR, nova_group INT, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_food_search (
        query VARCHAR, product_count BIGINT, avg_energy_kcal DOUBLE,
        avg_proteins DOUBLE, avg_fat DOUBLE, avg_carbs DOUBLE,
        nutriscore_a_pct DOUBLE, last_fetched TIMESTAMPTZ)""")


def fetch_categories() -> list[str]:
    """Live category list from FakeStore API."""
    try:
        return fetch_json(f"{_FAKESTORE_BASE}/products/categories")
    except Exception as e:
        print(f"[retail_iq] categories error: {e}")
        return []


def fetch_products(category: str, force: bool = False) -> None:
    _init_tables()
    if not (force or is_stale("bronze_retail_products", "category", category)):
        return
    try:
        data = fetch_json(f"{_FAKESTORE_BASE}/products/category/{category}")
        now  = datetime.now(timezone.utc)

        execute("DELETE FROM bronze_retail_products WHERE category=?", [category])
        execute("INSERT INTO bronze_retail_products VALUES (?,?,?)",
                [category, json.dumps(data), now])

        execute("DELETE FROM silver_retail_products WHERE category=?", [category])
        for p in data:
            rat = p.get("rating") or {}
            execute("INSERT INTO silver_retail_products VALUES (?,?,?,?,?,?,?,?,?)", [
                category,
                str(p.get("id")),
                p.get("title","")[:200],
                p.get("price"),
                rat.get("rate"),
                rat.get("count"),
                (p.get("description","") or "")[:500],
                p.get("image",""),
                now,
            ])

        execute("DELETE FROM gold_retail_products WHERE category=?", [category])
        execute("""
            INSERT INTO gold_retail_products
            SELECT category, count(*), avg(price), avg(rating),
                   min(price), max(price), max(last_fetched)
            FROM silver_retail_products WHERE category=?
            GROUP BY category
        """, [category])
    except Exception as e:
        print(f"[retail_iq] products error: {e}")


def fetch_food_search(query: str, force: bool = False) -> None:
    _init_tables()
    q_key = query.strip().lower()
    if not (force or is_stale("bronze_food_search", "query", q_key)):
        return
    try:
        data = fetch_json(_OFF_SEARCH_URL, params={
            "search_terms": query.strip(),
            "json": 1,
            "page_size": 30,
            "fields": ",".join([
                "product_name","brands","nutriments",
                "nutriscore_grade","nova_group",
            ]),
        })
        now = datetime.now(timezone.utc)

        execute("DELETE FROM bronze_food_search WHERE query=?", [q_key])
        execute("INSERT INTO bronze_food_search VALUES (?,?,?)",
                [q_key, json.dumps(data.get("products", [])[:30]), now])

        execute("DELETE FROM silver_food_search WHERE query=?", [q_key])
        for prod in (data.get("products") or [])[:30]:
            n = prod.get("nutriments") or {}
            execute("INSERT INTO silver_food_search VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
                q_key,
                (prod.get("product_name") or "")[:200],
                (prod.get("brands") or "")[:200],
                _num(n.get("energy-kcal_100g") or n.get("energy_100g")),
                _num(n.get("proteins_100g")),
                _num(n.get("fat_100g")),
                _num(n.get("carbohydrates_100g")),
                _num(n.get("fiber_100g")),
                _num(n.get("salt_100g")),
                (prod.get("nutriscore_grade") or "").upper() or None,
                _int(prod.get("nova_group")),
                now,
            ])

        execute("DELETE FROM gold_food_search WHERE query=?", [q_key])
        execute("""
            INSERT INTO gold_food_search
            SELECT query, count(*),
                   avg(energy_kcal), avg(proteins), avg(fat), avg(carbohydrates),
                   round(100.0 * sum(CASE WHEN nutriscore='A' THEN 1 ELSE 0 END)
                         / NULLIF(count(*),0), 1),
                   max(last_fetched)
            FROM silver_food_search WHERE query=?
            GROUP BY query
        """, [q_key])
    except Exception as e:
        print(f"[retail_iq] food search error: {e}")


def _num(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _int(v):
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def get_silver_products(category: str) -> pd.DataFrame:
    if not table_exists("silver_retail_products"):
        return pd.DataFrame()
    return query_df(
        "SELECT title, price, rating, rating_count, image_url, description "
        "FROM silver_retail_products WHERE category=? ORDER BY rating DESC",
        [category],
    )


def get_gold_products(category: str) -> pd.DataFrame:
    if not table_exists("gold_retail_products"):
        return pd.DataFrame()
    return query_df(
        "SELECT * FROM gold_retail_products WHERE category=?", [category])


def get_silver_food(query: str) -> pd.DataFrame:
    if not table_exists("silver_food_search"):
        return pd.DataFrame()
    q_key = query.strip().lower()
    return query_df(
        "SELECT product_name, brands, energy_kcal, proteins, fat, "
        "carbohydrates, fiber, salt, nutriscore, nova_group "
        "FROM silver_food_search WHERE query=? "
        "ORDER BY energy_kcal DESC NULLS LAST",
        [q_key],
    )


def get_gold_food(query: str) -> pd.DataFrame:
    if not table_exists("gold_food_search"):
        return pd.DataFrame()
    q_key = query.strip().lower()
    return query_df(
        "SELECT * FROM gold_food_search WHERE query=?", [q_key])


def last_fetched(category: str, food_query: str = "") -> str:
    t1 = last_fetched_str("bronze_retail_products", "category", category)
    t2 = last_fetched_str("bronze_food_search", "query", food_query.strip().lower()) if food_query else "Never"
    for t in [t1, t2]:
        if t != "Never":
            return t
    return "Never"
