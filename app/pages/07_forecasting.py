import streamlit as st
from src.database.queries import read_table


def run() -> None:
    st.title("Forecasting")
    st.markdown("Estimate upcoming behavior using baseline and model-driven forecasts.")
    st.info("Forecasting is configured as a framework placeholder. Add models in src/ml/forecasting.py for full production use.")
    mart = read_table("mart_ai_search_behavior_monthly")
    if mart.empty:
        st.warning("No analytical mart data available yet.")
        return

    st.write("Available categories:")
    st.write(sorted(mart["category"].unique().tolist()))
