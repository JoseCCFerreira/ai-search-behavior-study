import streamlit as st
import plotly.express as px
from src.database.queries import read_table


def run() -> None:
    st.title("Trend Analysis")
    st.markdown("Explore monthly trends for search engines, browsers and AI tools.")
    mart = read_table("mart_ai_search_behavior_monthly")
    if mart.empty:
        st.warning("The analytical mart is empty. Run the database load script.")
        return

    region = st.selectbox("Region", sorted(mart["region"].unique().tolist()))
    category = st.selectbox("Category", sorted(mart["category"].unique().tolist()))
    filtered = mart[(mart["region"] == region) & (mart["category"] == category)]

    fig = px.line(filtered, x="date", y="metric_value", color="platform", title=f"Trend by {category} in {region}")
    st.plotly_chart(fig, use_container_width=True)
