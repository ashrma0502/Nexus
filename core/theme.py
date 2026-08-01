# core/theme.py — Shared CSS, page widgets, Plotly layout, and dynamic symbol helpers.
# Call inject_css() once at the top of every page.
import streamlit as st


def inject_css():
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
code, pre { font-family: 'JetBrains Mono', monospace; }

div[data-testid="metric-container"] {
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    border: 1px solid rgba(124,58,237,0.30);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    height: auto !important;
    min-height: unset !important;
}
div[data-testid="metric-container"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 28px rgba(124,58,237,0.22);
}
/* Allow long metric values (e.g. weather condition) to wrap instead of truncating */
div[data-testid="stMetricValue"] > div {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    font-size: clamp(1rem, 2vw, 1.75rem) !important;
    line-height: 1.3 !important;
    word-break: break-word !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D0D1A 0%, #1A1A2E 100%);
    border-right: 1px solid rgba(124,58,237,0.18);
}
h1 { font-size: 1.9rem !important; font-weight: 700 !important; }
h2 { font-size: 1.4rem !important; font-weight: 600 !important; }
h1, h2 {
    background: linear-gradient(135deg, #7C3AED 0%, #A78BFA 60%, #C4B5FD 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
div[data-testid="stButton"] > button {
    background: linear-gradient(135deg, #7C3AED, #6D28D9);
    color: #fff !important;
    border: none;
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.2s ease;
}
div[data-testid="stButton"] > button:hover {
    background: linear-gradient(135deg, #8B5CF6, #7C3AED);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(124,58,237,0.40);
}
button[data-baseweb="tab"] { font-weight: 500; font-size: 0.92rem; }
div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
.nexus-status {
    background: linear-gradient(90deg, rgba(124,58,237,0.12) 0%, rgba(109,40,217,0.06) 100%);
    border: 1px solid rgba(124,58,237,0.28);
    border-radius: 10px;
    padding: 0.55rem 1rem;
    margin: 0.4rem 0 1rem 0;
    font-size: 0.85rem;
    color: #C4B5FD;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.nexus-hero {
    padding: 1.2rem 0 0.8rem 0;
    border-bottom: 1px solid rgba(124,58,237,0.18);
    margin-bottom: 1.4rem;
}
.nexus-hero p { color: #94A3B8; margin: 0.2rem 0 0 0; font-size: 0.97rem; }
.domain-badge {
    display: inline-block;
    background: rgba(124,58,237,0.18);
    border: 1px solid rgba(124,58,237,0.35);
    border-radius: 20px;
    padding: 0.15rem 0.65rem;
    font-size: 0.75rem;
    color: #A78BFA;
    font-weight: 500;
    margin: 0.1rem;
}
</style>
""",
        unsafe_allow_html=True,
    )


def page_header(icon: str, title: str, subtitle: str):
    st.markdown(
        f'<div class="nexus-hero"><h1 style="margin:0">{icon}&nbsp;{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def refresh_bar(last_time: str, key: str) -> bool:
    """Show last-refreshed status and a Refresh button. Returns True if clicked."""
    col_info, col_btn = st.columns([6, 1])
    with col_info:
        st.markdown(
            f'<div class="nexus-status">🕐 Last refreshed: <b>{last_time}</b>'
            f"&nbsp;&nbsp;·&nbsp;&nbsp;Auto-refreshes after 1 hour</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        return st.button("🔄 Refresh", key=f"refresh_{key}", use_container_width=True)


def badges(*labels: str):
    """Render pill badges for data source labels."""
    html = "".join(f'<span class="domain-badge">{l}</span>' for l in labels)
    st.markdown(html, unsafe_allow_html=True)


# Shared Plotly dark theme applied to every chart
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(26,26,46,0.6)",
    font=dict(family="Inter, sans-serif", color="#E2E8F0"),
    margin=dict(l=8, r=8, t=36, b=8),
    xaxis=dict(gridcolor="rgba(124,58,237,0.12)", zerolinecolor="rgba(124,58,237,0.2)"),
    yaxis=dict(gridcolor="rgba(124,58,237,0.12)", zerolinecolor="rgba(124,58,237,0.2)"),
    colorway=["#7C3AED","#A78BFA","#60A5FA","#34D399","#FBBF24","#F87171","#38BDF8"],
)

# --- Dynamic symbol helpers ---------------------------------------------------
# These maps drive UI labels that update when the user changes a selector.

_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",   "EUR": "€",   "GBP": "£",   "JPY": "¥",
    "CNY": "¥",   "INR": "₹",   "KRW": "₩",   "CHF": "Fr",
    "CAD": "CA$", "AUD": "A$",  "HKD": "HK$", "SGD": "S$",
    "MXN": "Mx$", "BRL": "R$",  "RUB": "₽",   "TRY": "₺",
    "ZAR": "R",   "SEK": "kr",  "NOK": "kr",  "DKK": "kr",
    "PLN": "zł",  "THB": "฿",   "IDR": "Rp",  "HUF": "Ft",
    "CZK": "Kč",  "ILS": "₪",   "PHP": "₱",   "MYR": "RM",
    "RON": "lei", "AED": "د.إ", "SAR": "﷼",  "QAR": "﷼",
    "BGN": "лв",  "HRK": "kn",  "ISK": "kr",  "NZD": "NZ$",
}

_CRYPTO_ICONS: dict[str, str] = {
    "bitcoin": "₿",       "ethereum": "Ξ",         "tether": "₮",
    "binancecoin": "BNB", "ripple": "✕",           "cardano": "₳",
    "solana": "◎",        "polkadot": "●",          "dogecoin": "Ð",
    "litecoin": "Ł",      "chainlink": "⬡",         "stellar": "✦",
    "monero": "ɱ",        "tron": "TRX",            "avalanche-2": "AVAX",
    "shiba-inu": "🐕",    "uniswap": "🦄",          "wrapped-bitcoin": "₿",
    "dai": "◈",           "cosmos": "⚛",            "internet-computer": "∞",
}

# Open-Meteo WMO weather code → emoji
_WX_EMOJIS: dict[int, str] = {
    0: "☀️",  1: "🌤️",  2: "⛅",   3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌧️",
    61: "🌧️", 63: "🌧️", 65: "🌊",
    71: "🌨️", 73: "❄️",  75: "❄️",  77: "🌨️",
    80: "🌦️", 81: "🌧️", 82: "⛈️",
    85: "🌨️", 86: "❄️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}

# FakeStore API categories → emoji
_CATEGORY_ICONS: dict[str, str] = {
    "electronics": "💻", "jewelery": "💍",
    "men's clothing": "👔", "women's clothing": "👗",
    "furniture": "🛋️", "groceries": "🛒", "sports": "⚽",
    "beauty": "💄", "home": "🏠", "toys": "🧸",
    "books": "📚", "automotive": "🚗", "music": "🎵", "garden": "🌿",
}

# Air quality parameter → emoji
_AQ_ICONS: dict[str, str] = {
    "pm25": "💨", "pm10": "🌬️", "o3": "☁️",
    "no2": "🏭", "so2": "⚗️",  "co": "🔥",
    "bc": "⬛",  "no": "🏭",
}


def currency_symbol(code: str) -> str:
    return _CURRENCY_SYMBOLS.get(code, code)


def crypto_icon(coin_id: str, fallback_symbol: str = "") -> str:
    return _CRYPTO_ICONS.get(coin_id, fallback_symbol or "🪙")


def weather_emoji(code) -> str:
    try:
        return _WX_EMOJIS.get(int(code), "🌡️")
    except (TypeError, ValueError):
        return "🌡️"


def category_icon(category: str) -> str:
    return _CATEGORY_ICONS.get(category.lower(), "🏷️")


def aq_icon(parameter: str) -> str:
    return _AQ_ICONS.get((parameter or "").lower(), "🌫️")
