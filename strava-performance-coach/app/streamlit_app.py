"""Streamlit dashboard for Strava Performance Coach."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.auth import StravaOAuth
from src.connector import StravaConnector
from src.database.create_database import DatabaseInitializer
from src.database.db_connection import get_connection_context
from src.metrics import PerformanceAnalytics
from src.coach import PerformanceCoach


st.set_page_config(
    page_title="Strava Performance Coach",
    page_icon="SPC",
    layout="wide",
    initial_sidebar_state="expanded",
)


def ensure_database() -> None:
    """Apply the idempotent schema so existing databases receive new tables."""
    DatabaseInitializer(settings.duckdb_path).initialize(with_mock_data=False)


@st.cache_data(ttl=60)
def load_dataframe(query: str) -> pd.DataFrame:
    with get_connection_context() as conn:
        return conn.fetch_df(query)


def run_daily_sync() -> str:
    with StravaConnector() as connector:
        result = connector.sync_daily_if_needed()
    load_dataframe.clear()
    return (
        f"{result.status}: fetched={result.activities_fetched}, "
        f"loaded={result.activities_loaded}, failed={result.activities_failed}, "
        f"metrics={result.analytics_metrics_rows}, "
        f"recommendations={result.recommendations_created}"
    )


def refresh_analytics() -> str:
    with get_connection_context() as conn:
        athlete_row = conn.fetch_one("SELECT athlete_id FROM athlete_profile LIMIT 1")
        athlete_id = athlete_row[0] if athlete_row else None
        analytics = PerformanceAnalytics(conn).refresh_all(athlete_id)
        coach = PerformanceCoach(conn).generate_recommendations(athlete_id)

    load_dataframe.clear()
    return (
        f"metrics={analytics.metrics_rows}, daily={analytics.daily_rows}, "
        f"weekly={analytics.weekly_rows}, recommendations={coach.recommendations_created}"
    )


ensure_database()

st.title("Strava Performance Coach")
st.caption("Daily Strava sync, performance analytics, and explainable coaching.")

with st.sidebar:
    st.header("Data Sync")

    oauth = StravaOAuth()
    if oauth.is_authenticated():
        st.success("Strava tokens available.")
        if st.button("Check Strava Today", width="stretch"):
            try:
                st.info(run_daily_sync())
            except Exception as exc:
                st.error(f"Daily sync failed: {exc}")
    else:
        st.warning("Strava is not authenticated yet.")
        st.link_button("Authorize Strava", oauth.generate_authorization_url())

    if st.button("Refresh Analytics", width="stretch"):
        try:
            st.info(refresh_analytics())
        except Exception as exc:
            st.error(f"Analytics refresh failed: {exc}")

    st.markdown("---")
    st.write(f"Database: `{settings.duckdb_path}`")


overview = load_dataframe(
    """
    SELECT
        COUNT(*) AS activities,
        ROUND(COALESCE(SUM(distance_km), 0), 2) AS distance_km,
        ROUND(COALESCE(SUM(moving_time_minutes), 0), 1) AS moving_minutes,
        MAX(activity_date) AS latest_activity
    FROM stg_activities
    """
)

metrics = load_dataframe(
    """
    SELECT
        ROUND(COALESCE(AVG(performance_score), 0), 1) AS avg_performance,
        ROUND(COALESCE(SUM(training_load), 0), 1) AS total_load,
        ROUND(COALESCE(AVG(fatigue_impact), 0), 1) AS avg_fatigue
    FROM fct_activity_metrics
    """
)

col1, col2, col3, col4 = st.columns(4)
row = overview.iloc[0]
metric_row = metrics.iloc[0]
col1.metric("Activities", int(row["activities"]))
col2.metric("Distance", f"{row['distance_km']:.1f} km")
col3.metric("Performance", f"{metric_row['avg_performance']:.1f}")
col4.metric("Training Load", f"{metric_row['total_load']:.0f}")

if int(row["activities"]) == 0:
    st.info("No activities loaded yet. Authenticate Strava and run the daily check.")
    st.stop()

tab_overview, tab_activities, tab_profile, tab_coach = st.tabs(
    ["Analytics", "Activities", "Profile", "Coach"]
)

with tab_overview:
    daily = load_dataframe(
        """
        SELECT summary_date, total_distance_km, total_moving_time_minutes,
               avg_performance_score, total_training_load, daily_score
        FROM daily_summary
        ORDER BY summary_date
        """
    )

    weekly = load_dataframe(
        """
        SELECT week_start, total_distance_km, total_training_load,
               weekly_score, fatigue_level, recovery_status
        FROM weekly_summary
        ORDER BY week_start
        """
    )

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.subheader("Daily Performance")
        if daily.empty:
            st.info("Refresh analytics to build daily performance.")
        else:
            st.plotly_chart(
                px.line(
                    daily,
                    x="summary_date",
                    y="avg_performance_score",
                    markers=True,
                    labels={
                        "summary_date": "Date",
                        "avg_performance_score": "Performance Score",
                    },
                ),
                width="stretch",
            )

    with chart_col2:
        st.subheader("Training Load")
        if weekly.empty:
            st.info("Refresh analytics to build weekly load.")
        else:
            st.plotly_chart(
                px.bar(
                    weekly,
                    x="week_start",
                    y="total_training_load",
                    color="fatigue_level",
                    labels={
                        "week_start": "Week",
                        "total_training_load": "Training Load",
                        "fatigue_level": "Fatigue",
                    },
                ),
                width="stretch",
            )

with tab_activities:
    activities = load_dataframe(
        """
        SELECT
            a.activity_id,
            a.activity_date,
            a.activity_name,
            a.activity_type,
            ROUND(a.distance_km, 2) AS distance_km,
            ROUND(a.moving_time_minutes, 1) AS moving_time_minutes,
            ROUND(a.average_speed_kmh, 2) AS average_speed_kmh,
            a.average_heartrate,
            ROUND(a.average_pace_min_km, 2) AS average_pace_min_km,
            ROUND(a.total_elevation_gain, 1) AS total_elevation_gain,
            m.performance_score,
            m.training_load,
            m.intensity_level,
            m.fatigue_impact,
            m.recovery_indicator,
            EXISTS (
                SELECT 1
                FROM activity_streams s
                WHERE s.activity_id = a.activity_id
            ) AS has_gps
        FROM stg_activities a
        LEFT JOIN fct_activity_metrics m ON a.activity_id = m.activity_id
        ORDER BY a.activity_date DESC, a.activity_id DESC
        """
    )

    filter_col1, filter_col2 = st.columns([2, 1])
    available_types = sorted(activities["activity_type"].dropna().unique().tolist())
    with filter_col1:
        type_filter = st.multiselect(
            "Activity type",
            available_types,
            default=available_types,
        )
    with filter_col2:
        gps_only = st.checkbox("Only activities with GPS stream")

    filtered_activities = activities.copy()
    if type_filter:
        filtered_activities = filtered_activities[
            filtered_activities["activity_type"].isin(type_filter)
        ]
    if gps_only:
        filtered_activities = filtered_activities[filtered_activities["has_gps"]]

    if filtered_activities.empty:
        st.info("No activities match the current filters.")
    else:
        labels = {
            row.activity_id: (
                f"{row.activity_date} | {row.activity_type} | "
                f"{row.distance_km:.2f} km | {row.activity_name}"
            )
            for row in filtered_activities.itertuples(index=False)
        }
        selected_activity_id = st.selectbox(
            "Activity detail",
            filtered_activities["activity_id"].tolist(),
            format_func=lambda activity_id: labels.get(activity_id, str(activity_id)),
        )
        selected = filtered_activities[
            filtered_activities["activity_id"] == selected_activity_id
        ].iloc[0]

        detail_col1, detail_col2, detail_col3, detail_col4, detail_col5 = st.columns(5)
        detail_col1.metric("Distance", f"{selected['distance_km']:.2f} km")
        detail_col2.metric("Moving Time", f"{selected['moving_time_minutes']:.1f} min")
        detail_col3.metric("Avg Speed", f"{selected['average_speed_kmh']:.1f} km/h")
        pace = selected["average_pace_min_km"]
        detail_col4.metric("Avg Pace", "-" if pd.isna(pace) else f"{pace:.2f} min/km")
        performance = selected["performance_score"]
        detail_col5.metric(
            "Performance",
            "-" if pd.isna(performance) else f"{int(performance)} / 100",
        )

        eval_col1, eval_col2, eval_col3 = st.columns(3)
        eval_col1.write(f"**Intensity:** {selected['intensity_level'] or '-'}")
        eval_col2.write(f"**Recovery:** {selected['recovery_indicator'] or '-'}")
        eval_col3.write(
            "**GPS stream:** available" if selected["has_gps"] else "**GPS stream:** unavailable"
        )

        streams = load_dataframe(
            f"""
            SELECT
                point_index,
                point_time,
                latitude,
                longitude,
                elevation_m,
                distance_m / 1000.0 AS distance_km,
                speed_mps * 3.6 AS speed_kmh,
                heartrate,
                pace_min_km,
                source_file
            FROM activity_streams
            WHERE activity_id = {int(selected_activity_id)}
            ORDER BY point_index
            """
        )

        if streams.empty:
            st.info(
                "No GPS stream available for this activity. CSV metrics are available; "
                "FIT/FIT.GZ files need FIT parsing support to extract route points."
            )
        else:
            map_points = streams.dropna(subset=["latitude", "longitude"])
            if not map_points.empty:
                center = {
                    "lat": map_points["latitude"].mean(),
                    "lon": map_points["longitude"].mean(),
                }
                route_fig = go.Figure(
                    go.Scattermapbox(
                        lat=map_points["latitude"],
                        lon=map_points["longitude"],
                        mode="lines",
                        line={"width": 4, "color": "#fc4c02"},
                        name="Route",
                    )
                )
                route_fig.update_layout(
                    mapbox={
                        "style": "open-street-map",
                        "center": center,
                        "zoom": 11,
                    },
                    margin={"l": 0, "r": 0, "t": 0, "b": 0},
                    height=450,
                    showlegend=False,
                )
                st.plotly_chart(route_fig, width="stretch")

            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.plotly_chart(
                    px.line(
                        streams,
                        x="distance_km",
                        y="elevation_m",
                        labels={
                            "distance_km": "Distance (km)",
                            "elevation_m": "Elevation (m)",
                        },
                        title="Elevation",
                    ),
                    width="stretch",
                )
                st.plotly_chart(
                    px.line(
                        streams,
                        x="distance_km",
                        y="pace_min_km",
                        labels={
                            "distance_km": "Distance (km)",
                            "pace_min_km": "Pace (min/km)",
                        },
                        title="Pace",
                    ),
                    width="stretch",
                )
            with chart_col2:
                st.plotly_chart(
                    px.line(
                        streams,
                        x="distance_km",
                        y="speed_kmh",
                        labels={
                            "distance_km": "Distance (km)",
                            "speed_kmh": "Speed (km/h)",
                        },
                        title="Speed",
                    ),
                    width="stretch",
                )
                if streams["heartrate"].notna().any():
                    st.plotly_chart(
                        px.line(
                            streams,
                            x="distance_km",
                            y="heartrate",
                            labels={
                                "distance_km": "Distance (km)",
                                "heartrate": "Heart Rate (bpm)",
                            },
                            title="Heart Rate",
                        ),
                        width="stretch",
                    )
                else:
                    st.info("This stream has no heart-rate samples.")

        st.subheader("Filtered Activities")
        st.dataframe(
            filtered_activities.drop(columns=["activity_id"]),
            width="stretch",
            hide_index=True,
        )

with tab_profile:
    profile = load_dataframe(
        """
        SELECT athlete_id, athlete_name, city, state, country, sex, premium, updated_at
        FROM athlete_profile
        LIMIT 1
        """
    )
    by_type = load_dataframe(
        """
        SELECT
            activity_type,
            COUNT(*) AS activities,
            ROUND(SUM(distance_km), 2) AS distance_km,
            ROUND(SUM(moving_time_minutes), 1) AS moving_minutes,
            ROUND(AVG(average_speed_kmh), 2) AS avg_speed_kmh,
            ROUND(AVG(average_heartrate), 0) AS avg_heartrate
        FROM stg_activities
        GROUP BY activity_type
        ORDER BY activities DESC
        """
    )

    if profile.empty:
        st.info("No athlete profile loaded yet.")
    else:
        athlete = profile.iloc[0]
        st.subheader(athlete["athlete_name"])
        profile_col1, profile_col2, profile_col3 = st.columns(3)
        profile_col1.write(f"**Athlete ID:** {athlete['athlete_id']}")
        profile_col2.write(
            f"**Location:** {athlete['city'] or '-'}, {athlete['country'] or '-'}"
        )
        profile_col3.write(f"**Sex:** {athlete['sex'] or '-'}")

    st.subheader("Activity Profile")
    st.dataframe(by_type, width="stretch", hide_index=True)

with tab_coach:
    recommendations = load_dataframe(
        """
        SELECT priority_level, recommendation_type, recommendation_text,
               action_suggested, confidence_score, created_at
        FROM coach_recommendations
        WHERE status = 'pending'
        ORDER BY
            CASE priority_level
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                ELSE 3
            END,
            confidence_score DESC,
            created_at DESC
        LIMIT 20
        """
    )

    if recommendations.empty:
        st.info("No pending recommendations. Refresh analytics after loading activities.")
    else:
        for rec in recommendations.itertuples(index=False):
            with st.container(border=True):
                st.write(f"**{rec.priority_level.upper()}** | {rec.recommendation_type}")
                st.write(rec.recommendation_text)
                st.caption(
                    f"Suggested action: {rec.action_suggested} "
                    f"| confidence={rec.confidence_score:.0%}"
                )
