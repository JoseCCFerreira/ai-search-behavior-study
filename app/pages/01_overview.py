import streamlit as st
import pandas as pd
import plotly.express as px
from src.database.queries import get_mart_data, read_table


def run() -> None:
    st.title("Overview")
    st.markdown(
        "This page offers a high-level summary of search behavior, browser usage, and AI adoption trends."
    )

    mart = get_mart_data()
    if mart.empty:
        st.warning("No analytical data found. Run data ingestion and database loading scripts first.")
        return

    latest_date = mart["date"].max()
    active_regions = mart["region"].nunique()
    st.metric("Latest available month", str(latest_date.date()))
    st.metric("Regions available", active_regions)

    trend = mart[mart["metric_type"] == "metric_value"] if "metric_type" in mart.columns else mart
    if not trend.empty:
        chart = px.line(
            trend.sort_values("date"),
            x="date",
            y="metric_value",
            color="category",
            title="Monthly Metric Trends by Category",
        )
        st.plotly_chart(chart, use_container_width=True)

    st.markdown("### Demo insights")
    st.write(
        "The demo dataset includes synthetic trends for search engines, browsers, and AI tool traffic. "
        "Use the visualization pages to explore the relationships and data quality."
    )

    if st.checkbox("Show raw event sample"):
        events = read_table("fact_events")
        st.dataframe(events.head(10))
