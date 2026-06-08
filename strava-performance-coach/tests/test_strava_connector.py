"""Tests for the high-level Strava connector."""

import tempfile
import time
from pathlib import Path

from src.auth.strava_oauth import TokenData
from src.connector import StravaConnector
from src.database.create_database import DatabaseInitializer
from src.database.db_connection import get_direct_connection


def test_connector_syncs_profile_and_activities():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.duckdb")
        initializer = DatabaseInitializer(db_path)
        initializer.initialize(with_mock_data=False)

        token = TokenData(
            access_token="access",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
            athlete_id=12345,
        )
        mock_activity = {
            "id": 987654,
            "name": "Morning Run",
            "distance": 10000.5,
            "moving_time": 3600,
            "elapsed_time": 3700,
            "start_date": "2026-06-02T08:00:00Z",
            "type": "Run",
            "average_speed": 2.78,
            "max_speed": 5.2,
            "average_heartrate": 155.2,
            "max_heartrate": 182,
            "total_elevation_gain": 125.5,
            "kudos_count": 5,
            "comment_count": 2,
        }
        mock_data = {
            "GET:/athlete": {
                "id": 12345,
                "firstname": "Test",
                "lastname": "Athlete",
                "profile_medium": "https://example.com/profile.jpg",
                "city": "Lisbon",
                "state": "Lisbon",
                "country": "Portugal",
                "sex": "M",
                "summit": False,
            },
            "GET:/athlete/activities": [mock_activity],
        }

        conn = get_direct_connection(db_path)
        with StravaConnector(
            token_data=token,
            db=conn,
            mock_mode=True,
            mock_data=mock_data,
        ) as connector:
            result = connector.sync_activities(max_pages=1)

        assert result.status == "completed"
        assert result.activities_loaded == 1
        assert conn.get_table_count("raw_strava_activities") == 1
        assert conn.get_table_count("stg_activities") == 1

        activity = conn.fetch_one(
            """
            SELECT activity_name, activity_type, distance_meters, average_heartrate
            FROM stg_activities
            WHERE activity_id = ?
            """,
            (987654,),
        )
        assert activity == ("Morning Run", "Run", 10000, 155)

        conn.close()


def test_daily_sync_loads_only_new_activities_once_per_day():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.duckdb")
        initializer = DatabaseInitializer(db_path)
        initializer.initialize(with_mock_data=False)

        token = TokenData(
            access_token="access",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
            athlete_id=12345,
        )
        existing_activity = {
            "id": 111,
            "name": "Existing Run",
            "distance": 5000,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "start_date": "2026-06-01T08:00:00Z",
            "type": "Run",
            "average_speed": 2.8,
            "average_heartrate": 140,
        }
        new_activity = {
            "id": 222,
            "name": "New Ride",
            "distance": 20000,
            "moving_time": 3600,
            "elapsed_time": 3700,
            "start_date": "2026-06-02T08:00:00Z",
            "type": "Ride",
            "average_speed": 5.5,
            "average_heartrate": 150,
        }
        mock_data = {
            "GET:/athlete": {
                "id": 12345,
                "firstname": "Test",
                "lastname": "Athlete",
            },
            "GET:/athlete/activities": [new_activity, existing_activity],
        }

        conn = get_direct_connection(db_path)
        with StravaConnector(
            token_data=token,
            db=conn,
            mock_mode=True,
            mock_data=mock_data,
        ) as connector:
            connector.save_activity(existing_activity, athlete_id=12345)
            first = connector.sync_daily_if_needed(max_pages=1)
            second = connector.sync_daily_if_needed(max_pages=1)

        assert first.status == "completed"
        assert first.activities_fetched == 2
        assert first.activities_loaded == 1
        assert first.analytics_metrics_rows == 2
        assert second.status == "skipped_already_checked_today"
        assert conn.get_table_count("stg_activities") == 2
        assert conn.get_table_count("daily_summary") == 2
        assert conn.get_table_count("fct_activity_metrics") == 2

        conn.close()
