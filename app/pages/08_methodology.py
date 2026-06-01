import streamlit as st
from src.config import HYPOTHESIS


def run() -> None:
    st.title("Methodology")
    st.markdown("This page explains the study methodology, data sources, assumptions, and analysis approach.")
    st.subheader("Hypotheses")
    for key, value in HYPOTHESIS.items():
        st.markdown(f"**{key}**: {value}")
    st.markdown("### Data sources")
    st.write(
        "Google Trends, StatCounter GlobalStats, Similarweb-style AI traffic data, manual events, and synthetic demo data for initial development."
    )
    st.markdown("### Analysis approach")
    st.write(
        "The study uses a DuckDB analytical mart, descriptive analytics, correlation and lag analysis, clustering frameworks, and forecasting templates."
    )
