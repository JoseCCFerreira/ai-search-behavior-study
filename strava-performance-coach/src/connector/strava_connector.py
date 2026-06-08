"""
High-level Strava connector.

Coordinates OAuth tokens, Strava API reads, and DuckDB persistence for the
bronze and silver layers used by the performance coach.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timezone
from typing import Any, Dict, Optional, Set

from src.api.strava_client import StravaClient
from src.auth.strava_oauth import StravaOAuth, TokenData
from src.coach import PerformanceCoach
from src.database.db_connection import DatabaseConnection, get_direct_connection
from src.metrics import PerformanceAnalytics

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Summary returned after a Strava sync."""

    athlete_id: int
    activities_fetched: int
    activities_loaded: int
    activities_failed: int
    started_at: datetime
    finished_at: datetime
    status: str
    error_message: Optional[str] = None
    analytics_metrics_rows: int = 0
    recommendations_created: int = 0


class StravaConnector:
    """Connect Strava API data to the local DuckDB medallion schema."""

    def __init__(
        self,
        token_data: Optional[TokenData] = None,
        client: Optional[StravaClient] = None,
        db: Optional[DatabaseConnection] = None,
        oauth: Optional[StravaOAuth] = None,
        mock_mode: bool = False,
        mock_data: Optional[Dict[str, Any]] = None,
    ):
        self.oauth = oauth or StravaOAuth()
        self.token_data = token_data or self.oauth.load_tokens()
        if client is None and self.token_data is None:
            raise ValueError(
                "No Strava tokens found. Run the OAuth flow before syncing activities."
            )

        self.client = client or StravaClient(
            token=self.token_data,
            mock_mode=mock_mode,
            mock_data=mock_data,
        )
        self.db = db or get_direct_connection()
        self._owns_db = db is None

    def sync_profile(self) -> Dict[str, Any]:
        """Fetch and cache the authenticated athlete profile."""
        athlete = self.client.get_athlete()
        athlete_id = int(athlete["id"])
        athlete_name = " ".join(
            part
            for part in [athlete.get("firstname"), athlete.get("lastname")]
            if part
        ).strip() or str(athlete_id)

        self.db.execute("DELETE FROM athlete_profile WHERE athlete_id = ?", (athlete_id,))
        self.db.execute(
            """
            INSERT INTO athlete_profile (
                athlete_id, athlete_name, profile_picture_url, city, state,
                country, sex, premium, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                athlete_id,
                athlete_name,
                athlete.get("profile_medium") or athlete.get("profile"),
                athlete.get("city"),
                athlete.get("state"),
                athlete.get("country"),
                athlete.get("sex"),
                bool(athlete.get("summit") or athlete.get("premium")),
            ),
        )
        return athlete

    def sync_activities(
        self,
        after: Optional[int] = None,
        before: Optional[int] = None,
        per_page: int = 200,
        max_pages: Optional[int] = None,
        hydrate_details: bool = False,
        refresh_analytics: bool = True,
    ) -> SyncResult:
        """Sync Strava activities into raw_strava_activities and stg_activities."""
        started_at = datetime.now(timezone.utc)
        fetched = 0
        loaded = 0
        failed = 0
        athlete_id = self.token_data.athlete_id if self.token_data else 0
        error_message = None
        metrics_rows = 0
        recommendations_created = 0

        try:
            profile = self.sync_profile()
            athlete_id = int(profile["id"])
            activities = self.client.get_all_athlete_activities(
                before=before,
                after=after,
                per_page=per_page,
                max_pages=max_pages,
            )
            fetched = len(activities)

            for activity in activities:
                try:
                    payload = activity
                    if hydrate_details:
                        payload = self.client.get_activity(int(activity["id"]))
                    self.save_activity(payload, athlete_id=athlete_id)
                    loaded += 1
                except Exception as exc:
                    failed += 1
                    logger.exception(
                        "Failed to save Strava activity %s: %s",
                        activity.get("id"),
                        exc,
                    )

            status = "completed" if failed == 0 else "completed_with_errors"
            if refresh_analytics and loaded > 0:
                metrics_rows, recommendations_created = self.refresh_performance_outputs(
                    athlete_id
                )
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            logger.exception("Strava sync failed: %s", exc)

        finished_at = datetime.now(timezone.utc)
        result = SyncResult(
            athlete_id=athlete_id,
            activities_fetched=fetched,
            activities_loaded=loaded,
            activities_failed=failed,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            error_message=error_message,
            analytics_metrics_rows=metrics_rows,
            recommendations_created=recommendations_created,
        )
        self._record_load_history(result)

        if status == "failed":
            raise RuntimeError(error_message)
        return result

    def sync_daily_if_needed(
        self,
        initial_days: int = 90,
        per_page: int = 200,
        max_pages: Optional[int] = None,
        hydrate_details: bool = False,
    ) -> SyncResult:
        """
        Run at most one Strava check per day and load only unseen activities.

        If the database has no activities yet, it performs an initial lookback.
        Otherwise it requests activities since the latest stored activity day and
        persists only activity IDs that are not already in stg_activities.
        """
        started_at = datetime.now(timezone.utc)
        token_athlete_id = self.token_data.athlete_id if self.token_data else 0

        if self._daily_check_already_done():
            result = SyncResult(
                athlete_id=token_athlete_id,
                activities_fetched=0,
                activities_loaded=0,
                activities_failed=0,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                status="skipped_already_checked_today",
            )
            return result

        profile = self.sync_profile()
        athlete_id = int(profile["id"])
        existing_ids = self._existing_activity_ids(athlete_id)
        latest_activity_date = self._latest_activity_date(athlete_id)

        if latest_activity_date is None:
            after = int(time.time()) - initial_days * 24 * 60 * 60
        else:
            latest_day_start = datetime.combine(
                latest_activity_date,
                datetime_time.min,
                tzinfo=timezone.utc,
            )
            after = int(latest_day_start.timestamp())

        activities = self.client.get_all_athlete_activities(
            after=after,
            per_page=per_page,
            max_pages=max_pages,
        )
        new_activities = [
            activity for activity in activities if int(activity["id"]) not in existing_ids
        ]

        loaded = 0
        failed = 0
        for activity in new_activities:
            try:
                payload = activity
                if hydrate_details:
                    payload = self.client.get_activity(int(activity["id"]))
                self.save_activity(payload, athlete_id=athlete_id)
                loaded += 1
            except Exception as exc:
                failed += 1
                logger.exception(
                    "Failed to save daily Strava activity %s: %s",
                    activity.get("id"),
                    exc,
                )

        metrics_rows = 0
        recommendations_created = 0
        if loaded > 0:
            metrics_rows, recommendations_created = self.refresh_performance_outputs(
                athlete_id
            )

        if failed:
            status = "completed_with_errors"
        elif loaded:
            status = "completed"
        else:
            status = "no_new_activities"

        result = SyncResult(
            athlete_id=athlete_id,
            activities_fetched=len(activities),
            activities_loaded=loaded,
            activities_failed=failed,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status=status,
            analytics_metrics_rows=metrics_rows,
            recommendations_created=recommendations_created,
        )
        self._record_load_history(result, load_type="daily_strava_sync")
        return result

    def refresh_performance_outputs(self, athlete_id: int) -> tuple[int, int]:
        """Refresh analytics and coaching outputs for an athlete."""
        analytics_result = PerformanceAnalytics(self.db).refresh_all(athlete_id)
        coach_result = PerformanceCoach(self.db).generate_recommendations(athlete_id)
        return analytics_result.metrics_rows, coach_result.recommendations_created

    def save_activity(self, activity: Dict[str, Any], athlete_id: Optional[int] = None) -> None:
        """Persist one Strava activity into bronze and silver tables."""
        source_activity_id = int(activity["id"])
        resolved_athlete_id = athlete_id or self._extract_athlete_id(activity)
        raw_payload = json.dumps(activity, default=str)

        self.db.execute(
            "DELETE FROM raw_strava_activities WHERE source_activity_id = ?",
            (source_activity_id,),
        )
        self.db.execute(
            """
            INSERT INTO raw_strava_activities (
                source_activity_id, athlete_id, raw_payload, updated_at
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (source_activity_id, resolved_athlete_id, raw_payload),
        )

        staged = self._normalize_activity(activity, resolved_athlete_id)
        self.db.execute(
            "DELETE FROM stg_activities WHERE activity_id = ?",
            (staged["activity_id"],),
        )
        self.db.execute(
            """
            INSERT INTO stg_activities (
                activity_id, athlete_id, activity_name, activity_type, activity_date,
                distance_meters, moving_time_seconds, elapsed_time_seconds,
                average_speed_mps, max_speed_mps, average_heartrate, max_heartrate,
                total_elevation_gain, total_elevation_loss, kudos_count,
                comment_count, photo_count, trainer, commute, manual, private,
                flagged, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                staged["activity_id"],
                staged["athlete_id"],
                staged["activity_name"],
                staged["activity_type"],
                staged["activity_date"],
                staged["distance_meters"],
                staged["moving_time_seconds"],
                staged["elapsed_time_seconds"],
                staged["average_speed_mps"],
                staged["max_speed_mps"],
                staged["average_heartrate"],
                staged["max_heartrate"],
                staged["total_elevation_gain"],
                staged["total_elevation_loss"],
                staged["kudos_count"],
                staged["comment_count"],
                staged["photo_count"],
                staged["trainer"],
                staged["commute"],
                staged["manual"],
                staged["private"],
                staged["flagged"],
            ),
        )

    def _normalize_activity(self, activity: Dict[str, Any], athlete_id: int) -> Dict[str, Any]:
        start_date = activity.get("start_date") or activity.get("start_date_local")
        if not start_date:
            raise ValueError(f"Activity {activity.get('id')} has no start_date")

        activity_datetime = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        return {
            "activity_id": int(activity["id"]),
            "athlete_id": athlete_id,
            "activity_name": activity.get("name") or "Untitled activity",
            "activity_type": activity.get("type") or activity.get("sport_type") or "Unknown",
            "activity_date": activity_datetime.date(),
            "distance_meters": int(round(float(activity.get("distance") or 0))),
            "moving_time_seconds": int(activity.get("moving_time") or 0),
            "elapsed_time_seconds": int(activity.get("elapsed_time") or 0),
            "average_speed_mps": self._optional_float(activity.get("average_speed")),
            "max_speed_mps": self._optional_float(activity.get("max_speed")),
            "average_heartrate": self._optional_int(activity.get("average_heartrate")),
            "max_heartrate": self._optional_int(activity.get("max_heartrate")),
            "total_elevation_gain": self._optional_float(
                activity.get("total_elevation_gain") or activity.get("elevation_gain")
            ),
            "total_elevation_loss": self._optional_float(activity.get("total_elevation_loss")),
            "kudos_count": int(activity.get("kudos_count") or 0),
            "comment_count": int(activity.get("comment_count") or 0),
            "photo_count": int(activity.get("photo_count") or 0),
            "trainer": bool(activity.get("trainer")),
            "commute": bool(activity.get("commute")),
            "manual": bool(activity.get("manual")),
            "private": bool(activity.get("private")),
            "flagged": bool(activity.get("flagged")),
        }

    def _record_load_history(
        self,
        result: SyncResult,
        load_type: str = "strava_sync",
    ) -> None:
        self.db.execute(
            """
            INSERT INTO data_load_history (
                load_type, load_start, load_end, num_records_loaded,
                num_records_failed, status, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                load_type,
                result.started_at.replace(tzinfo=None),
                result.finished_at.replace(tzinfo=None),
                result.activities_loaded,
                result.activities_failed,
                result.status,
                result.error_message,
            ),
        )

    def _daily_check_already_done(self) -> bool:
        row = self.db.fetch_one(
            """
            SELECT COUNT(*)
            FROM data_load_history
            WHERE load_type = 'daily_strava_sync'
              AND CAST(load_start AS DATE) = CURRENT_DATE
              AND status IN ('completed', 'completed_with_errors', 'no_new_activities')
            """
        )
        return bool(row and row[0] > 0)

    def _existing_activity_ids(self, athlete_id: int) -> Set[int]:
        rows = self.db.fetch_all(
            "SELECT activity_id FROM stg_activities WHERE athlete_id = ?",
            (athlete_id,),
        )
        return {int(row[0]) for row in rows}

    def _latest_activity_date(self, athlete_id: int) -> Optional[date]:
        row = self.db.fetch_one(
            "SELECT MAX(activity_date) FROM stg_activities WHERE athlete_id = ?",
            (athlete_id,),
        )
        return row[0] if row and row[0] else None

    def close(self) -> None:
        """Close owned resources."""
        self.client.close()
        if self._owns_db:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def _extract_athlete_id(activity: Dict[str, Any]) -> int:
        athlete = activity.get("athlete") or {}
        if isinstance(athlete, dict) and athlete.get("id"):
            return int(athlete["id"])
        raise ValueError(f"Activity {activity.get('id')} does not include athlete_id")

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        return None if value is None else float(value)

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        return None if value is None else int(round(float(value)))


def sync_recent_activities(days: int = 30, **kwargs) -> SyncResult:
    """Convenience function to sync recent Strava activities."""
    after = int(time.time()) - days * 24 * 60 * 60
    with StravaConnector() as connector:
        return connector.sync_activities(after=after, **kwargs)


def sync_daily_if_needed(**kwargs) -> SyncResult:
    """Convenience function for the daily incremental sync policy."""
    with StravaConnector() as connector:
        return connector.sync_daily_if_needed(**kwargs)
