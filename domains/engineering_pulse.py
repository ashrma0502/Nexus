# domains/engineering_pulse.py — GitHub repo search.
# Optional: set GITHUB_TOKEN env var / st.secrets to raise rate limit 60 → 5000 req/hr.
import json
import os
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from core.db import execute, is_stale, last_fetched_str, query_df, table_exists
from core.fetch import fetch_json

_GH_BASE = "https://api.github.com"


def _gh_headers() -> dict[str, str]:
    """Return GitHub auth headers if a token is available."""
    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _init_tables():
    execute("""CREATE TABLE IF NOT EXISTS bronze_github_search (
        query VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_github_search (
        query VARCHAR, repo_full_name VARCHAR, stars INT, forks INT,
        language VARCHAR, description VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_github_repo (
        repo_full_name VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_github_repo (
        repo_full_name VARCHAR, owner VARCHAR, repo VARCHAR,
        stars INT, forks INT, open_issues INT, watchers INT,
        language VARCHAR, created_at VARCHAR, updated_at VARCHAR,
        pushed_at VARCHAR, description VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_github_repo (
        repo_full_name VARCHAR, stars INT, forks INT, open_issues INT,
        days_since_push INT, language VARCHAR, last_fetched TIMESTAMPTZ)""")


def search_repos(query: str, force: bool = False) -> pd.DataFrame:
    """Search GitHub repos; cache 1 h. Returns top-20 by stars."""
    _init_tables()
    q_key = query.strip().lower()
    if not q_key:
        return pd.DataFrame()
    if not (force or is_stale("bronze_github_search", "query", q_key)):
        return _read_search(q_key)

    try:
        data = fetch_json(
            f"{_GH_BASE}/search/repositories",
            params={
                "q": query.strip() + " stars:>10",
                "sort": "stars", "order": "desc",
                "per_page": 20,
            },
            headers=_gh_headers(),
        )
        items = data.get("items", [])
        now   = datetime.now(timezone.utc)

        execute("DELETE FROM bronze_github_search WHERE query=?", [q_key])
        execute("INSERT INTO bronze_github_search VALUES (?,?,?)",
                [q_key, json.dumps(items), now])

        execute("DELETE FROM silver_github_search WHERE query=?", [q_key])
        for repo in items:
            execute("INSERT INTO silver_github_search VALUES (?,?,?,?,?,?,?)", [
                q_key,
                repo.get("full_name",""),
                repo.get("stargazers_count"),
                repo.get("forks_count"),
                repo.get("language",""),
                (repo.get("description") or "")[:300],
                now,
            ])
    except Exception as e:
        print(f"[engineering_pulse] github search error: {e}")
    return _read_search(q_key)


def _read_search(q_key: str) -> pd.DataFrame:
    if not table_exists("silver_github_search"):
        return pd.DataFrame()
    return query_df(
        "SELECT repo_full_name, stars, forks, language, description "
        "FROM silver_github_search WHERE query=? ORDER BY stars DESC",
        [q_key],
    )


def fetch_repo(repo_full_name: str, force: bool = False) -> None:
    _init_tables()
    if not (force or is_stale("bronze_github_repo", "repo_full_name", repo_full_name)):
        return
    try:
        data = fetch_json(
            f"{_GH_BASE}/repos/{repo_full_name}",
            headers=_gh_headers(),
        )
        now = datetime.now(timezone.utc)

        execute("DELETE FROM bronze_github_repo WHERE repo_full_name=?", [repo_full_name])
        execute("INSERT INTO bronze_github_repo VALUES (?,?,?)",
                [repo_full_name, json.dumps(data), now])

        parts = repo_full_name.split("/", 1)
        execute("DELETE FROM silver_github_repo WHERE repo_full_name=?", [repo_full_name])
        execute("INSERT INTO silver_github_repo VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            repo_full_name,
            parts[0] if parts else "",
            parts[1] if len(parts) > 1 else "",
            data.get("stargazers_count"),
            data.get("forks_count"),
            data.get("open_issues_count"),
            data.get("watchers_count"),
            data.get("language",""),
            data.get("created_at",""),
            data.get("updated_at",""),
            data.get("pushed_at",""),
            (data.get("description") or "")[:300],
            now,
        ])

        # Gold
        pushed = data.get("pushed_at","")
        try:
            from dateutil import parser as dtp
            push_dt = dtp.parse(pushed).replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - push_dt).days
        except Exception:
            days_since = None

        execute("DELETE FROM gold_github_repo WHERE repo_full_name=?", [repo_full_name])
        execute("INSERT INTO gold_github_repo VALUES (?,?,?,?,?,?,?)", [
            repo_full_name,
            data.get("stargazers_count"),
            data.get("forks_count"),
            data.get("open_issues_count"),
            days_since,
            data.get("language",""),
            now,
        ])
    except Exception as e:
        print(f"[engineering_pulse] repo detail error: {e}")

def get_silver_github(repo_full_name: str) -> pd.DataFrame:
    if not table_exists("silver_github_repo"):
        return pd.DataFrame()
    return query_df(
        "SELECT * FROM silver_github_repo WHERE repo_full_name=?",
        [repo_full_name],
    )


def get_gold_github(repo_full_name: str) -> pd.DataFrame:
    if not table_exists("gold_github_repo"):
        return pd.DataFrame()
    return query_df(
        "SELECT * FROM gold_github_repo WHERE repo_full_name=?",
        [repo_full_name],
    )


def last_fetched(repo_full_name: str) -> str:
    return last_fetched_str("bronze_github_repo", "repo_full_name", repo_full_name)
