# pages/2_RetailIQ.py — Retail product data and search
import plotly.express as px
import streamlit as st

import domains.retail_iq as riq
from core.theme import PLOTLY_LAYOUT, badges, category_icon, inject_css, page_header, refresh_bar

st.set_page_config(
    page_title="RetailIQ — Nexus",
    page_icon="🛒", layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()
page_header("🛒", "RetailIQ", "FakeStore Products · OpenFoodFacts Nutrition — driven by category & search")
badges("FakeStore API", "OpenFoodFacts")

with st.spinner("Loading product categories…"):
    categories = riq.fetch_categories()

if not categories:
    st.error("Could not load FakeStore categories. Check your connection.")
    st.stop()

with st.sidebar:
    st.markdown("### 🎛️ Controls")
    selected_category = st.selectbox(
        "🏷️ Product Category",
        options=categories,
        key="category_selector",
    )
    st.markdown("---")
    food_query = st.text_input(
        "🥗 Food / Nutrition Search",
        placeholder="e.g. chocolate, oat milk, quinoa…",
        key="food_search_input",
    )

last_time = riq.last_fetched(selected_category, food_query)
force = refresh_bar(last_time, "retailiq")

with st.spinner(f"Fetching data for '{selected_category}'…"):
    riq.fetch_products(selected_category, force=force)

if food_query and len(food_query.strip()) >= 2:
    with st.spinner(f"Searching food products for '{food_query}'…"):
        riq.fetch_food_search(food_query, force=force)

silver_products = riq.get_silver_products(selected_category)
gold_products   = riq.get_gold_products(selected_category)
silver_food     = riq.get_silver_food(food_query) if food_query and len(food_query.strip()) >= 2 else None
gold_food       = riq.get_gold_food(food_query)   if food_query and len(food_query.strip()) >= 2 else None

cat_icon = category_icon(selected_category)   # ← driven by current category
tab_prod, tab_food = st.tabs([f"{cat_icon} Products", "🥗 Nutrition"])

with tab_prod:
    # Header icon + title both driven by selected_category
    st.markdown(f"### {cat_icon} Category: **{selected_category.title()}**")

    if not gold_products.empty:
        gp = gold_products.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📦 Products",   int(gp.get("product_count",0)))
        c2.metric("💰 Avg Price",  f"${float(gp.get('avg_price',0) or 0):.2f}")
        c3.metric("⭐ Avg Rating", f"{float(gp.get('avg_rating',0) or 0):.2f}")
        c4.metric("💵 Price Range",
                  f"${float(gp.get('min_price',0) or 0):.2f} – ${float(gp.get('max_price',0) or 0):.2f}")

    if silver_products.empty:
        st.warning("No products loaded for this category.")
    else:
        col_tbl, col_chart = st.columns([3, 2])
        with col_tbl:
            st.markdown("#### Product Listings")
            disp = silver_products[["title","price","rating","rating_count"]].rename(
                columns={"title":"Product","price":"Price ($)",
                         "rating":"Rating","rating_count":"Reviews"}
            )
            st.dataframe(disp, use_container_width=True, hide_index=True, height=360)

        with col_chart:
            # Price distribution
            fig = px.histogram(
                silver_products, x="price", nbins=10,
                title="Price Distribution",
                labels={"price":"Price ($)","count":"Count"},
                color_discrete_sequence=["#7C3AED"],
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=200)
            st.plotly_chart(fig, use_container_width=True)

            # Rating scatter
            if "rating" in silver_products.columns and "price" in silver_products.columns:
                fig2 = px.scatter(
                    silver_products, x="price", y="rating",
                    size="rating_count", color="rating",
                    hover_name="title",
                    title="Rating vs Price",
                    labels={"price":"Price ($)","rating":"Rating"},
                    color_continuous_scale="Purples",
                )
                fig2.update_layout(**PLOTLY_LAYOUT, height=260)
                st.plotly_chart(fig2, use_container_width=True)

with tab_food:
    if not food_query or len(food_query.strip()) < 2:
        st.info("Enter a food / ingredient in the sidebar search box to explore nutrition data from OpenFoodFacts.")
    elif silver_food is None or silver_food.empty:
        st.warning(f"No food products found for '{food_query}'.")
    else:
        st.markdown(f"### Nutrition Results: **{food_query}**")

        if gold_food is not None and not gold_food.empty:
            gf = gold_food.iloc[0]
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("📋 Products",     int(gf.get("product_count",0) or 0))
            c2.metric("🔥 Avg kcal/100g", f"{float(gf.get('avg_energy_kcal',0) or 0):.0f}")
            c3.metric("💪 Avg Protein",  f"{float(gf.get('avg_proteins',0) or 0):.1f}g")
            c4.metric("🧈 Avg Fat",      f"{float(gf.get('avg_fat',0) or 0):.1f}g")
            c5.metric("🌾 Avg Carbs",    f"{float(gf.get('avg_carbs',0) or 0):.1f}g")

        col_t, col_c = st.columns([3, 2])
        with col_t:
            disp = silver_food[["product_name","brands","energy_kcal",
                                "proteins","fat","carbohydrates",
                                "nutriscore","nova_group"]].rename(columns={
                "product_name":"Product","brands":"Brand",
                "energy_kcal":"kcal/100g","proteins":"Protein(g)",
                "fat":"Fat(g)","carbohydrates":"Carbs(g)",
                "nutriscore":"Nutriscore","nova_group":"NOVA",
            })
            st.dataframe(disp, use_container_width=True, hide_index=True, height=380)

        with col_c:
            macro_df = silver_food[["product_name","proteins","fat","carbohydrates"]].dropna()
            if not macro_df.empty:
                fig3 = px.bar(
                    macro_df.head(10), x="product_name",
                    y=["proteins","fat","carbohydrates"],
                    title="Macros per Product (top 10)",
                    labels={"value":"g/100g","product_name":"Product",
                            "variable":"Macro"},
                    barmode="stack",
                    color_discrete_sequence=["#7C3AED","#FBBF24","#34D399"],
                )
                fig3.update_layout(**PLOTLY_LAYOUT, height=360,
                                   xaxis_tickangle=-30)
                st.plotly_chart(fig3, use_container_width=True)
