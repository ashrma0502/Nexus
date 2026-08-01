# pages/4_EngineeringPulse.py — GitHub Repo Velocity
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import domains.engineering_pulse as ep
from core.theme import PLOTLY_LAYOUT, badges, inject_css, page_header, refresh_bar

st.set_page_config(
    page_title="EngineeringPulse — Nexus",
    page_icon="⚙️", layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
page_header("⚙️", "EngineeringPulse", "GitHub Repo Velocity — search, explore, and analyse repositories")
badges("GitHub REST API")

with st.sidebar:
    st.markdown("### 🎛️ Controls")
    repo_query = st.text_input(
        "🔍 GitHub Repo Search",
        placeholder="e.g. streamlit, pytorch, fastapi…",
        key="repo_search_input",
    )

if not repo_query or len(repo_query.strip()) < 2:
    st.info("Type a search term in the sidebar to explore GitHub repositories.")
    st.stop()

last_time_gh = ep.last_fetched(repo_query)
force_gh = refresh_bar(last_time_gh, "github")

with st.spinner(f"Searching GitHub for '{repo_query}'…"):
    search_df = ep.search_repos(repo_query, force=force_gh)

if search_df.empty:
    st.warning("No repos found. Try a different query.")
    st.stop()

st.markdown(f"### Top Repositories for **{repo_query}**")

col_tbl, col_chart = st.columns([3, 2])
with col_tbl:
    disp = search_df[["repo_full_name","stars","forks","language","description"]].rename(
        columns={"repo_full_name":"Repository","stars":"⭐ Stars",
                 "forks":"🍴 Forks","language":"Language","description":"Description"}
    )
    st.dataframe(disp, use_container_width=True, hide_index=True, height=280)

with col_chart:
    if "stars" in search_df.columns:
        top10 = search_df.head(10)
        fig = px.bar(
            top10, x="stars", y="repo_full_name",
            orientation="h", title="Stars (Top 10)",
            labels={"stars":"⭐ Stars","repo_full_name":"Repository"},
            color="stars", color_continuous_scale="Purples",
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=280, yaxis_autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.markdown("#### 🔬 Repository Deep Dive")
repo_options = search_df["repo_full_name"].tolist()
selected_repo = st.selectbox(
    "Select a repository for details",
    options=repo_options,
    key="repo_detail_selector",
)

with st.spinner(f"Fetching details for {selected_repo}…"):
    ep.fetch_repo(selected_repo, force=force_gh)

gold_gh   = ep.get_gold_github(selected_repo)
silver_gh = ep.get_silver_github(selected_repo)

if not gold_gh.empty:
    g = gold_gh.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⭐ Stars",          f"{int(g.get('stars',0) or 0):,}")
    c2.metric("🍴 Forks",          f"{int(g.get('forks',0) or 0):,}")
    c3.metric("🐛 Open Issues",    f"{int(g.get('open_issues',0) or 0):,}")
    c4.metric("📅 Days Since Push",
              f"{int(g.get('days_since_push',0) or 0)} days"
              if g.get('days_since_push') is not None else "—")

if not silver_gh.empty:
    s = silver_gh.iloc[0]
    st.markdown(f"**Language:** {s.get('language','—')} &nbsp;|&nbsp; "
                f"**Created:** {str(s.get('created_at',''))[:10]} &nbsp;|&nbsp; "
                f"**Last pushed:** {str(s.get('pushed_at',''))[:10]}")
    if s.get("description"):
        st.info(s["description"])
