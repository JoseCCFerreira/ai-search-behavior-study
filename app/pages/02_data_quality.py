import streamlit as st
import pandas as pd
from src.database.queries import read_table

TABLES = [
    "raw_google_trends",
    "raw_search_engine_share",
    "raw_browser_share",
    "raw_ai_tool_traffic",
    "raw_events",
    "fact_google_trends",
    "fact_search_engine_share",
    "fact_browser_share",
    "fact_ai_tool_traffic",
]


def summarize_table(name: str) -> dict[str, object]:
    df = read_table(name)
    missing = df.isna().sum().sum()
    duplicates = df.duplicated().sum()
    return {
        "table": name,
        "rows": len(df),
        "columns": len(df.columns),
        "missing_values": int(missing),
        "duplicates": int(duplicates),
    }


def run() -> None:
    st.title("Data Quality")
    st.markdown("Review row counts, missing values, duplicates and temporal coverage for each source.")
    summary = [summarize_table(table) for table in TABLES]
    st.table(pd.DataFrame(summary))

    st.markdown("### Raw events structure")
    events = read_table("raw_events")
    st.dataframe(events.head(10))
