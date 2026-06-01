import streamlit as st
import plotly.express as px
from src.database.queries import read_table


def run() -> None:
    st.title("Current Distribution")
    st.markdown("Compare the latest available shares for search engines, browsers and AI tools.")
    browser = read_table("fact_browser_share")
    search = read_table("fact_search_engine_share")
    ai = read_table("fact_ai_tool_traffic")

    if browser.empty or search.empty or ai.empty:
        st.warning("Processed data not yet available. Load demo data first.")
        return

    latest = browser[browser["date"] == browser["date"].max()]
    fig_browser = px.bar(latest, x="platform", y="market_share_percent", color="platform", title="Browser Market Share")
    st.plotly_chart(fig_browser, use_container_width=True)

    latest_search = search[search["date"] == search["date"].max()]
    fig_search = px.bar(latest_search, x="platform", y="market_share_percent", color="platform", title="Search Engine Market Share")
    st.plotly_chart(fig_search, use_container_width=True)

    latest_ai = ai[ai["date"] == ai["date"].max()]
    fig_ai = px.bar(latest_ai, x="ai_tool", y="traffic_share_percent", color="ai_tool", title="AI Tool Traffic Share")
    st.plotly_chart(fig_ai, use_container_width=True)
