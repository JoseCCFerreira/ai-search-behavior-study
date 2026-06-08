"""
Database Tests

Comprehensive test suite for DuckDB connection and schema validation.

Author: Strava Performance Coach
Date: 2026-06-02
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
import json

from src.database.db_connection import (
    DatabaseConnection,
    DatabaseConnectionPool,
    get_connection,
    get_direct_connection,
    get_connection_context,
    close_connection_pool
)
from src.database.create_database import DatabaseInitializer


# Fixtures

@pytest.fixture
def temp_database():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.duckdb')
        yield db_path
        close_connection_pool()


@pytest.fixture
def initialized_database(temp_database):
    """Create initialized database with schema and mock data."""
    initializer = DatabaseInitializer(temp_database)
    results = initializer.initialize(with_mock_data=True)
    assert results['status'] == 'success'
    yield temp_database
    close_connection_pool()


@pytest.fixture
def db_connection(temp_database):
    """Create database connection."""
    conn = get_direct_connection(temp_database)
    yield conn
    conn.close()


# ============================================================================
# DatabaseConnection Tests
# ============================================================================

class TestDatabaseConnection:
    """Test DatabaseConnection class."""
    
    def test_connection_initialization(self, temp_database):
        """Test database connection initialization."""
        conn = DatabaseConnection(temp_database)
        assert conn.connection is not None
        assert conn.database_path == temp_database
        conn.close()
    
    def test_connection_close(self, db_connection):
        """Test closing connection."""
        db_connection.close()
        assert db_connection.connection is None
    
    def test_connection_context_manager(self, temp_database):
        """Test context manager functionality."""
        with DatabaseConnection(temp_database) as conn:
            assert conn.connection is not None
    
    def test_execute_query(self, db_connection):
        """Test executing SQL query."""
        result = db_connection.execute("SELECT 1 as num")
        assert result is not None
    
    def test_fetch_all(self, db_connection):
        """Test fetch_all method."""
        result = db_connection.fetch_all("SELECT 1 as num")
        assert len(result) == 1
        assert result[0][0] == 1
    
    def test_fetch_one(self, db_connection):
        """Test fetch_one method."""
        result = db_connection.fetch_one("SELECT 1 as num")
        assert result is not None
        assert result[0] == 1
    
    def test_fetch_df(self, db_connection):
        """Test fetch_df method (pandas)."""
        df = db_connection.fetch_df("SELECT 1 as num, 'test' as name")
        assert len(df) == 1
        assert df['num'].iloc[0] == 1
        assert df['name'].iloc[0] == 'test'
    
    def test_parameterized_query(self, db_connection):
        """Test parameterized queries."""
        result = db_connection.fetch_one(
            "SELECT ? as value",
            ('test_value',)
        )
        assert result[0] == 'test_value'
    
    def test_table_exists(self, initialized_database):
        """Test table_exists method."""
        conn = get_direct_connection(initialized_database)
        assert conn.table_exists('stg_activities') is True
        assert conn.table_exists('nonexistent_table') is False
        conn.close()
    
    def test_get_table_info(self, initialized_database):
        """Test get_table_info method."""
        conn = get_direct_connection(initialized_database)
        info = conn.get_table_info('stg_activities')
        
        assert info['name'] == 'stg_activities'
        assert len(info['columns']) > 0
        assert 'activity_id' in [col['name'] for col in info['columns']]
        
        conn.close()
    
    def test_get_table_count(self, initialized_database):
        """Test get_table_count method."""
        conn = get_direct_connection(initialized_database)
        count = conn.get_table_count('stg_activities')
        
        assert count > 0  # Should have mock data
        
        conn.close()


# ============================================================================
# Schema Tests
# ============================================================================

class TestDatabaseSchema:
    """Test database schema creation and structure."""
    
    def test_bronze_layer_tables_exist(self, initialized_database):
        """Test Bronze layer tables exist."""
        conn = get_direct_connection(initialized_database)
        
        bronze_tables = ['raw_strava_activities', 'raw_strava_events']
        for table in bronze_tables:
            assert conn.table_exists(table), f"Table {table} not found"
        
        conn.close()
    
    def test_silver_layer_tables_exist(self, initialized_database):
        """Test Silver layer tables exist."""
        conn = get_direct_connection(initialized_database)
        
        silver_tables = ['stg_activities', 'stg_events']
        for table in silver_tables:
            assert conn.table_exists(table), f"Table {table} not found"
        
        conn.close()
    
    def test_gold_layer_tables_exist(self, initialized_database):
        """Test Gold layer tables exist."""
        conn = get_direct_connection(initialized_database)
        
        gold_tables = [
            'fct_activity_metrics',
            'daily_summary',
            'weekly_summary',
            'coach_recommendations'
        ]
        for table in gold_tables:
            assert conn.table_exists(table), f"Table {table} not found"
        
        conn.close()
    
    def test_utility_tables_exist(self, initialized_database):
        """Test utility tables exist."""
        conn = get_direct_connection(initialized_database)
        
        utility_tables = [
            'athlete_profile',
            'ref_activity_types',
            'data_load_history',
            'data_quality_metrics'
        ]
        for table in utility_tables:
            assert conn.table_exists(table), f"Table {table} not found"
        
        conn.close()
    
    def test_stg_activities_structure(self, initialized_database):
        """Test stg_activities table structure."""
        conn = get_direct_connection(initialized_database)
        info = conn.get_table_info('stg_activities')
        
        column_names = [col['name'] for col in info['columns']]
        required_columns = [
            'activity_id', 'athlete_id', 'activity_name', 'activity_type',
            'activity_date', 'distance_km', 'moving_time_minutes',
            'average_speed_kmh', 'average_heartrate'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Column {col} not found"
        
        conn.close()
    
    def test_fct_activity_metrics_structure(self, initialized_database):
        """Test fct_activity_metrics table structure."""
        conn = get_direct_connection(initialized_database)
        info = conn.get_table_info('fct_activity_metrics')
        
        column_names = [col['name'] for col in info['columns']]
        required_columns = [
            'activity_id', 'athlete_id', 'performance_score',
            'training_load', 'intensity_level'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Column {col} not found"
        
        conn.close()
    
    def test_ref_activity_types_seeded(self, initialized_database):
        """Test ref_activity_types populated with data."""
        conn = get_direct_connection(initialized_database)
        count = conn.get_table_count('ref_activity_types')
        
        assert count > 0, "ref_activity_types should be seeded"
        
        # Check for specific activity types
        result = conn.fetch_all("SELECT activity_type FROM ref_activity_types")
        activity_types = [row[0] for row in result]
        
        assert 'Run' in activity_types
        assert 'Ride' in activity_types
        
        conn.close()


# ============================================================================
# Mock Data Tests
# ============================================================================

class TestMockData:
    """Test mock data insertion and retrieval."""
    
    def test_mock_athlete_inserted(self, initialized_database):
        """Test mock athlete data was inserted."""
        conn = get_direct_connection(initialized_database)
        count = conn.get_table_count('athlete_profile')
        
        assert count > 0
        
        athlete = conn.fetch_one(
            "SELECT athlete_id, athlete_name FROM athlete_profile LIMIT 1"
        )
        assert athlete[1] == 'Test Athlete'
        
        conn.close()
    
    def test_mock_activities_inserted(self, initialized_database):
        """Test mock activities were inserted."""
        conn = get_direct_connection(initialized_database)
        count = conn.get_table_count('stg_activities')
        
        assert count == 10, f"Expected 10 mock activities, got {count}"
        
        conn.close()
    
    def test_mock_activities_data_quality(self, initialized_database):
        """Test mock activity data quality."""
        conn = get_direct_connection(initialized_database)
        
        # Check for NULL values in critical columns
        result = conn.fetch_one("""
            SELECT COUNT(*) FROM stg_activities
            WHERE activity_id IS NULL
            OR athlete_id IS NULL
            OR activity_date IS NULL
        """)
        
        assert result[0] == 0, "Found NULL values in critical columns"
        
        conn.close()
    
    def test_mock_metrics_inserted(self, initialized_database):
        """Test mock metrics were inserted."""
        conn = get_direct_connection(initialized_database)
        count = conn.get_table_count('fct_activity_metrics')
        
        assert count == 10, f"Expected 10 mock metrics, got {count}"
        
        conn.close()
    
    def test_mock_daily_summary_inserted(self, initialized_database):
        """Test mock daily summaries were inserted."""
        conn = get_direct_connection(initialized_database)
        count = conn.get_table_count('daily_summary')
        
        assert count == 7, f"Expected 7 mock daily summaries, got {count}"
        
        conn.close()
    
    def test_mock_weekly_summary_inserted(self, initialized_database):
        """Test mock weekly summary was inserted."""
        conn = get_direct_connection(initialized_database)
        count = conn.get_table_count('weekly_summary')
        
        assert count == 1, f"Expected 1 mock weekly summary, got {count}"
        
        conn.close()


# ============================================================================
# Connection Pool Tests
# ============================================================================

class TestConnectionPool:
    """Test DatabaseConnectionPool functionality."""
    
    def test_pool_initialization(self, temp_database):
        """Test connection pool initialization."""
        pool = DatabaseConnectionPool(temp_database, pool_size=3)
        assert len(pool.connections) == 3
        pool.close_all()
    
    def test_pool_get_connection(self, temp_database):
        """Test getting connection from pool."""
        pool = DatabaseConnectionPool(temp_database, pool_size=2)
        
        conn1 = pool.get_connection()
        conn2 = pool.get_connection()
        conn3 = pool.get_connection()  # Should cycle back to conn1
        
        assert conn1 == conn3
        pool.close_all()
    
    def test_pool_context_manager(self, temp_database):
        """Test pool as context manager."""
        with DatabaseConnectionPool(temp_database, pool_size=2) as pool:
            assert len(pool.connections) == 2


# ============================================================================
# Query Tests
# ============================================================================

class TestQueries:
    """Test common queries on schema."""
    
    def test_recent_activities_view(self, initialized_database):
        """Test v_recent_activities view."""
        conn = get_direct_connection(initialized_database)
        
        result = conn.fetch_all("SELECT * FROM v_recent_activities LIMIT 5")
        assert len(result) > 0
        
        conn.close()
    
    def test_performance_trend_view(self, initialized_database):
        """Test v_performance_trend view."""
        conn = get_direct_connection(initialized_database)
        
        result = conn.fetch_all("SELECT * FROM v_performance_trend LIMIT 5")
        assert len(result) > 0
        
        conn.close()
    
    def test_activity_distribution_view(self, initialized_database):
        """Test v_activity_distribution view."""
        conn = get_direct_connection(initialized_database)
        
        result = conn.fetch_all("SELECT * FROM v_activity_distribution")
        assert len(result) > 0
        
        conn.close()
    
    def test_weekly_activities_query(self, initialized_database):
        """Test querying activities from past week."""
        conn = get_direct_connection(initialized_database)
        
        result = conn.fetch_all("""
            SELECT activity_type, COUNT(*) as cnt
            FROM stg_activities
            WHERE activity_date >= CURRENT_DATE - INTERVAL 7 DAY
            GROUP BY activity_type
        """)
        
        assert len(result) > 0
        
        conn.close()
    
    def test_performance_stats_query(self, initialized_database):
        """Test querying performance statistics."""
        conn = get_direct_connection(initialized_database)
        
        result = conn.fetch_one("""
            SELECT
                AVG(performance_score) as avg_score,
                MAX(performance_score) as max_score,
                MIN(performance_score) as min_score
            FROM fct_activity_metrics
        """)
        
        assert result is not None
        assert result[0] is not None  # avg_score
        
        conn.close()


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_invalid_database_path(self):
        """Test handling invalid database path."""
        with pytest.raises(Exception):
            conn = DatabaseConnection('/invalid/path/to/database.duckdb')
    
    def test_query_on_closed_connection(self, db_connection):
        """Test querying on closed connection."""
        db_connection.close()
        
        with pytest.raises(RuntimeError):
            db_connection.execute("SELECT 1")
    
    def test_insert_empty_records(self, db_connection):
        """Test inserting empty records."""
        with pytest.raises(ValueError):
            db_connection.insert_records('stg_activities', [])
    
    def test_query_nonexistent_table(self, db_connection):
        """Test querying nonexistent table."""
        with pytest.raises(Exception):
            db_connection.execute("SELECT * FROM nonexistent_table")


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for database operations."""
    
    def test_full_workflow(self, temp_database):
        """Test full database workflow."""
        # 1. Initialize
        initializer = DatabaseInitializer(temp_database)
        results = initializer.initialize(with_mock_data=True)
        assert results['status'] == 'success'
        
        # 2. Connect and verify
        conn = get_direct_connection(temp_database)
        assert conn.table_exists('stg_activities')
        
        # 3. Query data
        activities = conn.fetch_all("""
            SELECT activity_id, activity_type, distance_km
            FROM stg_activities
            WHERE distance_km > 5
        """)
        assert len(activities) > 0
        
        # 4. Insert new activity
        new_activity = {
            'activity_id': 9999,
            'athlete_id': 12345,
            'activity_name': 'Test Activity',
            'activity_type': 'Run',
            'activity_date': datetime.now().date(),
            'distance_meters': 5000,
            'moving_time_seconds': 1200,
            'elapsed_time_seconds': 1300,
            'average_speed_mps': 4.17,
            'average_heartrate': 150,
        }
        conn.insert_records('stg_activities', [new_activity])
        
        # 5. Verify insertion
        count = conn.get_table_count('stg_activities')
        assert count == 11  # 10 mock + 1 new
        
        conn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
