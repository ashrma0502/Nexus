# app.py — CityPulse: Weather, Air Quality, Earthquakes
# Uses browser geolocation (via streamlit-js-eval) as default when no city is typed.
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_js_eval import get_geolocation

import domains.city_pulse as cp
from core.theme import (
    PLOTLY_LAYOUT, aq_icon, badges, inject_css,
    page_header, refresh_bar, weather_emoji,
)

st.set_page_config(
    page_title="CityPulse — Nexus",
    page_icon="🌆", layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
page_header("🌆", "CityPulse", "Weather · Air Quality · Earthquakes — driven by city search")
badges("Open-Meteo", "USGS", "Nominatim")

st.markdown("#### 🔍 Search for a City")
city_query = st.text_input(
    "Type a city name",
    placeholder="e.g. London, Tokyo, New York…",
    label_visibility="collapsed",
    key="city_search_input",
)

# ── City resolution ────────────────────────────────────────────────────────────
# Priority: typed search > browser geolocation > prompt to type
city: dict | None = None
using_device_location = False

if city_query and len(city_query.strip()) >= 2:
    # User typed a search query — run geocoding
    with st.spinner("Searching cities…"):
        results = cp.search_cities(city_query)
    if not results:
        st.warning("No cities matched your query. Try a different name.")
        st.stop()
    city_options = {r["display"]: r for r in results}
    selected_display = st.selectbox(
        "Select a city from results",
        options=list(city_options.keys()),
        key="city_selector",
    )
    city = city_options[selected_display]
else:
    # No search query — try browser geolocation
    geo = get_geolocation()
    if geo and isinstance(geo, dict) and geo.get("coords"):
        coords = geo["coords"]
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        if lat is not None and lon is not None:
            with st.spinner("Detecting your location…"):
                city = cp.reverse_geocode_coords(float(lat), float(lon))
            if city:
                using_device_location = True
                st.markdown(
                    f'<div class="nexus-status">📍 Showing data for your device location: '
                    f'<b>{city["display"]}</b> — search above to change city</div>',
                    unsafe_allow_html=True,
                )
    if city is None:
        # Geolocation not yet available or denied — show friendly prompt
        st.info(
            "🌍 **Allow location access** in your browser to auto-load your city, "
            "or type a city name above to search manually.",
            icon="📍",
        )
        st.stop()

# ── Fetch + load data ──────────────────────────────────────────────────────────
city_key = city["key"]

last_time = cp.last_fetched(city_key)
force = refresh_bar(last_time, "citypulse")

with st.spinner(f"Fetching data for {city['name']}…"):
    cp.fetch_city(city, force=force)

weather_df = cp.get_silver_weather(city_key)
gold_wx    = cp.get_gold_weather(city_key)
aq_df      = cp.get_gold_air_quality(city_key)
eq_df      = cp.get_silver_earthquakes(city_key)
gold_eq    = cp.get_gold_earthquakes(city_key)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_wx, tab_aq, tab_eq = st.tabs(["☀️ Weather", "🌫️ Air Quality", "🌍 Earthquakes"])

with tab_wx:
    if weather_df.empty:
        st.warning("No weather data fetched yet.")
    else:
        row = weather_df.iloc[0]
        st.markdown(f"### {city['name']}, {city['country']}")
        try:
            code = int(row.get('weather_code') or 0)
        except (TypeError, ValueError):
            code = 0
        wx_icon = weather_emoji(code)
        wx_desc = str(row.get('wx_desc', '—'))

        # Single-line HTML avoids Streamlit's markdown parser misreading </div> as text
        def wx_card(col, label, value, sub=None):
            sub_html = (f'<div style="margin-top:0.3rem;font-size:0.78rem;color:#4ade80;">'
                        f'&#8593; {sub}</div>') if sub else ''
            col.markdown(
                f'<div style="background:linear-gradient(135deg,#1A1A2E 0%,#16213E 100%);'
                f'border:1px solid rgba(124,58,237,0.30);border-radius:12px;'
                f'padding:1rem 1.25rem;min-height:100px;">'
                f'<div style="font-size:0.84rem;color:#94A3B8;font-weight:400;'
                f'margin-bottom:0.35rem;">{label}</div>'
                f'<div style="font-size:1.4rem;font-weight:700;color:#FAFAFA;'
                f'white-space:normal;word-break:break-word;line-height:1.3;">{value}</div>'
                f'{sub_html}</div>',
                unsafe_allow_html=True,
            )

        c1, c2, c3, c4, c5 = st.columns(5)
        wx_card(c1, "🌡️ Temperature", f"{row.get('temp_c','—')} °C",
                sub=f"Feels {row.get('feels_like_c','—')} °C")
        wx_card(c2, "💧 Humidity",   f"{row.get('humidity','—')} %")
        wx_card(c3, "💨 Wind Speed", f"{row.get('wind_kph','—')} km/h")
        wx_card(c4, "🌧️ Precip.",   f"{row.get('precip_mm','—')} mm")
        wx_card(c5, f"{wx_icon} Condition", wx_desc)

        if not gold_wx.empty:
            gw = gold_wx.iloc[0]
            st.markdown("#### 7-Day Forecast Summary")
            gc1, gc2, gc3 = st.columns(3)
            wx_card(gc1, "🔆 Max Temp (7d)",    f"{gw.get('max_temp_7d','—')} °C")
            wx_card(gc2, "❄️ Min Temp (7d)",    f"{gw.get('min_temp_7d','—')} °C")
            wx_card(gc3, "☔ Total Precip (7d)", f"{round(float(gw.get('total_precip_7d',0) or 0),1)} mm")

        st.markdown("#### 📍 Location")
        map_df = weather_df[["lat","lon"]].rename(columns={"lat":"latitude","lon":"longitude"})
        st.map(map_df, zoom=8)

with tab_aq:
    if aq_df.empty:
        st.warning("No air quality data for this location. OpenAQ coverage may be limited.")
    else:
        st.markdown("### Air Quality (Open-Meteo · current hourly values)")
        c1, c2 = st.columns(2)
        with c1:
            aq_disp = aq_df[["parameter","avg_value","max_value","location_count"]].copy()
            aq_disp["avg_value"]  = aq_disp["avg_value"].fillna(0).round(2)
            aq_disp["max_value"]  = aq_disp["max_value"].fillna(0).round(2)
            aq_disp["parameter"]  = aq_disp["parameter"].fillna("unknown").apply(
                lambda p: f"{aq_icon(p)} {p}"
            )
            st.dataframe(
                aq_disp.rename(
                    columns={"parameter":"Parameter","avg_value":"Avg","max_value":"Max",
                             "location_count":"Stations"}
                ),
                use_container_width=True, hide_index=True,
            )
        with c2:
            plot_df = aq_df.copy()
            plot_df["avg_value"] = plot_df["avg_value"].fillna(0)
            fig = px.bar(
                plot_df, x="parameter", y="avg_value",
                color="parameter", title="Average Pollutant Levels",
                labels={"parameter":"Parameter","avg_value":"Avg Value"},
                color_discrete_sequence=PLOTLY_LAYOUT["colorway"],
            )
            fig.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)

with tab_eq:
    if not gold_eq.empty:
        gq = gold_eq.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("🔢 Events (30d)",   int(gq.get("eq_count",0) or 0))
        c2.metric("📊 Avg Magnitude",  f"{round(float(gq.get('avg_magnitude',0) or 0), 2)}")
        c3.metric("⚠️ Max Magnitude", f"{round(float(gq.get('max_magnitude',0) or 0), 2)}")

    if eq_df.empty:
        st.info("No earthquakes ≥ M1.5 within 500 km in the last 30 days.")
    else:
        st.markdown("### Recent Earthquakes (last 30 days, ≥ M1.5, within 500 km)")
        st.dataframe(
            eq_df.rename(columns={
                "eq_time":"Time","magnitude":"Mag","place":"Location",
                "depth_km":"Depth (km)","lat":"Lat","lon":"Lon",
            }),
            use_container_width=True, hide_index=True,
        )

        if "lat" in eq_df.columns and "lon" in eq_df.columns:
            map_data = eq_df.dropna(subset=["lat","lon"])
            if not map_data.empty:
                fig = px.scatter_map(
                    map_data, lat="lat", lon="lon", 
                    size="magnitude", color="magnitude", 
                    hover_name="place", hover_data={ "magnitude": True, "depth_km": True }, 
                    color_continuous_scale="Plasma", 
                    map_style="carto-darkmatter", 
                    title="Earthquake Map", size_max=20, zoom=5) 
                fig.update_layout( **PLOTLY_LAYOUT, height=420 ) 
                st.plotly_chart( fig, use_container_width=True ) 
