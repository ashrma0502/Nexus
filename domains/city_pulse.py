# domains/city_pulse.py — Weather, Air Quality, Earthquakes per city.
# APIs: Open-Meteo (geo+weather+AQ), USGS (earthquakes).
import json
import math
from datetime import datetime, timedelta, timezone

import pandas as pd

from core.db import execute, is_stale, last_fetched_str, query_df, table_exists
from core.fetch import fetch_json

# ── API endpoints ─────────────────────────────────────────────────────────────
_GEO_URL   = "https://geocoding-api.open-meteo.com/v1/search"
_WX_URL    = "https://api.open-meteo.com/v1/forecast"
_AQ_URL    = "https://air-quality-api.open-meteo.com/v1/air-quality"  # replaces deprecated OpenAQ v2
_USGS_URL  = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Pollutants to request from Open-Meteo AQ
_AQ_PARAMS = "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone,sulphur_dioxide"

# Display name mapping (Open-Meteo field → readable label)
_AQ_LABELS = {
    "pm10":             "pm10",
    "pm2_5":            "pm25",
    "carbon_monoxide":  "co",
    "nitrogen_dioxide": "no2",
    "ozone":            "o3",
    "sulphur_dioxide":  "so2",
}

# WMO weather code → description string
_WX_CODES = {
    0:"Clear sky", 1:"Mainly clear", 2:"Partly cloudy", 3:"Overcast",
    45:"Fog", 48:"Icy fog", 51:"Light drizzle", 53:"Drizzle", 55:"Heavy drizzle",
    61:"Light rain", 63:"Rain", 65:"Heavy rain", 71:"Light snow", 73:"Snow",
    75:"Heavy snow", 77:"Snow grains", 80:"Light showers", 81:"Showers",
    82:"Heavy showers", 85:"Snow showers", 86:"Heavy snow showers",
    95:"Thunderstorm", 96:"Thunderstorm w/ hail", 99:"Thunderstorm w/ heavy hail",
}


# Table initialization
def _init_tables():
    execute("""CREATE TABLE IF NOT EXISTS bronze_weather (
        city_key VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_weather (
        city_key VARCHAR, city_name VARCHAR, country VARCHAR,
        lat DOUBLE, lon DOUBLE, temp_c DOUBLE, feels_like_c DOUBLE,
        humidity INT, wind_kph DOUBLE, weather_code INT, precip_mm DOUBLE,
        wx_desc VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_weather_summary (
        city_key VARCHAR, max_temp_7d DOUBLE, min_temp_7d DOUBLE,
        total_precip_7d DOUBLE, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_air_quality (
        city_key VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_air_quality (
        city_key VARCHAR, location_name VARCHAR, parameter VARCHAR,
        value DOUBLE, unit VARCHAR, last_updated VARCHAR,
        last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_air_quality (
        city_key VARCHAR, parameter VARCHAR, avg_value DOUBLE,
        max_value DOUBLE, location_count BIGINT, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS bronze_earthquakes (
        city_key VARCHAR, raw_json VARCHAR, last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS silver_earthquakes (
        city_key VARCHAR, eq_id VARCHAR, magnitude DOUBLE, place VARCHAR,
        eq_time TIMESTAMPTZ, lat DOUBLE, lon DOUBLE, depth_km DOUBLE,
        last_fetched TIMESTAMPTZ)""")
    execute("""CREATE TABLE IF NOT EXISTS gold_earthquakes (
        city_key VARCHAR, eq_count BIGINT, avg_magnitude DOUBLE,
        max_magnitude DOUBLE, last_fetched TIMESTAMPTZ)""")


# Geocoding utility
def search_cities(query: str) -> list[dict]:
    """Geocode query via Open-Meteo; returns list of city dicts."""
    if len(query.strip()) < 2:
        return []
    try:
        data = fetch_json(_GEO_URL, params={
            "name": query.strip(), "count": 12,
            "language": "en", "format": "json",
        })
        cities = []
        for r in data.get("results", []):
            code = r.get("country_code", "XX")
            key  = f"{r.get('name','').lower().replace(' ','_')}_{code.lower()}"
            admin = r.get("admin1") or ""
            cities.append({
                "key":     key,
                "name":    r.get("name", ""),
                "admin":   admin,
                "country": r.get("country", ""),
                "code":    code,
                "lat":     r.get("latitude"),
                "lon":     r.get("longitude"),
                "display": f"{r.get('name')}, {admin+', ' if admin else ''}{r.get('country','')}",
            })
        return cities
    except Exception:
        return []


def reverse_geocode_coords(lat: float, lon: float) -> dict | None:
    """Reverse geocode lat/lon via Nominatim; returns city dict or None on failure."""
    try:
        data = fetch_json(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10, "addressdetails": 1},
            headers={"User-Agent": "Nexus-Platform/1.0"},
        )
        addr  = data.get("address", {})
        name  = (addr.get("city") or addr.get("town") or addr.get("village")
                 or addr.get("county") or data.get("name", "Unknown"))
        country = addr.get("country", "")
        code    = addr.get("country_code", "xx").upper()
        admin   = addr.get("state") or addr.get("region") or ""
        key     = f"{name.lower().replace(' ','_')}_{code.lower()}_geo"
        return {
            "key":     key,
            "name":    name,
            "admin":   admin,
            "country": country,
            "code":    code,
            "lat":     lat,
            "lon":     lon,
            "display": f"{name}{', ' + admin if admin else ''}, {country}",
        }
    except Exception:
        return None


# Orchestrator
def fetch_city(city: dict, force: bool = False) -> None:
    """Fetch Weather, AQ, Earthquakes for a city into DuckDB."""
    _init_tables()
    key = city["key"]
    lat, lon = city["lat"], city["lon"]
    now = datetime.now(timezone.utc)

    _fetch_weather(key, city, lat, lon, now, force)
    _fetch_air_quality(key, lat, lon, now, force)
    _fetch_earthquakes(key, lat, lon, now, force)


# Weather data processing
def _fetch_weather(key, city, lat, lon, now, force):
    if not (force or is_stale("bronze_weather", "city_key", key)):
        return
    try:
        data = fetch_json(_WX_URL, params={
            "latitude": lat, "longitude": lon,
            "current": ",".join([
                "temperature_2m","apparent_temperature",
                "relative_humidity_2m","wind_speed_10m",
                "precipitation","weather_code",
            ]),
            "daily":   ",".join([
                "temperature_2m_max","temperature_2m_min","precipitation_sum",
            ]),
            "timezone": "auto", "forecast_days": 7,
        })
        cur  = data.get("current", {})
        day  = data.get("daily", {})
        code = cur.get("weather_code", 0)

        execute("DELETE FROM bronze_weather WHERE city_key=?", [key])
        execute("INSERT INTO bronze_weather VALUES (?,?,?)",
                [key, json.dumps(data), now])

        execute("DELETE FROM silver_weather WHERE city_key=?", [key])
        execute("""INSERT INTO silver_weather VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            key, city["name"], city["country"], lat, lon,
            cur.get("temperature_2m"),
            cur.get("apparent_temperature"),
            cur.get("relative_humidity_2m"),
            cur.get("wind_speed_10m"),
            code,
            cur.get("precipitation"),
            _WX_CODES.get(code, "Unknown"),
            now,
        ])

        max_t  = max(day.get("temperature_2m_max") or [None], default=None)
        min_t  = min(day.get("temperature_2m_min") or [None], default=None)
        precip = sum(x for x in (day.get("precipitation_sum") or []) if x is not None)

        execute("DELETE FROM gold_weather_summary WHERE city_key=?", [key])
        execute("INSERT INTO gold_weather_summary VALUES (?,?,?,?,?)",
                [key, max_t, min_t, precip, now])
    except Exception as e:
        print(f"[city_pulse] weather error: {e}")


# Air quality processing (Open-Meteo AQ — free, no key required)
def _fetch_air_quality(key, lat, lon, now, force):
    if not (force or is_stale("bronze_air_quality", "city_key", key)):
        return
    try:
        data = fetch_json(_AQ_URL, params={
            "latitude": lat, "longitude": lon,
            "current": _AQ_PARAMS,
        })

        execute("DELETE FROM bronze_air_quality WHERE city_key=?", [key])
        execute("INSERT INTO bronze_air_quality VALUES (?,?,?)",
                [key, json.dumps(data), now])

        current       = data.get("current", {})
        current_units = data.get("current_units", {})

        execute("DELETE FROM silver_air_quality WHERE city_key=?", [key])
        for field, label in _AQ_LABELS.items():
            value = current.get(field)
            if value is None:
                continue
            unit = current_units.get(field, "")
            execute("INSERT INTO silver_air_quality VALUES (?,?,?,?,?,?,?)", [
                key, "Open-Meteo", label, float(value), unit, current.get("time", ""), now,
            ])

        execute("DELETE FROM gold_air_quality WHERE city_key=?", [key])
        execute("""
            INSERT INTO gold_air_quality
            SELECT city_key, parameter,
                   avg(value), max(value),
                   count(DISTINCT location_name), max(last_fetched)
            FROM silver_air_quality
            WHERE city_key=? AND value IS NOT NULL
            GROUP BY city_key, parameter
        """, [key])
    except Exception as e:
        print(f"[city_pulse] air quality error: {e}")


# Earthquake processing
def _fetch_earthquakes(key, lat, lon, now, force):
    if not (force or is_stale("bronze_earthquakes", "city_key", key)):
        return
    try:
        start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        data  = fetch_json(_USGS_URL, params={
            "format": "geojson",
            "latitude": lat, "longitude": lon,
            "maxradiuskm": 500,
            "minmagnitude": 1.5,
            "limit": 50, "orderby": "time",
            "starttime": start,
        })

        execute("DELETE FROM bronze_earthquakes WHERE city_key=?", [key])
        execute("INSERT INTO bronze_earthquakes VALUES (?,?,?)",
                [key, json.dumps(data), now])

        execute("DELETE FROM silver_earthquakes WHERE city_key=?", [key])
        for feat in data.get("features", []):
            props  = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [None, None, None])
            eq_t   = None
            if props.get("time"):
                eq_t = datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc)
            execute("INSERT INTO silver_earthquakes VALUES (?,?,?,?,?,?,?,?,?)", [
                key, feat.get("id"),
                props.get("mag"), props.get("place"),
                eq_t,
                coords[1] if len(coords) > 1 else None,
                coords[0] if coords else None,
                coords[2] if len(coords) > 2 else None,
                now,
            ])

        execute("DELETE FROM gold_earthquakes WHERE city_key=?", [key])
        execute("""
            INSERT INTO gold_earthquakes
            SELECT city_key, count(*), avg(magnitude), max(magnitude), max(last_fetched)
            FROM silver_earthquakes WHERE city_key=? GROUP BY city_key
        """, [key])
    except Exception as e:
        print(f"[city_pulse] earthquakes error: {e}")


# Read accessors
def get_silver_weather(city_key: str) -> pd.DataFrame:
    if not table_exists("silver_weather"):
        return pd.DataFrame()
    return query_df("SELECT * FROM silver_weather WHERE city_key=?", [city_key])


def get_gold_weather(city_key: str) -> pd.DataFrame:
    if not table_exists("gold_weather_summary"):
        return pd.DataFrame()
    return query_df("SELECT * FROM gold_weather_summary WHERE city_key=?", [city_key])


def get_gold_air_quality(city_key: str) -> pd.DataFrame:
    if not table_exists("gold_air_quality"):
        return pd.DataFrame()
    return query_df(
        "SELECT * FROM gold_air_quality WHERE city_key=? ORDER BY avg_value DESC",
        [city_key],
    )


def get_silver_earthquakes(city_key: str) -> pd.DataFrame:
    if not table_exists("silver_earthquakes"):
        return pd.DataFrame()
    return query_df(
        "SELECT eq_time, magnitude, place, depth_km, lat, lon "
        "FROM silver_earthquakes WHERE city_key=? ORDER BY eq_time DESC",
        [city_key],
    )


def get_gold_earthquakes(city_key: str) -> pd.DataFrame:
    if not table_exists("gold_earthquakes"):
        return pd.DataFrame()
    return query_df("SELECT * FROM gold_earthquakes WHERE city_key=?", [city_key])


def last_fetched(city_key: str) -> str:
    return last_fetched_str("bronze_weather", "city_key", city_key)
