import sys
import pathlib
import duckdb
import pandas as pd
from pathlib import Path

# Ensure project root is importable when running script directly
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from src.config import (
    AI_TRAFFIC_CSV,
    BROWSER_CSV,
    DB_PATH,
    EVENTS_CSV,
    GOOGLE_TRENDS_OUTPUT,
    RAW_DIR,
    SEARCH_ENGINE_CSV,
)
from src.utils.helpers import ensure_directory


def load_csv_to_table(conn: duckdb.DuckDBPyConnection, csv_path: Path, table_name: str) -> None:
    if not csv_path.exists():
        print(f"Warning: CSV not found for {table_name}: {csv_path}")
        return
    df = pd.read_csv(csv_path, parse_dates=[0])
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.register("temp_df", df)
    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM temp_df")
    conn.unregister("temp_df")
    print(f"Loaded {csv_path.name} into {table_name}")


def safe_normalize_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.to_period("M").dt.to_timestamp()


def create_processed_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "CREATE OR REPLACE TABLE dim_date AS "
        "SELECT DISTINCT date AS date, EXTRACT(year FROM date) AS year, "
        "EXTRACT(month FROM date) AS month, EXTRACT(quarter FROM date) AS quarter, "
        "CASE WHEN EXTRACT(month FROM date)=1 THEN 'January' WHEN EXTRACT(month FROM date)=2 THEN 'February' "
        "WHEN EXTRACT(month FROM date)=3 THEN 'March' WHEN EXTRACT(month FROM date)=4 THEN 'April' "
        "WHEN EXTRACT(month FROM date)=5 THEN 'May' WHEN EXTRACT(month FROM date)=6 THEN 'June' "
        "WHEN EXTRACT(month FROM date)=7 THEN 'July' WHEN EXTRACT(month FROM date)=8 THEN 'August' "
        "WHEN EXTRACT(month FROM date)=9 THEN 'September' WHEN EXTRACT(month FROM date)=10 THEN 'October' "
        "WHEN EXTRACT(month FROM date)=11 THEN 'November' ELSE 'December' END AS month_name "
        "FROM (SELECT DISTINCT date FROM raw_google_trends)"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE dim_region AS SELECT DISTINCT region, region AS region_group FROM (SELECT region FROM raw_google_trends)"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE dim_platform AS "
        "SELECT DISTINCT platform, category FROM (SELECT platform, category FROM raw_search_engine_share UNION ALL SELECT platform, category FROM raw_browser_share)"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE fact_google_trends AS "
        "SELECT date, region, keyword, interest AS normalized_interest_index, "
        "(interest - LAG(interest) OVER (PARTITION BY region, keyword ORDER BY date)) AS month_over_month_growth, "
        "(interest - LAG(interest, 12) OVER (PARTITION BY region, keyword ORDER BY date)) AS year_over_year_growth "
        "FROM raw_google_trends"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE fact_search_engine_share AS "
        "SELECT date, region, platform, category, value_percent AS market_share_percent, "
        "(value_percent - LAG(value_percent) OVER (PARTITION BY region, platform ORDER BY date)) AS month_over_month_growth, "
        "(value_percent - LAG(value_percent, 12) OVER (PARTITION BY region, platform ORDER BY date)) AS year_over_year_growth "
        "FROM raw_search_engine_share"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE fact_browser_share AS "
        "SELECT date, region, platform, category, value_percent AS market_share_percent, "
        "(value_percent - LAG(value_percent) OVER (PARTITION BY region, platform ORDER BY date)) AS month_over_month_growth, "
        "(value_percent - LAG(value_percent, 12) OVER (PARTITION BY region, platform ORDER BY date)) AS year_over_year_growth "
        "FROM raw_browser_share"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE fact_ai_tool_traffic AS "
        "SELECT date, region, ai_tool, traffic_share_percent, visits, "
        "(traffic_share_percent - LAG(traffic_share_percent) OVER (PARTITION BY region, ai_tool ORDER BY date)) AS month_over_month_growth, "
        "(traffic_share_percent - LAG(traffic_share_percent, 12) OVER (PARTITION BY region, ai_tool ORDER BY date)) AS year_over_year_growth "
        "FROM raw_ai_tool_traffic"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE fact_events AS SELECT * FROM raw_events"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE mart_ai_search_behavior_monthly AS "
        "SELECT date, region, 'search_engine' AS category, platform, market_share_percent AS metric_value, 'market_share_percent' AS metric_type "
        "FROM fact_search_engine_share "
        "UNION ALL "
        "SELECT date, region, 'browser' AS category, platform, market_share_percent AS metric_value, 'market_share_percent' AS metric_type "
        "FROM fact_browser_share "
        "UNION ALL "
        "SELECT date, region, 'ai_tool' AS category, ai_tool AS platform, traffic_share_percent AS metric_value, 'traffic_share_percent' AS metric_type "
        "FROM fact_ai_tool_traffic"
    )
    print("Processed tables created in DuckDB.")


def main() -> None:
    ensure_directory(Path(DB_PATH).parent)
    conn = duckdb.connect(database=str(DB_PATH), read_only=False)
    try:
        print(f"Loading demo data into database at {DB_PATH}")
        load_csv_to_table(conn, GOOGLE_TRENDS_OUTPUT, "raw_google_trends")
        load_csv_to_table(conn, SEARCH_ENGINE_CSV, "raw_search_engine_share")
        load_csv_to_table(conn, BROWSER_CSV, "raw_browser_share")
        load_csv_to_table(conn, AI_TRAFFIC_CSV, "raw_ai_tool_traffic")
        load_csv_to_table(conn, EVENTS_CSV, "raw_events")
        create_processed_tables(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
