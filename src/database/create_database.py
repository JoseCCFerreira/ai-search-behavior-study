import sys
import pathlib
import duckdb
from pathlib import Path

# Ensure project root is importable when running script directly
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from src.config import DB_PATH
from src.utils.helpers import ensure_directory


def create_database() -> None:
    ensure_directory(Path(DB_PATH).parent)
    conn = duckdb.connect(database=str(DB_PATH), read_only=False)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS raw_google_trends (date DATE, region VARCHAR, keyword VARCHAR, interest DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS raw_search_engine_share (date DATE, region VARCHAR, platform VARCHAR, category VARCHAR, value_percent DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS raw_browser_share (date DATE, region VARCHAR, platform VARCHAR, category VARCHAR, value_percent DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS raw_ai_tool_traffic (date DATE, region VARCHAR, ai_tool VARCHAR, visits BIGINT, traffic_share_percent DOUBLE, avg_visit_duration DOUBLE, pages_per_visit DOUBLE, bounce_rate DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS raw_events (event_date DATE, event_name VARCHAR, event_type VARCHAR, affected_platform VARCHAR, description VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS dim_date (date DATE PRIMARY KEY, year INTEGER, month INTEGER, quarter INTEGER, month_name VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS dim_region (region VARCHAR PRIMARY KEY, region_group VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS dim_platform (platform VARCHAR PRIMARY KEY, category VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fact_google_trends (date DATE, region VARCHAR, keyword VARCHAR, normalized_interest_index DOUBLE, month_over_month_growth DOUBLE, year_over_year_growth DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fact_search_engine_share (date DATE, region VARCHAR, platform VARCHAR, market_share_percent DOUBLE, month_over_month_growth DOUBLE, year_over_year_growth DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fact_browser_share (date DATE, region VARCHAR, platform VARCHAR, market_share_percent DOUBLE, month_over_month_growth DOUBLE, year_over_year_growth DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fact_ai_tool_traffic (date DATE, region VARCHAR, ai_tool VARCHAR, traffic_share_percent DOUBLE, visits BIGINT, month_over_month_growth DOUBLE, year_over_year_growth DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fact_events (event_date DATE, event_name VARCHAR, event_type VARCHAR, affected_platform VARCHAR, description VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS mart_ai_search_behavior_monthly (date DATE, region VARCHAR, category VARCHAR, platform VARCHAR, metric_type VARCHAR, metric_value DOUBLE)"
        )
        print(f"Created DuckDB database at {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    create_database()
