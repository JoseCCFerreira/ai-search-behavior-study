import duckdb
from pathlib import Path
from typing import Any

from src.config import DB_PATH


def connect_db() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(database=str(DB_PATH), read_only=False)


def read_table(table_name: str) -> Any:
    conn = connect_db()
    try:
        return conn.execute(f"SELECT * FROM {table_name}").df()
    finally:
        conn.close()


def get_mart_data():
    conn = connect_db()
    try:
        return conn.execute("SELECT * FROM mart_ai_search_behavior_monthly").df()
    finally:
        conn.close()
