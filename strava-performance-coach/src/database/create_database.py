"""
Database Initialization

Script to create database schema, reference data, and mock data for testing.

Author: Strava Performance Coach
Date: 2026-06-02
"""

import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
import json
from typing import List, Dict, Any

from config.settings import settings
from src.database.db_connection import get_direct_connection

logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """Initialize DuckDB database with schema and seed data."""
    
    def __init__(self, database_path: str = None):
        """
        Initialize database.
        
        Args:
            database_path: Path to .duckdb file
        """
        self.database_path = database_path or settings.duckdb_path
        self.conn = None
        self.schema_path = Path(__file__).parent.parent.parent / "database" / "schema.sql"
    
    def connect(self) -> None:
        """Create database connection."""
        try:
            self.conn = get_direct_connection(self.database_path)
            logger.info(f"Connected to database: {self.database_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def load_schema(self) -> str:
        """
        Load SQL schema from file.
        
        Returns:
            SQL schema string
        """
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {self.schema_path}")
        
        with open(self.schema_path, 'r') as f:
            schema = f.read()
        
        logger.info(f"Schema loaded from {self.schema_path}")
        return schema
    
    def execute_schema(self) -> None:
        """Execute schema SQL to create tables."""
        try:
            schema = self.load_schema()
            
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in schema.split(';') if s.strip()]
            
            for i, statement in enumerate(statements, 1):
                self.conn.execute(statement)
                logger.debug(f"Executed statement {i}/{len(statements)}")
            
            logger.info(f"Schema created successfully ({len(statements)} statements)")
        
        except Exception as e:
            logger.error(f"Failed to execute schema: {e}")
            raise
    
    def verify_schema(self) -> Dict[str, int]:
        """
        Verify schema was created correctly.
        
        Returns:
            Dictionary with table names and row counts
        """
        tables = {
            # Bronze
            'raw_strava_activities': 0,
            'raw_strava_events': 0,
            # Silver
            'stg_activities': 0,
            'activity_streams': 0,
            'stg_events': 0,
            # Gold
            'fct_activity_metrics': 0,
            'daily_summary': 0,
            'weekly_summary': 0,
            'coach_recommendations': 0,
            # Utility
            'athlete_profile': 0,
            'ref_activity_types': 0,
            'data_load_history': 0,
            'data_quality_metrics': 0,
        }
        
        try:
            for table_name in tables.keys():
                if self.conn.table_exists(table_name):
                    count = self.conn.get_table_count(table_name)
                    tables[table_name] = count
                    logger.info(f"✓ Table {table_name}: {count} rows")
                else:
                    logger.warning(f"✗ Table {table_name} not found")
            
            return tables
        
        except Exception as e:
            logger.error(f"Schema verification failed: {e}")
            raise
    
    def insert_mock_data(self) -> None:
        """Insert mock data for testing."""
        logger.info("Inserting mock data...")
        
        try:
            # Insert mock athlete
            self._insert_mock_athlete()
            
            # Insert mock activities (Bronze)
            self._insert_mock_activities()
            
            # Insert mock staged activities (Silver)
            self._insert_mock_staged_activities()
            
            # Insert mock metrics (Gold)
            self._insert_mock_metrics()
            
            # Insert mock summaries
            self._insert_mock_summaries()
            
            logger.info("Mock data inserted successfully")
        
        except Exception as e:
            logger.error(f"Failed to insert mock data: {e}")
            raise
    
    def _insert_mock_athlete(self) -> None:
        """Insert mock athlete profile."""
        athlete_data = {
            'athlete_id': 12345,
            'athlete_name': 'Test Athlete',
            'profile_picture_url': 'https://example.com/profile.jpg',
            'city': 'Lisbon',
            'state': 'PT',
            'country': 'Portugal',
            'sex': 'M',
            'premium': True
        }
        
        self.conn.insert_records('athlete_profile', [athlete_data])
        logger.info(f"Inserted mock athlete: {athlete_data['athlete_name']}")
    
    def _insert_mock_activities(self) -> None:
        """Insert mock raw activities."""
        # Generate 10 mock activities
        activities = []
        base_date = datetime.now()
        
        for i in range(10):
            activity_date = base_date - timedelta(days=i)
            activity_data = {
                'source_activity_id': 1000 + i,
                'athlete_id': 12345,
                'raw_payload': json.dumps({
                    'id': 1000 + i,
                    'name': f'Activity {i+1}',
                    'type': ['Run', 'Ride', 'Walk', 'Hike', 'Swim'][i % 5],
                    'distance': (5 + i) * 1000,
                    'moving_time': 1800 + (i * 60),
                    'average_speed': 4 + (i * 0.1),
                    'average_heartrate': 140 + (i * 2),
                })
            }
            activities.append(activity_data)
        
        self.conn.insert_records('raw_strava_activities', activities)
        logger.info(f"Inserted {len(activities)} mock raw activities")
    
    def _insert_mock_staged_activities(self) -> None:
        """Insert mock staged activities."""
        activities = []
        base_date = datetime.now().date()
        activity_types = ['Run', 'Ride', 'Walk', 'Hike', 'Swim']
        
        for i in range(10):
            activity_date = base_date - timedelta(days=i)
            activity_type = activity_types[i % 5]
            distance_m = (5 + i) * 1000
            moving_time_s = 1800 + (i * 60)
            
            activity = {
                'activity_id': 2000 + i,
                'athlete_id': 12345,
                'activity_name': f'{activity_type} {i+1}',
                'activity_type': activity_type,
                'activity_date': activity_date,
                'distance_meters': distance_m,
                'moving_time_seconds': moving_time_s,
                'elapsed_time_seconds': moving_time_s + 300,
                'average_speed_mps': distance_m / moving_time_s,
                'max_speed_mps': 6 + (i * 0.1),
                'average_heartrate': 140 + (i * 2),
                'max_heartrate': 170 + (i * 2),
                'total_elevation_gain': 100 + (i * 10),
                'total_elevation_loss': 100 + (i * 10),
            }
            activities.append(activity)
        
        self.conn.insert_records('stg_activities', activities)
        logger.info(f"Inserted {len(activities)} mock staged activities")
    
    def _insert_mock_metrics(self) -> None:
        """Insert mock activity metrics."""
        metrics = []
        base_date = datetime.now().date()
        
        for i in range(10):
            activity_date = base_date - timedelta(days=i)
            
            metric = {
                'activity_id': 2000 + i,
                'athlete_id': 12345,
                'activity_date': activity_date,
                'performance_score': 70 + (i % 5) * 5,
                'training_load': 200 + (i * 10),
                'intensity_level': ['low', 'moderate', 'high'][i % 3],
                'intensity_score': 30 + (i % 4) * 20,
                'efficiency_score': 0.7 + (i * 0.01),
                'fatigue_impact': 20 + (i % 5) * 10,
                'recovery_indicator': ['good', 'fair', 'poor'][i % 3],
            }
            metrics.append(metric)
        
        self.conn.insert_records('fct_activity_metrics', metrics)
        logger.info(f"Inserted {len(metrics)} mock activity metrics")
    
    def _insert_mock_summaries(self) -> None:
        """Insert mock daily and weekly summaries."""
        base_date = datetime.now().date()
        
        # Daily summaries (last 7 days)
        daily = []
        for i in range(7):
            summary_date = base_date - timedelta(days=i)
            daily_summary = {
                'athlete_id': 12345,
                'summary_date': summary_date,
                'num_activities': (i % 3) + 1,
                'total_distance_km': (i + 5) * 1.5,
                'total_moving_time_minutes': 100 + (i * 15),
                'total_elapsed_time_minutes': 120 + (i * 15),
                'avg_heartrate': 140 + (i * 2),
                'max_heartrate': 170 + (i * 2),
                'avg_performance_score': 70 + (i % 5) * 5,
                'total_training_load': 500 + (i * 50),
                'total_elevation_gain': 200 + (i * 20),
                'num_runs': (i % 3),
                'num_rides': (i % 2),
                'num_walks': (i % 2),
                'num_hikes': (i % 2),
                'daily_score': 70 + (i % 5) * 5,
            }
            daily.append(daily_summary)
        
        self.conn.insert_records('daily_summary', daily)
        logger.info(f"Inserted {len(daily)} mock daily summaries")
        
        # Weekly summary (current week)
        week_start = base_date - timedelta(days=base_date.weekday())
        week_end = week_start + timedelta(days=6)
        iso_calendar = base_date.isocalendar()
        
        weekly = {
            'athlete_id': 12345,
            'week_start': week_start,
            'week_end': week_end,
            'iso_year': iso_calendar[0],
            'iso_week': iso_calendar[1],
            'num_activities': 5,
            'total_distance_km': 35.5,
            'total_moving_time_minutes': 420,
            'avg_heartrate': 142,
            'max_heartrate': 175,
            'avg_performance_score': 72,
            'total_training_load': 2100,
            'total_elevation_gain': 800,
            'weekly_score': 75,
            'fatigue_level': 'moderate',
            'recovery_status': 'good',
            'has_recommendation': True,
            'recommendation_text': 'Consider increasing intensity this week',
        }
        
        self.conn.insert_records('weekly_summary', [weekly])
        logger.info("Inserted 1 mock weekly summary")
    
    def initialize(self, with_mock_data: bool = True) -> Dict[str, Any]:
        """
        Run full initialization.
        
        Args:
            with_mock_data: Whether to insert mock data
        
        Returns:
            Dictionary with initialization results
        """
        try:
            self.connect()
            self.execute_schema()
            
            results = {
                'status': 'success',
                'database_path': self.database_path,
                'schema_created': True,
                'tables': self.verify_schema(),
            }
            
            if with_mock_data:
                self.insert_mock_data()
                results['mock_data_inserted'] = True
                results['tables'] = self.verify_schema()  # Update counts
            
            return results
        
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return {
                'status': 'failed',
                'database_path': self.database_path,
                'error': str(e)
            }
        
        finally:
            self.close()


def initialize_database(with_mock_data: bool = True, database_path: str = None) -> Dict[str, Any]:
    """
    Initialize database.
    
    Args:
        with_mock_data: Whether to insert mock data
        database_path: Optional custom database path
    
    Returns:
        Initialization results
    """
    initializer = DatabaseInitializer(database_path)
    return initializer.initialize(with_mock_data)


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize database
    logger.info("Starting database initialization...")
    results = initialize_database(with_mock_data=True)
    
    # Print results
    print("\n" + "="*60)
    print("Database Initialization Results")
    print("="*60)
    print(f"Status: {results['status'].upper()}")
    print(f"Database: {results['database_path']}")
    
    if results['status'] == 'success':
        print(f"Schema created: {results['schema_created']}")
        print(f"Mock data inserted: {results.get('mock_data_inserted', False)}")
        print("\nTables:")
        for table, count in results['tables'].items():
            status = "✓" if count >= 0 else "✗"
            print(f"  {status} {table}: {count} rows")
    else:
        print(f"Error: {results.get('error', 'Unknown error')}")
    
    print("="*60)
