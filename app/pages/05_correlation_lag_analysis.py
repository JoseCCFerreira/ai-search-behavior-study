import streamlit as st
import pandas as pd
import plotly.express as px
from src.database.queries import read_table


def run() -> None:
    st.title("Correlation & Lag Analysis")
    st.markdown("Compare correlations and visualize lagged relationships between variables.")

    trends = read_table("fact_google_trends")
    share = read_table("fact_search_engine_share")
    if trends.empty or share.empty:
        st.warning("Required tables are missing or empty. Load demo data first.")
        return

    keywords = ["ChatGPT", "Gemini AI", "Perplexity AI"]
    if not trends["keyword"].isin(keywords).any():
        st.warning("Demo data contains alternate keyword naming. Use the Trend Analysis page for current charts.")
        return

    correlation = share.pivot(index="date", columns="platform", values="market_share_percent").corr(method="pearson")
    fig = px.imshow(correlation, title="Search Engine Market Share Correlation")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Placeholder lag analysis")
    st.write("Lag analysis will compare time-shifted trends between AI interest and search engine share.")

    st.dataframe(correlation)
