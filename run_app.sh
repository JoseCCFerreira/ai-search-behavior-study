#!/bin/bash

echo "Creating demo data..."
python src/data_ingestion/create_demo_data.py

echo "Creating DuckDB database..."
python src/database/create_database.py

echo "Loading data to DuckDB..."
python src/database/load_to_duckdb.py

echo "Starting Streamlit app..."
streamlit run app/streamlit_app.py
