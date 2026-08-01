# domains/narrative_iq.py — News (Guardian), Books (OpenLibrary), TV Shows (TVMaze).
import json
import os
import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from core.db import execute, is_stale, last_fetched_str, query_df, table_exists
from core.fetch import fetch_json

_GUARDIAN_URL  = "https://content.guardianapis.com/search"
_OL_SEARCH_URL = "https://openlibrary.org/search.json"
_TVMAZE_URL    = "https://api.tvmaze.com/search/shows"


def _guardian_key() -> str:
    """Guardian API key — 'test' works for demo use."""
    try:
        return st.secrets.get("GUARDIAN_API_KEY", "test")
    except Exception:
        return os.environ.get("GUARDIAN_API_KEY", "test")


def _init_tables():
    execute("""CREATE TABLE IF NOT EXISTS bronze_news (
        topic VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_news (
        topic VARCHAR, title VARCHAR, section VARCHAR, web_url VARCHAR,
        trail_text VARCHAR, pub_date VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_news (
        topic VARCHAR, article_count BIGINT,
        top_section VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_books (
        topic VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_books (
        topic VARCHAR, title VARCHAR, author VARCHAR,
        first_publish_year INT, edition_count INT, cover_edition_key VARCHAR,
        last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_books (
        topic VARCHAR, book_count BIGINT, avg_publish_year DOUBLE,
        max_editions INT, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_shows (
        topic VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_shows (
        topic VARCHAR, show_id INT, show_name VARCHAR, show_type VARCHAR,
        language VARCHAR, genres VARCHAR, status VARCHAR, rating DOUBLE,
        premiered VARCHAR, summary VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_shows (
        topic VARCHAR, show_count BIGINT, avg_rating DOUBLE,
        top_genre VARCHAR, last_fetched TIMESTAMPTZ)""")


def fetch_news(topic: str, force: bool = False) -> None:
    _init_tables()
    t_key = topic.strip().lower()
    if not (force or is_stale("bronze_news", "topic", t_key)):
        return
    try:
        data = fetch_json(_GUARDIAN_URL, params={
            "q": topic.strip(), "api-key": _guardian_key(),
            "show-fields": "trailText,thumbnail",
            "page-size": 30, "order-by": "newest",
        })
        results = data.get("response", {}).get("results", [])
        now = datetime.now(timezone.utc)
        execute("DELETE FROM bronze_news WHERE topic=?", [t_key])
        execute("INSERT INTO bronze_news VALUES (?,?,?)", [t_key, json.dumps(results), now])
        execute("DELETE FROM silver_news WHERE topic=?", [t_key])
        for art in results:
            fields = art.get("fields") or {}
            execute("INSERT INTO silver_news VALUES (?,?,?,?,?,?,?)", [
                t_key, art.get("webTitle", "")[:300],
                art.get("sectionName", ""), art.get("webUrl", ""),
                (fields.get("trailText") or "")[:500],
                art.get("webPublicationDate", ""), now,
            ])
        execute("DELETE FROM gold_news WHERE topic=?", [t_key])
        execute("""
            INSERT INTO gold_news
            SELECT topic, count(*),
                   (SELECT section FROM silver_news
                    WHERE topic=?
                    GROUP BY section ORDER BY count(*) DESC LIMIT 1) AS top_section,
                   max(last_fetched)
            FROM silver_news WHERE topic=? GROUP BY topic
        """, [t_key, t_key])
    except Exception as e:
        print(f"[narrative_iq] news: {e}")


def fetch_books(topic: str, force: bool = False) -> None:
    _init_tables()
    t_key = topic.strip().lower()
    if not (force or is_stale("bronze_books", "topic", t_key)):
        return
    try:
        data = fetch_json(_OL_SEARCH_URL, params={
            "q": topic.strip(), "limit": 30,
            "fields": "title,author_name,first_publish_year,edition_count,cover_edition_key",
        })
        docs = data.get("docs", [])
        now  = datetime.now(timezone.utc)
        execute("DELETE FROM bronze_books WHERE topic=?", [t_key])
        execute("INSERT INTO bronze_books VALUES (?,?,?)", [t_key, json.dumps(docs[:30]), now])
        execute("DELETE FROM silver_books WHERE topic=?", [t_key])
        for doc in docs[:30]:
            authors = doc.get("author_name") or []
            execute("INSERT INTO silver_books VALUES (?,?,?,?,?,?,?)", [
                t_key, doc.get("title", "")[:300],
                ", ".join(authors[:3]),
                doc.get("first_publish_year"), doc.get("edition_count"),
                doc.get("cover_edition_key", ""), now,
            ])
        execute("DELETE FROM gold_books WHERE topic=?", [t_key])
        execute("""
            INSERT INTO gold_books
            SELECT topic, count(*), avg(first_publish_year),
                   max(edition_count), max(last_fetched)
            FROM silver_books WHERE topic=? GROUP BY topic
        """, [t_key])
    except Exception as e:
        print(f"[narrative_iq] books: {e}")


def fetch_shows(topic: str, force: bool = False) -> None:
    _init_tables()
    t_key = topic.strip().lower()
    if not (force or is_stale("bronze_shows", "topic", t_key)):
        return
    try:
        data = fetch_json(_TVMAZE_URL, params={"q": topic.strip()})
        now  = datetime.now(timezone.utc)
        execute("DELETE FROM bronze_shows WHERE topic=?", [t_key])
        execute("INSERT INTO bronze_shows VALUES (?,?,?)", [t_key, json.dumps(data), now])
        execute("DELETE FROM silver_shows WHERE topic=?", [t_key])
        for item in data[:30]:
            show = item.get("show") or {}
            genres    = ", ".join(show.get("genres") or [])
            rating_val = (show.get("rating") or {}).get("average")
            clean_sum  = re.sub(r"<[^>]+>", "", show.get("summary") or "")[:400]  # strip HTML tags
            execute("INSERT INTO silver_shows VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
                t_key, show.get("id"), show.get("name", "")[:200],
                show.get("type", ""), show.get("language", ""),
                genres, show.get("status", ""),
                float(rating_val) if rating_val else None,
                show.get("premiered", ""), clean_sum, now,
            ])
        execute("DELETE FROM gold_shows WHERE topic=?", [t_key])
        execute("""
            INSERT INTO gold_shows
            SELECT topic, count(*), avg(rating),
                   (SELECT genres FROM silver_shows
                    WHERE topic=? AND genres IS NOT NULL AND genres != ''
                    GROUP BY genres ORDER BY count(*) DESC LIMIT 1) AS top_genre,
                   max(last_fetched)
            FROM silver_shows WHERE topic=? GROUP BY topic
        """, [t_key, t_key])
    except Exception as e:
        print(f"[narrative_iq] shows: {e}")


def fetch_all(topic: str, force: bool = False) -> None:
    _init_tables()
    fetch_news(topic, force)
    fetch_books(topic, force)
    fetch_shows(topic, force)


def get_silver_news(topic: str) -> pd.DataFrame:
    if not table_exists("silver_news"):
        return pd.DataFrame()
    t_key = topic.strip().lower()
    return query_df(
        "SELECT title, section, pub_date, trail_text, web_url "
        "FROM silver_news WHERE topic=? ORDER BY pub_date DESC", [t_key],
    )


def get_gold_news(topic: str) -> pd.DataFrame:
    if not table_exists("gold_news"):
        return pd.DataFrame()
    return query_df("SELECT * FROM gold_news WHERE topic=?", [topic.strip().lower()])


def get_silver_books(topic: str) -> pd.DataFrame:
    if not table_exists("silver_books"):
        return pd.DataFrame()
    return query_df(
        "SELECT title, author, first_publish_year, edition_count "
        "FROM silver_books WHERE topic=? ORDER BY edition_count DESC NULLS LAST",
        [topic.strip().lower()],
    )


def get_gold_books(topic: str) -> pd.DataFrame:
    if not table_exists("gold_books"):
        return pd.DataFrame()
    return query_df("SELECT * FROM gold_books WHERE topic=?", [topic.strip().lower()])


def get_silver_shows(topic: str) -> pd.DataFrame:
    if not table_exists("silver_shows"):
        return pd.DataFrame()
    return query_df(
        "SELECT show_name, show_type, language, genres, status, rating, premiered, summary "
        "FROM silver_shows WHERE topic=? ORDER BY rating DESC NULLS LAST",
        [topic.strip().lower()],
    )


def get_gold_shows(topic: str) -> pd.DataFrame:
    if not table_exists("gold_shows"):
        return pd.DataFrame()
    return query_df("SELECT * FROM gold_shows WHERE topic=?", [topic.strip().lower()])


def last_fetched(topic: str) -> str:
    t_key = topic.strip().lower()
    for tbl in ["bronze_news", "bronze_books", "bronze_shows"]:
        t = last_fetched_str(tbl, "topic", t_key)
        if t != "Never":
            return t
    return "Never"
