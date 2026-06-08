"""Tests for analytics and coach outputs."""

import tempfile
from pathlib import Path

from src.coach import PerformanceCoach
from src.database.create_database import DatabaseInitializer
from src.database.db_connection import get_direct_connection
from src.metrics import PerformanceAnalytics


def test_performance_analytics_and_coach_generate_outputs():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.duckdb")
        initializer = DatabaseInitializer(db_path)
        result = initializer.initialize(with_mock_data=True)
        assert result["status"] == "success"

        conn = get_direct_connection(db_path)
        conn.execute("DELETE FROM coach_recommendations")

        analytics = PerformanceAnalytics(conn).refresh_all(12345)
        coach = PerformanceCoach(conn).generate_recommendations(12345)

        assert analytics.metrics_rows == 10
        assert analytics.daily_rows >= 7
        assert analytics.weekly_rows >= 1
        assert coach.recommendations_created >= 1

        recommendation = conn.fetch_one(
            """
            SELECT recommendation_type, priority_level
            FROM coach_recommendations
            WHERE athlete_id = 12345
            LIMIT 1
            """
        )
        assert recommendation is not None

        conn.close()
