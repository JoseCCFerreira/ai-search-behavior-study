"""Performance analytics for Strava activities."""

import logging
from dataclasses import dataclass
from typing import Optional

from src.database.db_connection import DatabaseConnection, get_direct_connection

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsResult:
    """Summary of analytics refresh work."""

    metrics_rows: int
    daily_rows: int
    weekly_rows: int


class PerformanceAnalytics:
    """Build gold-layer metrics and summaries from staged activities."""

    def __init__(self, db: Optional[DatabaseConnection] = None):
        self.db = db or get_direct_connection()
        self._owns_db = db is None

    def refresh_all(self, athlete_id: Optional[int] = None) -> AnalyticsResult:
        """Refresh activity metrics, daily summaries, and weekly summaries."""
        self.refresh_activity_metrics(athlete_id)
        self.refresh_daily_summary(athlete_id)
        self.refresh_weekly_summary(athlete_id)

        where_clause = "WHERE athlete_id = ?" if athlete_id is not None else ""
        params = (athlete_id,) if athlete_id is not None else None
        return AnalyticsResult(
            metrics_rows=self.db.fetch_one(
                f"SELECT COUNT(*) FROM fct_activity_metrics {where_clause}",
                params,
            )[0],
            daily_rows=self.db.fetch_one(
                f"SELECT COUNT(*) FROM daily_summary {where_clause}",
                params,
            )[0],
            weekly_rows=self.db.fetch_one(
                f"SELECT COUNT(*) FROM weekly_summary {where_clause}",
                params,
            )[0],
        )

    def refresh_activity_metrics(self, athlete_id: Optional[int] = None) -> None:
        """Recalculate per-activity performance metrics."""
        filter_sql = "WHERE athlete_id = ?" if athlete_id is not None else ""
        params = (athlete_id,) if athlete_id is not None else None

        self.db.execute(f"DELETE FROM fct_activity_metrics {filter_sql}", params)
        self.db.execute(
            f"""
            INSERT INTO fct_activity_metrics (
                activity_id, athlete_id, activity_date, performance_score,
                training_load, intensity_level, intensity_score, efficiency_score,
                fatigue_impact, recovery_indicator
            )
            SELECT
                activity_id,
                athlete_id,
                activity_date,
                LEAST(
                    100,
                    GREATEST(
                        0,
                        CAST(
                            45
                            + COALESCE(distance_km, 0) * 2.0
                            + COALESCE(average_speed_kmh, 0) * 1.8
                            + COALESCE(total_elevation_gain, 0) / 80.0
                            + CASE
                                WHEN average_heartrate IS NULL THEN 0
                                WHEN average_heartrate BETWEEN 125 AND 165 THEN 8
                                WHEN average_heartrate > 175 THEN -5
                                ELSE 2
                              END
                            AS INTEGER
                        )
                    )
                ) AS performance_score,
                ROUND(
                    moving_time_minutes
                    * CASE
                        WHEN average_heartrate IS NULL THEN 1.0
                        WHEN average_heartrate < 130 THEN 1.0
                        WHEN average_heartrate < 160 THEN 1.45
                        ELSE 1.9
                      END,
                    2
                ) AS training_load,
                CASE
                    WHEN average_heartrate IS NULL THEN
                        CASE
                            WHEN moving_time_minutes < 35 THEN 'low'
                            WHEN moving_time_minutes < 75 THEN 'moderate'
                            ELSE 'high'
                        END
                    WHEN average_heartrate < 130 THEN 'low'
                    WHEN average_heartrate < 160 THEN 'moderate'
                    ELSE 'high'
                END AS intensity_level,
                LEAST(
                    100,
                    GREATEST(
                        0,
                        CAST(
                            CASE
                                WHEN average_heartrate IS NOT NULL THEN average_heartrate * 0.55
                                ELSE COALESCE(average_speed_kmh, 0) * 8
                            END
                            AS INTEGER
                        )
                    )
                ) AS intensity_score,
                ROUND(COALESCE(average_speed_kmh, 0) / 30.0, 3) AS efficiency_score,
                LEAST(
                    100,
                    GREATEST(
                        0,
                        CAST(
                            moving_time_minutes
                            * CASE
                                WHEN average_heartrate IS NULL THEN 0.35
                                WHEN average_heartrate < 130 THEN 0.35
                                WHEN average_heartrate < 160 THEN 0.55
                                ELSE 0.8
                              END
                            AS INTEGER
                        )
                    )
                ) AS fatigue_impact,
                CASE
                    WHEN moving_time_minutes >= 90
                         OR COALESCE(average_heartrate, 0) >= 165 THEN 'poor'
                    WHEN moving_time_minutes >= 50
                         OR COALESCE(average_heartrate, 0) >= 145 THEN 'fair'
                    ELSE 'good'
                END AS recovery_indicator
            FROM stg_activities
            {filter_sql}
            """,
            params,
        )

    def refresh_daily_summary(self, athlete_id: Optional[int] = None) -> None:
        """Recalculate daily training summaries."""
        filter_sql = "WHERE athlete_id = ?" if athlete_id is not None else ""
        params = (athlete_id,) if athlete_id is not None else None

        self.db.execute(f"DELETE FROM daily_summary {filter_sql}", params)
        self.db.execute(
            f"""
            INSERT INTO daily_summary (
                athlete_id, summary_date, num_activities, total_distance_km,
                total_moving_time_minutes, total_elapsed_time_minutes,
                avg_heartrate, max_heartrate, avg_performance_score,
                total_training_load, total_elevation_gain, num_runs, num_rides,
                num_walks, num_hikes, daily_score
            )
            SELECT
                a.athlete_id,
                a.activity_date AS summary_date,
                COUNT(*) AS num_activities,
                ROUND(SUM(a.distance_km), 2) AS total_distance_km,
                ROUND(SUM(a.moving_time_minutes), 2) AS total_moving_time_minutes,
                ROUND(SUM(a.elapsed_time_minutes), 2) AS total_elapsed_time_minutes,
                CAST(AVG(a.average_heartrate) AS INTEGER) AS avg_heartrate,
                MAX(a.max_heartrate) AS max_heartrate,
                ROUND(AVG(m.performance_score), 2) AS avg_performance_score,
                ROUND(SUM(m.training_load), 2) AS total_training_load,
                ROUND(SUM(COALESCE(a.total_elevation_gain, 0)), 2) AS total_elevation_gain,
                SUM(CASE WHEN a.activity_type = 'Run' THEN 1 ELSE 0 END) AS num_runs,
                SUM(CASE WHEN a.activity_type = 'Ride' THEN 1 ELSE 0 END) AS num_rides,
                SUM(CASE WHEN a.activity_type = 'Walk' THEN 1 ELSE 0 END) AS num_walks,
                SUM(CASE WHEN a.activity_type = 'Hike' THEN 1 ELSE 0 END) AS num_hikes,
                CAST(AVG(m.performance_score) AS INTEGER) AS daily_score
            FROM stg_activities a
            LEFT JOIN fct_activity_metrics m ON a.activity_id = m.activity_id
            {filter_sql.replace("athlete_id", "a.athlete_id")}
            GROUP BY a.athlete_id, a.activity_date
            """,
            params,
        )

    def refresh_weekly_summary(self, athlete_id: Optional[int] = None) -> None:
        """Recalculate weekly training summaries."""
        filter_sql = "WHERE athlete_id = ?" if athlete_id is not None else ""
        params = (athlete_id,) if athlete_id is not None else None

        self.db.execute(f"DELETE FROM weekly_summary {filter_sql}", params)
        self.db.execute(
            f"""
            INSERT INTO weekly_summary (
                athlete_id, week_start, week_end, iso_year, iso_week,
                num_activities, total_distance_km, total_moving_time_minutes,
                avg_heartrate, max_heartrate, avg_performance_score,
                total_training_load, total_elevation_gain, weekly_score,
                fatigue_level, recovery_status, has_recommendation,
                recommendation_text
            )
            SELECT
                a.athlete_id,
                DATE_TRUNC('week', a.activity_date)::DATE AS week_start,
                (DATE_TRUNC('week', a.activity_date) + INTERVAL 6 DAY)::DATE AS week_end,
                EXTRACT('isoyear' FROM a.activity_date)::INTEGER AS iso_year,
                EXTRACT('week' FROM a.activity_date)::INTEGER AS iso_week,
                COUNT(*) AS num_activities,
                ROUND(SUM(a.distance_km), 2) AS total_distance_km,
                ROUND(SUM(a.moving_time_minutes), 2) AS total_moving_time_minutes,
                CAST(AVG(a.average_heartrate) AS INTEGER) AS avg_heartrate,
                MAX(a.max_heartrate) AS max_heartrate,
                ROUND(AVG(m.performance_score), 2) AS avg_performance_score,
                ROUND(SUM(m.training_load), 2) AS total_training_load,
                ROUND(SUM(COALESCE(a.total_elevation_gain, 0)), 2) AS total_elevation_gain,
                CAST(AVG(m.performance_score) AS INTEGER) AS weekly_score,
                CASE
                    WHEN SUM(m.training_load) >= 800 THEN 'high'
                    WHEN SUM(m.training_load) >= 350 THEN 'moderate'
                    ELSE 'low'
                END AS fatigue_level,
                CASE
                    WHEN AVG(m.fatigue_impact) >= 65 THEN 'needs_recovery'
                    WHEN AVG(m.fatigue_impact) >= 40 THEN 'balanced'
                    ELSE 'fresh'
                END AS recovery_status,
                SUM(m.training_load) >= 800 OR COUNT(*) < 3 AS has_recommendation,
                CASE
                    WHEN SUM(m.training_load) >= 800 THEN 'Reduce intensity and schedule recovery.'
                    WHEN COUNT(*) < 3 THEN 'Add one easy aerobic session for consistency.'
                    ELSE 'Keep current training balance.'
                END AS recommendation_text
            FROM stg_activities a
            LEFT JOIN fct_activity_metrics m ON a.activity_id = m.activity_id
            {filter_sql.replace("athlete_id", "a.athlete_id")}
            GROUP BY
                a.athlete_id,
                DATE_TRUNC('week', a.activity_date),
                EXTRACT('isoyear' FROM a.activity_date),
                EXTRACT('week' FROM a.activity_date)
            """,
            params,
        )

    def close(self) -> None:
        if self._owns_db:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
