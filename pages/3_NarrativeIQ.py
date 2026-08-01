# pages/3_NarrativeIQ.py — News, Books, and TV Shows
import plotly.express as px
import streamlit as st

import domains.narrative_iq as niq
from core.theme import PLOTLY_LAYOUT, badges, inject_css, page_header, refresh_bar

st.set_page_config(
    page_title="NarrativeIQ — Nexus",
    page_icon="📰", layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
page_header("📰", "NarrativeIQ", "News · Books · TV Shows — one search, three dimensions")
badges("The Guardian", "OpenLibrary", "TVMaze")

col_search, col_btn = st.columns([5, 1])
with col_search:
    topic = st.text_input(
        "🔍 Search topic",
        placeholder="e.g. artificial intelligence, climate change, space exploration…",
        label_visibility="collapsed",
        key="narrative_topic_input",
    )

if not topic or len(topic.strip()) < 2:
    st.info(
        "📚 Type a topic above to search The Guardian for news, "
        "OpenLibrary for books, and TVMaze for TV shows — all in one query."
    )
    st.stop()

t_key = topic.strip()

last_time = niq.last_fetched(t_key)
force = refresh_bar(last_time, "narrativeiq")

with st.spinner(f"Fetching news, books, and shows for '{t_key}'…"):
    niq.fetch_all(t_key, force=force)

silver_news  = niq.get_silver_news(t_key)
gold_news    = niq.get_gold_news(t_key)
silver_books = niq.get_silver_books(t_key)
gold_books   = niq.get_gold_books(t_key)
silver_shows = niq.get_silver_shows(t_key)
gold_shows   = niq.get_gold_shows(t_key)

st.markdown(f"### Results for: **{t_key}**")
c1, c2, c3 = st.columns(3)
c1.metric("📰 News Articles",  len(silver_news))
c2.metric("📚 Books Found",    len(silver_books))
c3.metric("📺 TV Shows Found", len(silver_shows))

tab_news, tab_books, tab_shows = st.tabs(["📰 News", "📚 Books", "📺 TV Shows"])

with tab_news:
    if silver_news.empty:
        st.warning("No news articles found.")
    else:
        if not gold_news.empty:
            gn = gold_news.iloc[0]
            c1, c2 = st.columns(2)
            c1.metric("📰 Total Articles", int(gn.get("article_count",0)))
            c2.metric("📌 Top Section", str(gn.get("top_section","—")))

        # Section breakdown
        section_counts = silver_news["section"].value_counts().reset_index()
        section_counts.columns = ["section","count"]
        col_tbl, col_chart = st.columns([3, 2])
        with col_tbl:
            for _, art in silver_news.iterrows():
                with st.expander(f"📄 {art['title'][:90]}…" if len(str(art['title'])) > 90 else f"📄 {art['title']}"):
                    st.markdown(f"**Section:** {art.get('section','')}  |  **Published:** {art.get('pub_date','')[:10]}")
                    st.markdown(art.get("trail_text",""))
                    st.markdown(f"[Read full article →]({art.get('web_url','')})")

        with col_chart:
            if not section_counts.empty:
                fig = px.pie(
                    section_counts, names="section", values="count",
                    title="Articles by Section",
                    color_discrete_sequence=PLOTLY_LAYOUT["colorway"],
                )
                fig.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig, use_container_width=True)

with tab_books:
    if silver_books.empty:
        st.warning("No books found.")
    else:
        if not gold_books.empty:
            gb = gold_books.iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("📚 Books Found",    int(gb.get("book_count",0)))
            c2.metric("📅 Avg Pub. Year",  f"{int(gb.get('avg_publish_year',0) or 0)}")
            c3.metric("📖 Max Editions",   int(gb.get("max_editions",0) or 0))

        col_tbl, col_chart = st.columns([3, 2])
        with col_tbl:
            disp = silver_books.rename(columns={
                "title":"Title","author":"Author",
                "first_publish_year":"First Published",
                "edition_count":"Editions",
            })
            st.dataframe(disp, use_container_width=True, hide_index=True, height=380)

        with col_chart:
            plot_df = silver_books.dropna(subset=["first_publish_year","edition_count"])
            if not plot_df.empty:
                fig2 = px.scatter(
                    plot_df, x="first_publish_year", y="edition_count",
                    hover_name="title", color="edition_count",
                    title="Publications Over Time",
                    labels={"first_publish_year":"Year","edition_count":"Editions"},
                    color_continuous_scale="Purples",
                )
                fig2.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig2, use_container_width=True)

            # Timeline histogram
            year_df = silver_books.dropna(subset=["first_publish_year"])
            if not year_df.empty:
                fig3 = px.histogram(
                    year_df, x="first_publish_year", nbins=20,
                    title="Books by Publication Decade",
                    labels={"first_publish_year":"Year","count":"Books"},
                    color_discrete_sequence=["#7C3AED"],
                )
                fig3.update_layout(**PLOTLY_LAYOUT, height=200)
                st.plotly_chart(fig3, use_container_width=True)

with tab_shows:
    if silver_shows.empty:
        st.warning("No TV shows found.")
    else:
        if not gold_shows.empty:
            gs = gold_shows.iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("📺 Shows Found",  int(gs.get("show_count",0)))
            c2.metric("⭐ Avg Rating",   f"{float(gs.get('avg_rating',0) or 0):.1f}")
            c3.metric("🎭 Top Genre",    str(gs.get("top_genre","—")))

        col_tbl, col_chart = st.columns([3, 2])
        with col_tbl:
            disp = silver_shows[["show_name","show_type","language",
                                  "genres","status","rating","premiered"]].rename(columns={
                "show_name":"Show","show_type":"Type","language":"Language",
                "genres":"Genres","status":"Status","rating":"Rating","premiered":"Premiered",
            })
            st.dataframe(disp, use_container_width=True, hide_index=True, height=380)

        with col_chart:
            rating_df = silver_shows.dropna(subset=["rating"])
            if not rating_df.empty:
                fig4 = px.bar(
                    rating_df.sort_values("rating", ascending=False).head(12),
                    x="show_name", y="rating", color="rating",
                    title="Show Ratings (Top 12)",
                    labels={"show_name":"Show","rating":"Rating"},
                    color_continuous_scale="Purples",
                )
                fig4.update_layout(**PLOTLY_LAYOUT, xaxis_tickangle=-30)
                st.plotly_chart(fig4, use_container_width=True)
