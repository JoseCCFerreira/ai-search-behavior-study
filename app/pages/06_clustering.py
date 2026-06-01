import streamlit as st
import plotly.express as px
from src.database.queries import read_table


def run() -> None:
    st.title("Clustering")
    st.markdown("Use clustering results to identify similar countries, platforms, or periods.")
    st.write("This page includes the clustering framework and feature exploration placeholders.")
    st.info("Clustering models have not yet been trained in the demo pipeline. Add model scripts in src/ml for advanced analysis.")
