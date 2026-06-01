import streamlit as st
from app.pages import (
    page_01_overview,
    page_02_data_quality,
    page_03_current_distribution,
    page_04_trend_analysis,
    page_05_correlation_lag_analysis,
    page_06_clustering,
    page_07_forecasting,
    page_08_methodology,
)

PAGES = {
    "Overview": page_01_overview,
    "Data Quality": page_02_data_quality,
    "Current Distribution": page_03_current_distribution,
    "Trend Analysis": page_04_trend_analysis,
    "Correlation & Lag Analysis": page_05_correlation_lag_analysis,
    "Clustering": page_06_clustering,
    "Forecasting": page_07_forecasting,
    "Methodology": page_08_methodology,
}


def main() -> None:
    st.set_page_config(
        page_title="AI Search Behavior Study",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.sidebar.title("AI Search Behavior Study")
    selection = st.sidebar.radio("Choose a page", list(PAGES.keys()))
    page = PAGES[selection]
    page.run()


if __name__ == "__main__":
    main()
