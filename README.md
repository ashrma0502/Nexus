# Nexus

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://project-nexus.streamlit.app/)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/framework-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![DuckDB](https://img.shields.io/badge/database-DuckDB-FFF000)

**Nexus** is a multi-domain, real-time data intelligence platform built with [Streamlit](https://streamlit.io). Five focused dashboards — covering cities, macroeconomics, retail, media, and software engineering — pull live data from a dozen free public APIs into a lightweight [DuckDB](https://duckdb.org) warehouse, organized as a Bronze → Silver → Gold pipeline.

**🔴 Live app: [project-nexus.streamlit.app](https://project-nexus.streamlit.app/)**

- 🖥️ **5 dashboards**, one Streamlit multipage app
- 🔌 **12 free public APIs** — nothing requires sign-up just to run it
- 🗄️ **DuckDB** medallion warehouse (Bronze → Silver → Gold) in a single embedded file — no external database to stand up
- 🔁 **TTL-based caching** (1–24h depending on the source) with a manual "Refresh" button on every page
- 🎨 A custom dark theme with live **Plotly** charts throughout

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Data Sources and Attribution](#data-sources-and-attribution)
- [Deploying Your Own Copy](#deploying-your-own-copy)
- [Contributing](#contributing)
- [License](#license)

## Features

| Module | Entry point | Highlights | Data sources |
|---|---|---|---|
| 🌆 **CityPulse** | `app.py` (Home) | Current weather + 7-day forecast summary, hourly air-quality readings by pollutant, and earthquakes ≥ M1.5 within 500 km of a city over the last 30 days. Auto-detects your city via browser geolocation, or search any city by name. | Open-Meteo (Geocoding, Forecast, Air Quality), USGS Earthquake Catalog, Nominatim |
| 📊 **MacroLens** | `pages/1_MacroLens.py` | Live pricing for any of the top 250 cryptocurrencies, auto-converted into your chosen currency; full FX rate tables; and a searchable catalogue of ~1,400 World Bank development indicators with historical trend charts. | CoinGecko, Frankfurter, World Bank |
| 🛒 **RetailIQ** | `pages/2_RetailIQ.py` | Product catalog by category with price/rating distributions, plus a food & nutrition lookup (macros, Nutri-Score, NOVA group) for any ingredient. | FakeStore API, Open Food Facts |
| 📰 **NarrativeIQ** | `pages/3_NarrativeIQ.py` | One topic search fanned out across news articles, books, and TV shows simultaneously. | The Guardian Open Platform, Open Library, TVMaze |
| ⚙️ **EngineeringPulse** | `pages/4_EngineeringPulse.py` | GitHub repository search ranked by stars, with a deep-dive view (forks, open issues, days since last push) for any repo. | GitHub REST API |

Every dashboard follows the same pattern: pick or search for an entity in the sidebar (or, on CityPulse, allow geolocation), Nexus fetches and caches the underlying data, and results render as KPI cards, sortable tables, and Plotly charts across topic-specific tabs.

## Architecture

### Bronze → Silver → Gold, in DuckDB

Every domain module (`domains/*.py`) follows the same medallion pattern, all inside one embedded DuckDB file (`nexus_warehouse.duckdb`):

```
User action (search / select / click "Refresh")
                │
                ▼
   is_stale(table, key, ttl_hours)?     ── core/db.py
                │  yes (or forced)
                ▼
     fetch_json(url, params)            ── core/fetch.py
     requests + tenacity retry (3 attempts, exponential backoff)
                │
                ▼
  BRONZE   raw API JSON + last_fetched timestamp   (untouched audit trail)
                │
                ▼
  SILVER   flattened, typed, one row per record     (e.g. one row per pollutant reading)
                │
                ▼
   GOLD    aggregated KPIs, computed in SQL          (avg / max / count, via DuckDB)
                │
                ▼
   Streamlit page reads Silver/Gold via get_*() accessors
   → st.metric / st.dataframe / Plotly charts
```

- **Bronze** stores the untouched API response as a JSON string, so nothing is lost even if downstream parsing logic changes later.
- **Silver** is the parsed, per-record view — what you'd query for a raw list of earthquakes, coins, or articles.
- **Gold** is a pre-aggregated summary table — what actually powers the `st.metric` cards, computed once per fetch rather than on every rerender.

### Shared core modules

| Module | Responsibility |
|---|---|
| `core/db.py` | A single cached DuckDB connection (`st.cache_resource`, thread-locked), generic `execute` / `query_df` / `fetchone` helpers, and `is_stale()` — the TTL check every domain module runs before hitting an API. Also ships `warehouse_stats()` and `distinct_entities()`, ready-made helpers for an admin/observability view over the warehouse (defined but not yet wired into a page). |
| `core/fetch.py` | `fetch_json()` — a `requests.Session` wrapper with `tenacity` retry (3 attempts, exponential backoff) on timeouts/connection errors. Every external API call in the app goes through this one function. |
| `core/theme.py` | Injects the shared dark/purple CSS once per page, renders the header/badge/refresh-bar widgets, defines the shared Plotly layout, and maps raw codes (WMO weather codes, currency codes, AQ parameters, product categories, crypto symbols) to emoji/icons that update live as selectors change. |

### Caching model

- Each Bronze table carries a `last_fetched TIMESTAMPTZ`. `is_stale()` compares it against a TTL — **1 hour** by default, **24 hours** for the World Bank indicator catalogue (large and slow-changing).
- Every page has a **🔄 Refresh** button that bypasses the TTL and force-fetches fresh data on demand.
- Because reads are keyed (by city, coin, topic, category, repo, …), previously explored entities stay cached in the warehouse for the rest of the session — revisiting "London" or "bitcoin" is instant until the TTL expires.

## Project Structure

```
Nexus/
├── app.py                      # Home page — CityPulse (Weather · Air Quality · Earthquakes)
├── requirements.txt
├── core/
│   ├── db.py                   # DuckDB singleton, execute/query helpers, TTL staleness checks
│   ├── fetch.py                # fetch_json() — requests + tenacity retry wrapper
│   └── theme.py                # Shared CSS, header/refresh-bar widgets, Plotly theme, icon maps
├── domains/                    # ETL logic per module: fetch → Bronze → Silver → Gold
│   ├── city_pulse.py           # Weather, Air Quality, Earthquakes
│   ├── macro_lens.py           # Crypto, FX Rates, World Bank Indicators
│   ├── retail_iq.py            # Retail Products, Food / Nutrition
│   ├── narrative_iq.py         # News, Books, TV Shows
│   └── engineering_pulse.py    # GitHub Repositories
└── pages/                      # Streamlit multipage routes (sidebar order = filename prefix)
    ├── 1_MacroLens.py
    ├── 2_RetailIQ.py
    ├── 3_NarrativeIQ.py
    └── 4_EngineeringPulse.py
```

*(`__init__.py` package markers are omitted above for brevity.)*

Two more paths appear at runtime and are intentionally **gitignored**:

- `nexus_warehouse.duckdb` (+ `.wal`) — the DuckDB warehouse file, created on first run
- `.streamlit/secrets.toml` — optional local secrets (see [Configuration](#configuration))

## Tech Stack

| Package | Role |
|---|---|
| [`streamlit`](https://streamlit.io) | App framework — multipage routing, widgets, and `st.cache_resource` |
| [`duckdb`](https://duckdb.org) | Embedded OLAP database — the Bronze/Silver/Gold warehouse, single file, no server |
| [`pandas`](https://pandas.pydata.org) | DataFrames for every Silver/Gold read and in-app transform |
| [`plotly`](https://plotly.com/python/) | All interactive charts — bar, line, scatter, histogram, and map-based views |
| [`requests`](https://requests.readthedocs.io) | HTTP client underlying every API call |
| [`tenacity`](https://tenacity.readthedocs.io) | Retry with exponential backoff on network errors (`core/fetch.py`) |
| [`python-dateutil`](https://dateutil.readthedocs.io) | Robust ISO-timestamp parsing (e.g. GitHub's `pushed_at` → "days since last push") |
| [`humanize`](https://github.com/python-humanize/humanize) | Human-friendly number/date formatting utilities |
| [`watchdog`](https://github.com/gorakhargosh/watchdog) | Fast local file-change detection for Streamlit's dev-mode auto-reload |
| [`streamlit-js-eval`](https://github.com/aghasemi/streamlit_js_eval) | Reads the browser's Geolocation API from Python (CityPulse's "use my location") |

## Getting Started

### Prerequisites

- Python 3.10+ (the codebase uses `X | None` union type hints, which require 3.10)
- pip

### 1. Clone and enter the project

```bash
git clone <this-repository-url>
cd Nexus
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run it

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`. On first load, CityPulse will ask your browser for location permission — allow it for an instant local forecast, or just type a city name to search instead.

## Configuration

Nexus runs with **zero configuration** — every data source works without an API key. Two optional secrets unlock higher limits or full functionality on one page each:

| Secret | Required? | Effect if unset | Get one at |
|---|---|---|---|
| `GUARDIAN_API_KEY` | No | Falls back to the Guardian's shared `"test"` key, which works but is rate-limited and meant for demos | [open-platform.theguardian.com/access](https://open-platform.theguardian.com/access/) (free) |
| `GITHUB_TOKEN` | No | GitHub requests stay unauthenticated (lower rate limit); a token raises it to 5,000 requests/hour | GitHub → Settings → Developer settings → Personal access tokens (no scopes needed) |

To set them locally, create `.streamlit/secrets.toml` (already gitignored):

```toml
# .streamlit/secrets.toml — optional, the app works without this file
GUARDIAN_API_KEY = "your-guardian-api-key"
GITHUB_TOKEN = "ghp_your_personal_access_token"
```

Both also work as plain environment variables (`GUARDIAN_API_KEY`, `GITHUB_TOKEN`) — the code checks `st.secrets` first and falls back to `os.environ`.

## Data Sources and Attribution

| Domain | API | Auth | Notes |
|---|---|---|---|
| CityPulse | [Open-Meteo](https://open-meteo.com) (Geocoding, Forecast, Air Quality) | None | Free, no key required |
| CityPulse | [USGS Earthquake Catalog](https://earthquake.usgs.gov/fdsnws/event/1/) | None | Public USGS feed |
| CityPulse | [Nominatim](https://nominatim.org) (OpenStreetMap) | None | Used only for reverse-geocoding device coordinates; a descriptive `User-Agent` is sent per Nominatim's usage policy |
| MacroLens | [CoinGecko](https://www.coingecko.com/en/api) | None | Public market-data endpoint |
| MacroLens | [Frankfurter](https://www.frankfurter.app) | None | ECB-sourced FX rates |
| MacroLens | [World Bank](https://data.worldbank.org) | None | Indicators + country catalogue |
| RetailIQ | [FakeStore API](https://fakestoreapi.com) | None | Demo e-commerce product data |
| RetailIQ | [Open Food Facts](https://world.openfoodfacts.org) | None | Community-maintained food database |
| NarrativeIQ | [The Guardian Open Platform](https://open-platform.theguardian.com) | Optional | See [Configuration](#configuration) |
| NarrativeIQ | [Open Library](https://openlibrary.org/developers/api) | None | |
| NarrativeIQ | [TVMaze](https://www.tvmaze.com/api) | None | |
| EngineeringPulse | [GitHub REST API](https://docs.github.com/en/rest) | Optional | See [Configuration](#configuration) |

Please respect each provider's rate limits and terms of use — Nexus is a demo/portfolio project, not a production data vendor.

## Deploying Your Own Copy

The live instance runs on [Streamlit Community Cloud](https://streamlit.io/cloud). To deploy your own:

1. Push this repository to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** → select your repo, the `main` branch, and `app.py` as the main file.
3. *(Optional)* Add `GUARDIAN_API_KEY` and/or `GITHUB_TOKEN` under **App settings → Secrets**, using the same TOML format shown in [Configuration](#configuration).
4. Deploy — Streamlit installs `requirements.txt` and launches the app.

Note that Community Cloud's filesystem is ephemeral per container: `nexus_warehouse.duckdb` will reset on redeploys or reboots. That's expected — it's a TTL cache, not a system of record, and rebuilds itself from the live APIs on the next visit.

## Contributing

Contributions are welcome:

1. Fork the repo and create a feature branch.
2. Follow the existing Bronze → Silver → Gold pattern for any new data source — any file in `domains/` works as a template.
3. Register new tables in an `_init_tables()` function and thread `last_fetched` through so the TTL/Refresh behavior stays consistent.
4. Open a pull request with a short description of the change.

## License

This repository does not currently include a license file. If you plan to reuse, fork, or distribute this code, please add a `LICENSE` (e.g. MIT) or check with the repository owner for terms.
