# core/fetch.py — HTTP fetcher with tenacity retry (3 attempts, exponential back-off).
# All domain modules use fetch_json(); TTL caching is handled by DuckDB, not here.
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Nexus-Platform/1.0",
    "Accept": "application/json",
})


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
    reraise=True,
)
def fetch_json(url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 20):
    """GET url, retrying on network errors. Raises HTTPError on 4xx/5xx."""
    resp = _SESSION.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
