"""
Database Module

DuckDB database management for Strava Performance Coach.
"""

from src.database.db_connection import (
    DatabaseConnection,
    DatabaseConnectionPool,
    get_connection,
    get_direct_connection,
    get_connection_context,
    close_connection_pool
)
from src.database.create_database import (
    DatabaseInitializer,
    initialize_database
)

__all__ = [
    'DatabaseConnection',
    'DatabaseConnectionPool',
    'get_connection',
    'get_direct_connection',
    'get_connection_context',
    'close_connection_pool',
    'DatabaseInitializer',
    'initialize_database',
]
