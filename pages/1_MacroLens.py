# pages/1_MacroLens.py — Crypto, FX Rates, World Bank Indicators.
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import domains.macro_lens as ml
from core.theme import (
    PLOTLY_LAYOUT, badges, crypto_icon, currency_symbol,
    inject_css, page_header, refresh_bar,
)

st.set_page_config(
    page_title="MacroLens — Nexus",
    page_icon="📊", layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
page_header("📊", "MacroLens", "Crypto · FX Rates · World Bank — live macro intelligence")
badges("CoinGecko", "Frankfurter", "World Bank")

# Load dynamic lists from APIs (cached 1 h)
with st.spinner("Loading coin, currency, and country lists…"):
    coins    = ml.fetch_coin_list()
    fx_dict   = ml.fetch_currency_list()
    countries  = ml.fetch_country_list()
    wb_inds    = ml.fetch_indicator_list()   # ~1,400 WDI indicators, cached 24 h

if not coins:
    st.error("Could not load CoinGecko coin list. Please check your connection.")
    st.stop()

# Sidebar selectors built from live API lists
with st.sidebar:
    st.markdown("### 🎛️ Controls")

    # Coin selector
    coin_options = {f"{c['name']} ({c['symbol']})": c for c in coins}
    selected_coin_label = st.selectbox(
        "🪙 Select Cryptocurrency",
        options=list(coin_options.keys()),
        key="coin_selector",
    )
    selected_coin = coin_options[selected_coin_label]
    coin_id = selected_coin["coin_id"]

    # Currency selector (from Frankfurter)
    if fx_dict:
        currency_options = {f"{v} ({k})": k for k, v in sorted(fx_dict.items())}
    else:
        currency_options = {"US Dollar (USD)": "USD", "Euro (EUR)": "EUR"}
    selected_currency_label = st.selectbox(
        "💱 Base Currency (FX)",
        options=list(currency_options.keys()),
        index=list(currency_options.values()).index("USD") if "USD" in currency_options.values() else 0,
        key="currency_selector",
    )
    base_currency = currency_options[selected_currency_label]

    # Country selector
    if countries:
        country_opts = {f"{c['name']} ({c['id']})": c for c in countries}
    else:
        country_opts = {}
    selected_country_label = st.selectbox(
        "🌍 Country (World Bank)",
        options=list(country_opts.keys()),
        key="country_selector",
    )
    selected_country = country_opts.get(selected_country_label, {})
    country_id = selected_country.get("id", "US")

    st.markdown("---")

    # Indicator multiselect — full WDI catalogue, searchable
    ind_options = {f"{r['indicator_name']} [{r['indicator_id']}]": r['indicator_id']
                   for r in wb_inds if r.get("indicator_id") and r.get("indicator_name")}

    # Default selection: the 5 common indicators (pre-ticked)
    default_defaults = [
        "NY.GDP.MKTP.CD", "NY.GDP.PCAP.CD", "SP.POP.TOTL",
        "FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS",
    ]
    # Find matching option labels for the defaults (names may differ slightly in live API)
    default_labels = [lbl for lbl, iid in ind_options.items() if iid in default_defaults]

    selected_ind_labels = st.multiselect(
        "📊 World Bank Indicators",
        options=list(ind_options.keys()),
        default=default_labels[:5],   # cap to 5 to avoid overwhelming first render
        max_selections=10,
        key="wb_indicator_selector",
        help="Type to search across ~1,400 World Development Indicators. Max 10.",
    )
    # Build {id: name} dict from selection
    selected_indicators = {
        ind_options[lbl]: lbl.rsplit(" [", 1)[0]
        for lbl in selected_ind_labels
        if lbl in ind_options
    }
last_time = ml.last_fetched(coin_id, base_currency, country_id)
force = refresh_bar(last_time, "macrolens")

with st.spinner("Fetching macro data…"):
    ml.fetch_crypto_markets(coin_id, vs_currency="usd", force=force)
    ml.fetch_fx_rates(base_currency, force=force)
    ml.fetch_worldbank(country_id, indicators=selected_indicators or None, force=force)

gold_crypto = ml.get_gold_crypto(coin_id)
gold_fx     = ml.get_gold_fx(base_currency)
# Filter World Bank reads to only the indicators the user selected
if selected_indicators:
    ind_ids = list(selected_indicators.keys())
    silver_wb = ml.get_silver_worldbank(country_id, indicator_ids=ind_ids)
    gold_wb   = ml.get_gold_worldbank(country_id, indicator_ids=ind_ids)
else:
    silver_wb = ml.get_silver_worldbank(country_id)
    gold_wb   = ml.get_gold_worldbank(country_id)

def crypto_in_local(crypto_price_usd, fx_df, local_currency):
    """Convert USD crypto price to local currency using Gold FX table."""
    if fx_df.empty or local_currency == "USD":
        return crypto_price_usd, local_currency
    row = fx_df[fx_df["target_currency"] == local_currency]
    if row.empty:
        return crypto_price_usd, "USD"
    rate = float(row.iloc[0]["rate"])
    return crypto_price_usd * rate, local_currency

tab_crypto, tab_fx, tab_wb = st.tabs(
    ["🪙 Crypto", "💱 FX Rates", "🌍 World Bank"]
)

with tab_crypto:
    if gold_crypto.empty:
        st.warning("No crypto data loaded.")
    else:
        row = gold_crypto.iloc[0]
        price_usd = float(row.get("price") or 0)
        price_local, local_sym = crypto_in_local(price_usd, gold_fx, base_currency)

        # Dynamic icons driven by current coin + currency selections
        c_icon  = crypto_icon(coin_id, selected_coin.get("symbol",""))  # e.g. ₿ for bitcoin
        cur_sym = currency_symbol(base_currency)                         # e.g. € for EUR
        chg     = float(row.get('change_24h') or 0)

        st.markdown(f"### {c_icon} {row.get('name','')} ({row.get('symbol','')})")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric(f"{c_icon} Price (USD)",         f"${price_usd:,.4f}")
        c2.metric(f"{cur_sym} Price ({base_currency})", f"{cur_sym}{price_local:,.4f}")
        c3.metric("📈 24h Change",
                  f"{chg:+.2f}%",
                  delta_color="normal" if chg >= 0 else "inverse")
        c4.metric("🏦 Market Cap", f"${float(row.get('market_cap') or 0)/1e9:.2f}B")
        c5.metric("📊 Volume 24h", f"${float(row.get('volume_24h') or 0)/1e9:.2f}B")

        if base_currency != "USD" and not gold_fx.empty:
            rate_row = gold_fx[gold_fx["target_currency"] == base_currency]
            if not rate_row.empty:
                cur_sym = currency_symbol(base_currency)
                st.success(
                    f"🔄 FX rate applied: 1 USD = {cur_sym}{float(rate_row.iloc[0]['rate']):.4f} {base_currency} "
                    f"(source: Frankfurter · {rate_row.iloc[0]['rate_date']})"
                )

with tab_fx:
    if gold_fx.empty:
        st.warning("No FX data loaded.")
    else:
        cur_sym = currency_symbol(base_currency)  # changes with selector
        st.markdown(f"### Exchange Rates — Base: **{cur_sym} {base_currency}**")
        top20 = gold_fx.head(20)
        col_tbl, col_chart = st.columns([2, 3])
        with col_tbl:
            st.dataframe(
                gold_fx.rename(columns={
                    "target_currency":"Currency","rate":"Rate","rate_date":"Date"
                }),
                use_container_width=True, hide_index=True,
            )
        with col_chart:
            fig = px.bar(
                top20, x="target_currency", y="rate",
                color="rate", title=f"Top 20 Rates vs {base_currency}",
                labels={"target_currency":"Currency","rate":"Rate"},
                color_continuous_scale="Purples",
            )
            fig.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)

with tab_wb:
    if gold_wb.empty:
        st.warning("No World Bank data loaded.")
    else:
        st.markdown(f"### {selected_country.get('name', country_id)} — Key Indicators")

        # Gold KPIs
        for _, row_wb in gold_wb.iterrows():
            ind  = row_wb.get("indicator_name","")
            val  = row_wb.get("latest_value")
            yr   = int(row_wb.get("latest_year") or 0)
            if val is not None:
                if "GDP" in ind and "capita" not in ind.lower():
                    disp = f"${val/1e12:.2f}T"
                elif "capita" in ind.lower():
                    disp = f"${val:,.0f}"
                elif "Population" in ind:
                    disp = f"{val/1e6:.1f}M"
                else:
                    disp = f"{val:.2f}%"
                st.metric(f"📌 {ind} ({yr})", disp)

        st.markdown("---")

        # Time-series charts per indicator
        if not silver_wb.empty:
            st.markdown("#### Historical Trends")
            for indicator_name, grp in silver_wb.groupby("indicator_name"):
                grp_sorted = grp.sort_values("year")
                fig = px.line(
                    grp_sorted, x="year", y="value",
                    title=indicator_name,
                    labels={"year":"Year","value":"Value"},
                    markers=True,
                    color_discrete_sequence=["#7C3AED"],
                )
                fig.update_layout(**PLOTLY_LAYOUT, height=280)
                st.plotly_chart(fig, use_container_width=True)
