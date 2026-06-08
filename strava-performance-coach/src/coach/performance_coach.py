"""Rule-based performance coach recommendations."""

import logging
from dataclasses import dataclass
from typing import Optional

from src.database.db_connection import DatabaseConnection, get_direct_connection

logger = logging.getLogger(__name__)


@dataclass
class CoachResult:
    """Summary of generated recommendations."""

    recommendations_created: int


class PerformanceCoach:
    """Generate explainable performance recommendations from analytics tables."""

    def __init__(self, db: Optional[DatabaseConnection] = None):
        self.db = db or get_direct_connection()
        self._owns_db = db is None

    def generate_recommendations(self, athlete_id: Optional[int] = None) -> CoachResult:
        """Refresh pending coach recommendations."""
        filter_sql = "WHERE athlete_id = ?" if athlete_id is not None else ""
        params = (athlete_id,) if athlete_id is not None else None
        self.db.execute(f"DELETE FROM coach_recommendations {filter_sql}", params)

        created = 0
        created += self._create_weekly_recommendations(athlete_id)
        created += self._create_activity_recommendations(athlete_id)
        return CoachResult(recommendations_created=created)

    def _create_weekly_recommendations(self, athlete_id: Optional[int]) -> int:
        filter_sql = "WHERE athlete_id = ?" if athlete_id is not None else ""
        params = (athlete_id,) if athlete_id is not None else None

        rows = self.db.fetch_all(
            f"""
            SELECT athlete_id, summary_id, fatigue_level, recovery_status,
                   total_training_load, num_activities, avg_performance_score
            FROM weekly_summary
            {filter_sql}
            ORDER BY week_start DESC
            LIMIT 8
            """,
            params,
        )

        records = []
        for row in rows:
            rec_athlete_id, week_id, fatigue, recovery, load, num_activities, score = row
            if fatigue == "high" or recovery == "needs_recovery":
                records.append(
                    self._recommendation_record(
                        rec_athlete_id,
                        "recovery_needed",
                        "Training load is high. Plan a recovery day or an easy Zone 2 session.",
                        "Keep the next session easy and avoid intervals.",
                        "high",
                        0.88,
                        week_id=week_id,
                    )
                )
            elif num_activities < 3:
                records.append(
                    self._recommendation_record(
                        rec_athlete_id,
                        "consistency_focus",
                        "This week has low activity frequency. Add one short aerobic workout.",
                        "Schedule a 30-45 minute easy run, ride, or walk.",
                        "medium",
                        0.78,
                        week_id=week_id,
                    )
                )
            elif score and score >= 80:
                records.append(
                    self._recommendation_record(
                        rec_athlete_id,
                        "progression_opportunity",
                        "Performance is trending well. A controlled progression session is appropriate.",
                        "Add one tempo or hill session if recovery feels good.",
                        "medium",
                        0.72,
                        week_id=week_id,
                    )
                )

        self._insert_recommendations(records)
        return len(records)

    def _create_activity_recommendations(self, athlete_id: Optional[int]) -> int:
        filter_sql = "WHERE athlete_id = ?" if athlete_id is not None else ""
        params = (athlete_id,) if athlete_id is not None else None

        rows = self.db.fetch_all(
            f"""
            SELECT athlete_id, activity_id, performance_score, fatigue_impact,
                   intensity_level, recovery_indicator
            FROM fct_activity_metrics
            {filter_sql}
            ORDER BY activity_date DESC
            LIMIT 10
            """,
            params,
        )

        records = []
        for row in rows:
            rec_athlete_id, activity_id, score, fatigue, intensity, recovery = row
            if fatigue and fatigue >= 70:
                records.append(
                    self._recommendation_record(
                        rec_athlete_id,
                        "fatigue_watch",
                        "The latest hard activity carries a high fatigue impact.",
                        "Follow with mobility, rest, or an easy aerobic session.",
                        "high",
                        0.84,
                        activity_id=activity_id,
                    )
                )
            elif intensity == "low" and score and score < 60:
                records.append(
                    self._recommendation_record(
                        rec_athlete_id,
                        "efficiency_focus",
                        "Low-intensity efficiency is below target.",
                        "Keep easy sessions conversational and build duration gradually.",
                        "low",
                        0.66,
                        activity_id=activity_id,
                    )
                )
            elif recovery == "good" and score and score >= 85:
                records.append(
                    self._recommendation_record(
                        rec_athlete_id,
                        "maintain_momentum",
                        "Strong recent performance with good recovery signal.",
                        "Maintain the pattern and avoid adding too much volume at once.",
                        "medium",
                        0.7,
                        activity_id=activity_id,
                    )
                )

        self._insert_recommendations(records)
        return len(records)

    def _insert_recommendations(self, records) -> None:
        if not records:
            return
        self.db.insert_records("coach_recommendations", records)

    @staticmethod
    def _recommendation_record(
        athlete_id: int,
        recommendation_type: str,
        recommendation_text: str,
        action_suggested: str,
        priority_level: str,
        confidence_score: float,
        activity_id: Optional[int] = None,
        week_id: Optional[int] = None,
    ):
        return {
            "athlete_id": athlete_id,
            "activity_id": activity_id,
            "week_id": week_id,
            "recommendation_type": recommendation_type,
            "recommendation_text": recommendation_text,
            "confidence_score": confidence_score,
            "action_suggested": action_suggested,
            "priority_level": priority_level,
            "status": "pending",
        }

    def close(self) -> None:
        if self._owns_db:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
