"""
Database Connection Management

Module for handling DuckDB connections with connection pooling,
error handling, and logging.

Author: Strava Performance Coach
Date: 2026-06-02
"""

import os
import logging
from typing import Optional, Any, List
from contextlib import contextmanager
import duckdb
from pathlib import Path

from config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    DuckDB Connection Manager
    
    Handles connection lifecycle, configuration, and basic operations.
    Thread-safe for read operations, should use separate connections for writes.
    """
    
    def __init__(self, database_path: Optional[str] = None):
        """
        Initialize database connection.
        
        Args:
            database_path: Path to .duckdb file. Defaults to settings.duckdb_path
        """
        self.database_path = database_path or settings.duckdb_path
        self.connection: Optional[duckdb.DuckDBPyConnection] = None
        self._initialize_connection()
    
    def _initialize_connection(self) -> None:
        """Initialize DuckDB connection with settings."""
        try:
            # Ensure directory exists
            db_dir = os.path.dirname(self.database_path)
            if db_dir:
                Path(db_dir).mkdir(parents=True, exist_ok=True)
            
            # Create connection
            self.connection = duckdb.connect(self.database_path)
            
            # Set configuration
            self.connection.execute("PRAGMA threads = 4")  # Use 4 CPU cores
            self.connection.execute("PRAGMA memory_limit = '2GB'")
            
            logger.info(f"Database connection initialized: {self.database_path}")
        
        except Exception as e:
            logger.error(f"Failed to initialize database connection: {e}")
            raise
    
    def execute(self, query: str, parameters: Optional[tuple] = None) -> duckdb.DuckDBPyRelation:
        """
        Execute SQL query.
        
        Args:
            query: SQL query string
            parameters: Optional parameters for parameterized queries
        
        Returns:
            DuckDB relation object
        
        Raises:
            RuntimeError: If connection is not initialized
            Exception: If query execution fails
        """
        if self.connection is None:
            raise RuntimeError("Database connection not initialized")
        
        try:
            if parameters:
                return self.connection.execute(query, parameters)
            else:
                return self.connection.execute(query)
        
        except Exception as e:
            logger.error(f"Query execution failed: {e}\nQuery: {query}")
            raise
    
    def fetch_all(self, query: str, parameters: Optional[tuple] = None) -> List[tuple]:
        """
        Execute query and fetch all results.
        
        Args:
            query: SQL query string
            parameters: Optional parameters
        
        Returns:
            List of result tuples
        """
        result = self.execute(query, parameters)
        return result.fetchall()
    
    def fetch_one(self, query: str, parameters: Optional[tuple] = None) -> Optional[tuple]:
        """
        Execute query and fetch single result.
        
        Args:
            query: SQL query string
            parameters: Optional parameters
        
        Returns:
            Single result tuple or None if not found
        """
        result = self.execute(query, parameters)
        return result.fetchone()
    
    def fetch_df(self, query: str, parameters: Optional[tuple] = None):
        """
        Execute query and return as pandas DataFrame.
        
        Args:
            query: SQL query string
            parameters: Optional parameters
        
        Returns:
            pandas DataFrame
        """
        result = self.execute(query, parameters)
        return result.df()
    
    def insert_records(self, table: str, records: List[dict]) -> int:
        """
        Insert multiple records into table.
        
        Args:
            table: Table name
            records: List of dictionaries with column names as keys
        
        Returns:
            Number of records inserted
        
        Raises:
            ValueError: If records list is empty
            Exception: If insert fails
        """
        if not records:
            raise ValueError("No records to insert")
        
        try:
            # Convert list of dicts to table
            import pandas as pd
            df = pd.DataFrame(records)
            
            columns = list(df.columns)
            quoted_columns = ", ".join(f'"{column}"' for column in columns)

            # Insert only provided columns so table defaults/generated columns can work.
            self.connection.execute(
                f"INSERT INTO {table} ({quoted_columns}) SELECT {quoted_columns} FROM df"
            )
            
            num_inserted = len(records)
            logger.info(f"Inserted {num_inserted} records into {table}")
            return num_inserted
        
        except Exception as e:
            logger.error(f"Insert failed for table {table}: {e}")
            raise
    
    def table_exists(self, table_name: str) -> bool:
        """
        Check if table exists in database.
        
        Args:
            table_name: Name of table to check
        
        Returns:
            True if table exists, False otherwise
        """
        query = """
            SELECT COUNT(*) as cnt
            FROM information_schema.tables
            WHERE table_name = ?
        """
        result = self.fetch_one(query, (table_name,))
        return result and result[0] > 0
    
    def get_table_info(self, table_name: str) -> dict:
        """
        Get information about table structure.
        
        Args:
            table_name: Name of table
        
        Returns:
            Dictionary with table information
        """
        query = f"DESCRIBE {table_name}"
        
        try:
            columns = self.fetch_all(query)
            return {
                'name': table_name,
                'columns': [
                    {
                        'name': col[0],
                        'type': col[1],
                        'null': col[2],
                        'key': col[3]
                    }
                    for col in columns
                ]
            }
        except Exception as e:
            logger.error(f"Failed to get table info for {table_name}: {e}")
            raise
    
    def get_table_count(self, table_name: str) -> int:
        """
        Get row count for table.
        
        Args:
            table_name: Name of table
        
        Returns:
            Number of rows in table
        """
        query = f"SELECT COUNT(*) as cnt FROM {table_name}"
        result = self.fetch_one(query)
        return result[0] if result else 0
    
    def vacuum(self) -> None:
        """
        Optimize database (reclaim space).
        
        Equivalent to VACUUM in SQLite.
        """
        try:
            self.connection.execute("VACUUM")
            self.connection.execute("CHECKPOINT")
            logger.info("Database optimized successfully")
        except Exception as e:
            logger.warning(f"VACUUM failed, running CHECKPOINT only: {e}")
            self.connection.execute("CHECKPOINT")
    
    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()


class DatabaseConnectionPool:
    """
    Simple connection pool for managing multiple DuckDB connections.
    
    Note: DuckDB is single-writer, multi-reader. This pool helps manage
    read connections while ensuring safe access.
    """
    
    def __init__(self, database_path: Optional[str] = None, pool_size: int = 3):
        """
        Initialize connection pool.
        
        Args:
            database_path: Path to .duckdb file
            pool_size: Number of read connections to maintain
        """
        self.database_path = database_path or settings.duckdb_path
        self.pool_size = pool_size
        self.connections: List[DatabaseConnection] = []
        self.current_idx = 0
        self._initialize_pool()
    
    def _initialize_pool(self) -> None:
        """Initialize pool of connections."""
        for i in range(self.pool_size):
            try:
                conn = DatabaseConnection(self.database_path)
                self.connections.append(conn)
                logger.info(f"Pool connection {i+1}/{self.pool_size} initialized")
            except Exception as e:
                logger.error(f"Failed to initialize pool connection {i+1}: {e}")
                raise
    
    def get_connection(self) -> DatabaseConnection:
        """
        Get next connection from pool (round-robin).
        
        Returns:
            DatabaseConnection object
        """
        conn = self.connections[self.current_idx]
        self.current_idx = (self.current_idx + 1) % self.pool_size
        return conn
    
    def close_all(self) -> None:
        """Close all connections in pool."""
        for conn in self.connections:
            try:
                conn.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        
        self.connections = []
        logger.info("All pool connections closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close_all()
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close_all()


# Global connection pool instance (lazy initialization)
_connection_pool: Optional[DatabaseConnectionPool] = None


def get_connection() -> DatabaseConnection:
    """
    Get connection from global pool.
    
    Returns:
        DatabaseConnection object
    """
    global _connection_pool
    
    if _connection_pool is None:
        _connection_pool = DatabaseConnectionPool()
    
    return _connection_pool.get_connection()


def get_direct_connection(database_path: Optional[str] = None) -> DatabaseConnection:
    """
    Get direct connection (not from pool).
    
    Useful for write operations or one-off connections.
    
    Args:
        database_path: Optional path to .duckdb file
    
    Returns:
        DatabaseConnection object
    """
    return DatabaseConnection(database_path)


@contextmanager
def get_connection_context(database_path: Optional[str] = None):
    """
    Context manager for database connection.
    
    Usage:
        with get_connection_context() as conn:
            results = conn.fetch_all("SELECT * FROM table")
    
    Args:
        database_path: Optional path to .duckdb file
    
    Yields:
        DatabaseConnection object
    """
    conn = get_direct_connection(database_path)
    try:
        yield conn
    finally:
        conn.close()


def close_connection_pool() -> None:
    """Close global connection pool."""
    global _connection_pool
    
    if _connection_pool:
        _connection_pool.close_all()
        _connection_pool = None
        logger.info("Global connection pool closed")
