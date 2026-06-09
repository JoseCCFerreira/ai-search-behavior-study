"""Streamlit dashboard for Strava Performance Coach."""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.database.create_database import DatabaseInitializer
from src.database.db_connection import get_connection_context
from src.processing import StravaExportImporter
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


def import_uploaded_file(
    uploaded_file,
    only_new: bool = True,
    activity_type: str = "Run",
) -> str:
    upload_dir = settings.raw_data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = None
    original_name = getattr(uploaded_file, "name", "activity_upload")
    suffixes = "".join(Path(original_name).suffixes) or ".upload"

    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffixes,
            prefix="strava_upload_",
            dir=upload_dir,
            delete=False,
        ) as temp_file:
            temp_file.write(uploaded_file.getbuffer())
            temp_path = Path(temp_file.name)

        if original_name.lower().endswith(".zip"):
            with StravaExportImporter(temp_path, database_path=settings.duckdb_path) as importer:
                result = importer.import_export(refresh_outputs=True, only_new=only_new)
                importer.db.vacuum()

            load_dataframe.clear()
            return (
                f"loaded={result.activities_loaded}, skipped={result.activities_skipped}, "
                f"failed={result.activities_failed}, streams={result.stream_points_loaded}, "
                f"metrics={result.metrics_rows}, recommendations={result.recommendations_created}"
            )

        result = import_single_activity_file(
            temp_path,
            original_name=original_name,
            activity_type=activity_type,
            only_new=only_new,
        )

        load_dataframe.clear()
        return result
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def import_single_activity_file(
    path: Path,
    original_name: str,
    activity_type: str,
    only_new: bool,
) -> str:
    raw_payload = path.read_bytes()
    activity_id = int(hashlib.sha1(raw_payload).hexdigest()[:15], 16)
    lower_name = original_name.lower()
    payload = gzip.decompress(raw_payload) if lower_name.endswith(".gz") else raw_payload

    if lower_name.endswith((".gpx", ".gpx.gz")):
        points = StravaExportImporter._parse_gpx_points(activity_id, payload, original_name)
    elif lower_name.endswith((".tcx", ".tcx.gz")):
        points = StravaExportImporter._parse_tcx_points(activity_id, payload, original_name)
    elif lower_name.endswith((".fit", ".fit.gz", ".git")):
        points = StravaExportImporter._parse_fit_points(activity_id, payload, original_name)
    else:
        raise ValueError("Unsupported file type. Use .zip, .gpx, .tcx, .fit, or .gz.")

    if not points:
        raise ValueError("No GPS/activity points were found in this file.")

    point_times = [point["point_time"] for point in points if point["point_time"] is not None]
    first_time = min(point_times) if point_times else None
    last_time = max(point_times) if point_times else None
    distance_m = max((point["distance_m"] or 0 for point in points), default=0)
    duration_s = int((last_time - first_time).total_seconds()) if first_time and last_time else 0
    speeds = [point["speed_mps"] for point in points if point["speed_mps"] is not None]
    heart_rates = [point["heartrate"] for point in points if point["heartrate"] is not None]
    elevations = [point["elevation_m"] for point in points if point["elevation_m"] is not None]
    elevation_gain = 0.0
    elevation_loss = 0.0
    for previous, current in zip(elevations, elevations[1:]):
        delta = current - previous
        if delta > 0:
            elevation_gain += delta
        else:
            elevation_loss += abs(delta)

    average_speed = (distance_m / duration_s) if duration_s > 0 and distance_m > 0 else (
        sum(speeds) / len(speeds) if speeds else None
    )
    activity_name = Path(original_name).name
    for suffix in [".fit.gz", ".gpx.gz", ".tcx.gz", ".fit", ".gpx", ".tcx", ".git"]:
        if activity_name.lower().endswith(suffix):
            activity_name = activity_name[: -len(suffix)]
            break

    with get_connection_context(settings.duckdb_path) as conn:
        athlete_row = conn.fetch_one("SELECT athlete_id FROM athlete_profile LIMIT 1")
        athlete_id = int(athlete_row[0]) if athlete_row else 0
        if athlete_row is None:
            conn.insert_records(
                "athlete_profile",
                [
                    {
                        "athlete_id": athlete_id,
                        "athlete_name": "Local Athlete",
                        "premium": False,
                    }
                ],
            )

        exists = conn.fetch_one(
            "SELECT COUNT(*) FROM stg_activities WHERE activity_id = ?",
            (activity_id,),
        )[0]
        if exists and only_new:
            conn.vacuum()
            return "loaded=0, skipped=1, failed=0, streams=0, metrics=0, recommendations=0"

        conn.execute("DELETE FROM fct_activity_metrics WHERE activity_id = ?", (activity_id,))
        conn.execute("DELETE FROM activity_streams WHERE activity_id = ?", (activity_id,))
        conn.execute("DELETE FROM stg_activities WHERE activity_id = ?", (activity_id,))
        conn.execute(
            "DELETE FROM raw_strava_activities WHERE source_activity_id = ?",
            (activity_id,),
        )
        conn.insert_records(
            "raw_strava_activities",
            [
                {
                    "source_activity_id": activity_id,
                    "athlete_id": athlete_id,
                    "raw_payload": json.dumps(
                        {
                            "source": "single_file_upload",
                            "filename": original_name,
                            "activity_type": activity_type,
                            "points": len(points),
                        }
                    ),
                }
            ],
        )
        conn.insert_records(
            "stg_activities",
            [
                {
                    "activity_id": activity_id,
                    "athlete_id": athlete_id,
                    "activity_name": activity_name or f"Activity {activity_id}",
                    "activity_type": activity_type,
                    "activity_date": first_time.date() if first_time else date.today(),
                    "distance_meters": int(round(distance_m or 0)),
                    "moving_time_seconds": duration_s,
                    "elapsed_time_seconds": duration_s,
                    "average_speed_mps": average_speed,
                    "max_speed_mps": max(speeds) if speeds else None,
                    "average_heartrate": int(round(sum(heart_rates) / len(heart_rates)))
                    if heart_rates
                    else None,
                    "max_heartrate": max(heart_rates) if heart_rates else None,
                    "total_elevation_gain": elevation_gain,
                    "total_elevation_loss": elevation_loss,
                    "calories": None,
                    "kudos_count": 0,
                    "comment_count": 0,
                    "photo_count": 0,
                    "trainer": False,
                    "commute": False,
                    "manual": False,
                    "private": False,
                    "flagged": False,
                }
            ],
        )
        batch_size = 5000
        for start in range(0, len(points), batch_size):
            conn.insert_records("activity_streams", points[start : start + batch_size])

        analytics = PerformanceAnalytics(conn).refresh_all(athlete_id)
        coach = PerformanceCoach(conn).generate_recommendations(athlete_id)
        conn.vacuum()

    return (
        f"loaded=1, skipped=0, failed=0, streams={len(points)}, "
        f"metrics={analytics.metrics_rows}, recommendations={coach.recommendations_created}"
    )


def format_minutes(minutes: float) -> str:
    hours = (minutes or 0) / 60
    return f"{hours:,.1f} h"


def format_number(value: float, suffix: str = "") -> str:
    return f"{(value or 0):,.0f}{suffix}"


def add_year_variation(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    annual = df.copy()
    for column in columns:
        annual[f"{column}_yoy"] = annual[column].pct_change() * 100
    return annual


def format_percent(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:+.1f}%"


def add_dashboard_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 3rem;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 14px 16px;
        }
        [data-testid="stMetricLabel"] {
            color: #4b5563;
        }
        div[data-testid="stTabs"] button {
            font-weight: 600;
        }
        .section-note {
            color: #5f6c7b;
            margin-top: -0.5rem;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_stat_summary(df: pd.DataFrame) -> pd.DataFrame:
    metrics = {
        "Distance (km)": "distance_km",
        "Moving time (min)": "moving_time_minutes",
        "Elevation gain (m)": "total_elevation_gain",
        "Calories": "calories",
        "Avg speed (km/h)": "average_speed_kmh",
        "Pace (min/km)": "average_pace_min_km",
        "Heart rate (bpm)": "average_heartrate",
        "Performance": "performance_score",
        "Training load": "training_load",
    }
    rows = []
    for label, column in metrics.items():
        series = df[column].dropna()
        if series.empty:
            continue
        rows.append(
            {
                "metric": label,
                "count": int(series.count()),
                "mean": series.mean(),
                "median": series.median(),
                "p25": series.quantile(0.25),
                "p75": series.quantile(0.75),
                "min": series.min(),
                "max": series.max(),
                "std": series.std(),
            }
        )
    return pd.DataFrame(rows).round(2)


def render_geo_map(
    geo_df: pd.DataFrame,
    color_metric: str,
    title: str,
    color_scale: str,
) -> None:
    if geo_df.empty:
        st.info("No GPS points available for the selected filters.")
        return

    center = {"lat": geo_df["latitude"].mean(), "lon": geo_df["longitude"].mean()}
    fig = px.scatter_mapbox(
        geo_df,
        lat="latitude",
        lon="longitude",
        size="samples",
        color=color_metric,
        hover_data={
            "activity_type": True,
            "samples": True,
            "avg_performance": ":.1f",
            "avg_speed_kmh": ":.1f",
            "avg_heartrate": ":.0f",
            "latitude": False,
            "longitude": False,
        },
        color_continuous_scale=color_scale,
        zoom=9,
        height=520,
        title=title,
    )
    fig.update_layout(
        mapbox={"style": "open-street-map", "center": center},
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
    )
    st.plotly_chart(fig, width="stretch")


def render_activity_heatmap(df: pd.DataFrame, activity_type: str) -> None:
    activity_df = df[df["activity_type"] == activity_type].copy()
    if activity_df.empty:
        st.info(f"No {activity_type.lower()} activities in the selected filters.")
        return

    daily = (
        activity_df.groupby("activity_date", as_index=False)
        .agg(distance_km=("distance_km", "sum"))
        .sort_values("activity_date")
    )
    daily["activity_date"] = pd.to_datetime(daily["activity_date"])
    daily["week"] = daily["activity_date"].dt.isocalendar().week.astype(int)
    daily["weekday"] = daily["activity_date"].dt.day_name()
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    heatmap = (
        daily.pivot_table(
            index="weekday",
            columns="week",
            values="distance_km",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(weekday_order)
    )

    fig = px.imshow(
        heatmap,
        aspect="auto",
        color_continuous_scale="Oranges" if activity_type == "Ride" else "Blues",
        labels={"x": "ISO week", "y": "Weekday", "color": "km"},
        title=f"{activity_type} heatmap by week",
    )
    fig.update_layout(height=330, margin={"l": 0, "r": 0, "t": 45, "b": 0})
    st.plotly_chart(fig, width="stretch")


ensure_database()
add_dashboard_style()

st.title("Strava Performance Coach")
st.caption("Offline activity database, performance analytics, GPS maps, and explainable coaching.")

with st.sidebar:
    st.header("Local Database")
    if st.button("Refresh Analytics", width="stretch"):
        try:
            st.info(refresh_analytics())
        except Exception as exc:
            st.error(f"Analytics refresh failed: {exc}")

    st.header("Upload Activities")
    uploaded_export = st.file_uploader(
        "Strava export or activity file",
        type=["zip", "gpx", "fit", "tcx", "gz", "git"],
        accept_multiple_files=False,
    )
    upload_activity_type = st.selectbox(
        "Type for single activity files",
        ["Run", "Ride", "Walk", "Hike", "Swim", "Workout"],
    )
    only_new_upload = st.checkbox("Import only new activities", value=True)
    if st.button(
        "Import Uploaded File",
        width="stretch",
        disabled=uploaded_export is None,
    ):
        try:
            with st.spinner("Importing activities and optimizing database..."):
                st.success(
                    import_uploaded_file(
                        uploaded_export,
                        only_new=only_new_upload,
                        activity_type=upload_activity_type,
                    )
                )
        except Exception as exc:
            st.error(f"Upload import failed: {exc}")

    st.markdown("---")
    st.write(f"Database: `{settings.duckdb_path}`")


activities_all = load_dataframe(
    """
    SELECT
        a.activity_id,
        a.activity_date,
        EXTRACT(year FROM a.activity_date) AS activity_year,
        EXTRACT(month FROM a.activity_date) AS activity_month_num,
        EXTRACT(day FROM a.activity_date) AS activity_day,
        EXTRACT(week FROM a.activity_date) AS activity_week,
        DATE_TRUNC('month', a.activity_date) AS activity_month,
        a.activity_name,
        a.activity_type,
        ROUND(a.distance_km, 2) AS distance_km,
        ROUND(a.moving_time_minutes, 1) AS moving_time_minutes,
        ROUND(a.elapsed_time_minutes, 1) AS elapsed_time_minutes,
        ROUND(a.average_speed_kmh, 2) AS average_speed_kmh,
        a.average_heartrate,
        ROUND(a.average_pace_min_km, 2) AS average_pace_min_km,
        ROUND(a.total_elevation_gain, 1) AS total_elevation_gain,
        ROUND(COALESCE(a.calories, 0), 1) AS calories,
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
    FROM stg_activities
    a LEFT JOIN fct_activity_metrics m ON a.activity_id = m.activity_id
    ORDER BY a.activity_date DESC, a.activity_id DESC
    """
)

geo_all = load_dataframe(
    """
    SELECT
        ROUND(s.latitude, 3) AS latitude,
        ROUND(s.longitude, 3) AS longitude,
        a.activity_type,
        EXTRACT(year FROM a.activity_date) AS activity_year,
        EXTRACT(month FROM a.activity_date) AS activity_month_num,
        COUNT(*) AS samples,
        AVG(m.performance_score) AS avg_performance,
        AVG(s.speed_mps * 3.6) AS avg_speed_kmh,
        AVG(s.heartrate) AS avg_heartrate
    FROM activity_streams s
    JOIN stg_activities a ON a.activity_id = s.activity_id
    LEFT JOIN fct_activity_metrics m ON m.activity_id = a.activity_id
    WHERE s.latitude IS NOT NULL
      AND s.longitude IS NOT NULL
    GROUP BY
        ROUND(s.latitude, 3),
        ROUND(s.longitude, 3),
        a.activity_type,
        EXTRACT(year FROM a.activity_date),
        EXTRACT(month FROM a.activity_date)
    ORDER BY samples DESC
    """
)

if activities_all.empty:
    st.info("No activities loaded yet. Authenticate Strava and run the daily check.")
    st.stop()

activities_all["activity_date"] = pd.to_datetime(activities_all["activity_date"])
activities_all["activity_month"] = pd.to_datetime(activities_all["activity_month"])
available_years = sorted(activities_all["activity_year"].dropna().astype(int).unique().tolist())
available_months = sorted(
    activities_all["activity_month_num"].dropna().astype(int).unique().tolist()
)
available_types = sorted(activities_all["activity_type"].dropna().unique().tolist())
month_labels = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

with st.sidebar:
    st.markdown("---")
    st.header("Dashboard Filters")
    selected_years = st.multiselect("Years", available_years, default=available_years)
    selected_months = st.multiselect(
        "Months",
        available_months,
        default=available_months,
        format_func=lambda month: month_labels.get(month, str(month)),
    )
    min_date = activities_all["activity_date"].min().date()
    max_date = activities_all["activity_date"].max().date()
    selected_date_range = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    selected_types = st.multiselect(
        "Activity types",
        available_types,
        default=available_types,
    )

filtered = activities_all.copy()
if selected_years:
    filtered = filtered[filtered["activity_year"].astype(int).isin(selected_years)]
if selected_months:
    filtered = filtered[filtered["activity_month_num"].astype(int).isin(selected_months)]
if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
    start_date, end_date = selected_date_range
    filtered = filtered[
        (filtered["activity_date"].dt.date >= start_date)
        & (filtered["activity_date"].dt.date <= end_date)
    ]
if selected_types:
    filtered = filtered[filtered["activity_type"].isin(selected_types)]

geo_filtered = geo_all.copy()
if not geo_filtered.empty:
    if selected_years:
        geo_filtered = geo_filtered[
            geo_filtered["activity_year"].astype(int).isin(selected_years)
        ]
    if selected_months:
        geo_filtered = geo_filtered[
            geo_filtered["activity_month_num"].astype(int).isin(selected_months)
        ]
    if selected_types:
        geo_filtered = geo_filtered[geo_filtered["activity_type"].isin(selected_types)]

if filtered.empty:
    st.info("No activities match the selected filters.")
    st.stop()

total_activities = len(filtered)
total_distance = filtered["distance_km"].sum()
total_moving = filtered["moving_time_minutes"].sum()
total_calories = filtered["calories"].sum()
total_elevation = filtered["total_elevation_gain"].sum()
avg_performance = filtered["performance_score"].dropna().mean()

kpi_cols = st.columns(6)
kpi_cols[0].metric("Activities", f"{total_activities:,}")
kpi_cols[1].metric("Distance", f"{total_distance:,.1f} km")
kpi_cols[2].metric("Moving Time", format_minutes(total_moving))
kpi_cols[3].metric("Calories", format_number(total_calories))
kpi_cols[4].metric("Elevation Gain", format_number(total_elevation, " m"))
kpi_cols[5].metric(
    "Performance",
    "-" if pd.isna(avg_performance) else f"{avg_performance:.1f}",
)

(
    tab_home,
    tab_years,
    tab_stats,
    tab_geo,
    tab_heatmaps,
    tab_activities,
    tab_profile,
    tab_coach,
) = st.tabs(
    [
        "Overview",
        "Timeline",
        "Statistics",
        "Geo Map",
        "Heatmaps",
        "Activities",
        "Profile",
        "Coach",
    ]
)

with tab_home:
    current_year = date.today().year
    today = pd.Timestamp(date.today())
    year_start = pd.Timestamp(date(current_year, 1, 1))
    days_elapsed = max(1, (today - year_start).days + 1)
    days_in_year = 366 if pd.Timestamp(date(current_year, 12, 31)).dayofyear == 366 else 365
    projection_base = activities_all[
        activities_all["activity_year"].astype(int).eq(current_year)
    ].copy()
    if selected_types:
        projection_base = projection_base[projection_base["activity_type"].isin(selected_types)]

    previous_30_start = today - pd.Timedelta(days=60)
    last_30_start = today - pd.Timedelta(days=30)
    trend_base = activities_all.copy()
    if selected_types:
        trend_base = trend_base[trend_base["activity_type"].isin(selected_types)]
    previous_30 = trend_base[
        (trend_base["activity_date"] >= previous_30_start)
        & (trend_base["activity_date"] < last_30_start)
    ]
    last_30 = trend_base[
        (trend_base["activity_date"] >= last_30_start)
        & (trend_base["activity_date"] <= today)
    ]

    st.subheader(f"Current Year Projection ({current_year})")
    projection_cols = st.columns(5)
    ytd_distance = projection_base["distance_km"].sum()
    ytd_hours = projection_base["moving_time_minutes"].sum() / 60
    ytd_calories = projection_base["calories"].sum()
    ytd_elevation = projection_base["total_elevation_gain"].sum()
    ytd_performance = projection_base["performance_score"].mean()
    projection_factor = days_in_year / days_elapsed
    projection_cols[0].metric(
        "YTD Distance",
        f"{ytd_distance:,.1f} km",
        f"proj. {ytd_distance * projection_factor:,.0f} km",
    )
    projection_cols[1].metric(
        "YTD Time",
        f"{ytd_hours:,.1f} h",
        f"proj. {ytd_hours * projection_factor:,.0f} h",
    )
    projection_cols[2].metric(
        "YTD Calories",
        format_number(ytd_calories),
        f"proj. {ytd_calories * projection_factor:,.0f}",
    )
    projection_cols[3].metric(
        "YTD Elevation",
        format_number(ytd_elevation, " m"),
        f"proj. {ytd_elevation * projection_factor:,.0f} m",
    )
    projection_cols[4].metric(
        "YTD Performance",
        "-" if pd.isna(ytd_performance) else f"{ytd_performance:.1f}",
    )

    trend_cols = st.columns(4)
    trend_metrics = [
        ("30d Distance", "distance_km", "km"),
        ("30d Time", "moving_time_minutes", "min"),
        ("30d Elevation", "total_elevation_gain", "m"),
        ("30d Performance", "performance_score", ""),
    ]
    for col, (label, metric, suffix) in zip(trend_cols, trend_metrics):
        current_value = (
            last_30[metric].mean() if metric == "performance_score" else last_30[metric].sum()
        )
        previous_value = (
            previous_30[metric].mean()
            if metric == "performance_score"
            else previous_30[metric].sum()
        )
        delta = None
        if previous_value and not pd.isna(previous_value):
            delta = ((current_value - previous_value) / previous_value) * 100
        display_value = current_value / 60 if metric == "moving_time_minutes" else current_value
        display_suffix = "h" if metric == "moving_time_minutes" else suffix
        col.metric(
            label,
            f"{display_value:,.1f} {display_suffix}".strip(),
            format_percent(delta),
        )

    monthly = (
        filtered.groupby("activity_month", as_index=False)
        .agg(
            distance_km=("distance_km", "sum"),
            moving_time_minutes=("moving_time_minutes", "sum"),
            calories=("calories", "sum"),
            total_elevation_gain=("total_elevation_gain", "sum"),
            performance_score=("performance_score", "mean"),
            training_load=("training_load", "sum"),
        )
        .sort_values("activity_month")
    )
    by_type = (
        filtered.groupby("activity_type", as_index=False)
        .agg(
            activities=("activity_id", "count"),
            distance_km=("distance_km", "sum"),
            moving_time_minutes=("moving_time_minutes", "sum"),
            calories=("calories", "sum"),
            elevation_gain=("total_elevation_gain", "sum"),
            performance_score=("performance_score", "mean"),
        )
        .sort_values("distance_km", ascending=False)
    )

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.plotly_chart(
            px.area(
                monthly,
                x="activity_month",
                y="distance_km",
                labels={"activity_month": "Month", "distance_km": "Distance (km)"},
                title="Monthly Distance",
            ),
            width="stretch",
        )

    with chart_col2:
        st.plotly_chart(
            px.bar(
                by_type,
                x="activity_type",
                y="moving_time_minutes",
                color="activity_type",
                labels={
                    "activity_type": "Type",
                    "moving_time_minutes": "Moving time (min)",
                },
                title="Time by Activity Type",
            ),
            width="stretch",
        )

    chart_col3, chart_col4 = st.columns(2)
    with chart_col3:
        st.plotly_chart(
            px.line(
                monthly,
                x="activity_month",
                y=["calories", "total_elevation_gain"],
                labels={"activity_month": "Month", "value": "Total", "variable": "Metric"},
                title="Calories and Elevation Gain",
            ),
            width="stretch",
        )
    with chart_col4:
        st.plotly_chart(
            px.line(
                monthly,
                x="activity_month",
                y="performance_score",
                markers=True,
                labels={
                    "activity_month": "Month",
                    "performance_score": "Performance score",
                },
                title="Performance Trend",
            ),
            width="stretch",
        )

    chart_col5, chart_col6 = st.columns(2)
    with chart_col5:
        st.plotly_chart(
            px.sunburst(
                filtered,
                path=["activity_type", "intensity_level"],
                values="distance_km",
                title="Distance Composition by Type and Intensity",
            ),
            width="stretch",
        )
    with chart_col6:
        st.plotly_chart(
            px.scatter(
                filtered,
                x="distance_km",
                y="performance_score",
                color="activity_type",
                size="training_load",
                hover_name="activity_name",
                labels={
                    "distance_km": "Distance (km)",
                    "performance_score": "Performance",
                    "training_load": "Training load",
                },
                title="Distance vs Performance",
            ),
            width="stretch",
        )

    st.subheader("Overview by Activity Type")
    st.dataframe(
        by_type.round(
            {
                "distance_km": 1,
                "moving_time_minutes": 1,
                "calories": 0,
                "elevation_gain": 0,
                "performance_score": 1,
            }
        ),
        width="stretch",
        hide_index=True,
    )

with tab_years:
    annual = (
        filtered.groupby("activity_year", as_index=False)
        .agg(
            activities=("activity_id", "count"),
            distance_km=("distance_km", "sum"),
            moving_time_minutes=("moving_time_minutes", "sum"),
            calories=("calories", "sum"),
            elevation_gain=("total_elevation_gain", "sum"),
            performance_score=("performance_score", "mean"),
            training_load=("training_load", "sum"),
        )
        .sort_values("activity_year")
    )
    annual["moving_hours"] = annual["moving_time_minutes"] / 60
    annual = add_year_variation(
        annual,
        ["distance_km", "moving_hours", "calories", "elevation_gain", "performance_score"],
    )

    year_col1, year_col2 = st.columns(2)
    with year_col1:
        st.plotly_chart(
            px.bar(
                annual,
                x="activity_year",
                y="distance_km",
                labels={"activity_year": "Year", "distance_km": "Distance (km)"},
                title="Distance by Year",
            ),
            width="stretch",
        )
        st.plotly_chart(
            px.line(
                annual,
                x="activity_year",
                y="performance_score",
                markers=True,
                labels={
                    "activity_year": "Year",
                    "performance_score": "Avg performance",
                },
                title="Performance by Year",
            ),
            width="stretch",
        )
    with year_col2:
        st.plotly_chart(
            px.bar(
                annual,
                x="activity_year",
                y=["moving_hours", "elevation_gain"],
                barmode="group",
                labels={"activity_year": "Year", "value": "Total", "variable": "Metric"},
                title="Time and Elevation by Year",
            ),
            width="stretch",
        )
        annual_by_type = (
            filtered.groupby(["activity_year", "activity_type"], as_index=False)
            .agg(distance_km=("distance_km", "sum"))
            .sort_values("activity_year")
        )
        st.plotly_chart(
            px.bar(
                annual_by_type,
                x="activity_year",
                y="distance_km",
                color="activity_type",
                labels={
                    "activity_year": "Year",
                    "distance_km": "Distance (km)",
                    "activity_type": "Type",
                },
                title="Yearly Distance by Type",
            ),
            width="stretch",
        )

    st.subheader("Year-over-Year Variation")
    display_annual = annual[
        [
            "activity_year",
            "activities",
            "distance_km",
            "distance_km_yoy",
            "moving_hours",
            "moving_hours_yoy",
            "calories",
            "calories_yoy",
            "elevation_gain",
            "elevation_gain_yoy",
            "performance_score",
            "performance_score_yoy",
        ]
    ].round(1)
    st.dataframe(display_annual, width="stretch", hide_index=True)

    timeline_col1, timeline_col2 = st.columns(2)
    filtered["weekday"] = filtered["activity_date"].dt.day_name()
    with timeline_col1:
        month_type = (
            filtered.groupby(["activity_month", "activity_type"], as_index=False)
            .agg(distance_km=("distance_km", "sum"))
            .sort_values("activity_month")
        )
        st.plotly_chart(
            px.area(
                month_type,
                x="activity_month",
                y="distance_km",
                color="activity_type",
                labels={"activity_month": "Month", "distance_km": "Distance (km)"},
                title="Monthly Distance by Type",
            ),
            width="stretch",
        )
    with timeline_col2:
        weekday_order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        weekday = (
            filtered.groupby("weekday", as_index=False)
            .agg(
                activities=("activity_id", "count"),
                performance_score=("performance_score", "mean"),
            )
            .set_index("weekday")
            .reindex(weekday_order)
            .reset_index()
        )
        st.plotly_chart(
            px.bar(
                weekday,
                x="weekday",
                y="activities",
                color="performance_score",
                labels={
                    "weekday": "Weekday",
                    "activities": "Activities",
                    "performance_score": "Avg performance",
                },
                title="Activity Frequency and Performance by Weekday",
                color_continuous_scale="Viridis",
            ),
            width="stretch",
        )

with tab_stats:
    st.subheader("Statistical Analysis")
    st.markdown(
        '<p class="section-note">Distribution, variability, correlations, and outliers for the selected timeline.</p>',
        unsafe_allow_html=True,
    )

    stats_df = build_stat_summary(filtered)
    st.dataframe(stats_df, width="stretch", hide_index=True)

    stat_col1, stat_col2 = st.columns(2)
    with stat_col1:
        st.plotly_chart(
            px.box(
                filtered,
                x="activity_type",
                y="performance_score",
                color="activity_type",
                points="outliers",
                labels={
                    "activity_type": "Type",
                    "performance_score": "Performance",
                },
                title="Performance Distribution by Activity Type",
            ),
            width="stretch",
        )
        st.plotly_chart(
            px.histogram(
                filtered,
                x="moving_time_minutes",
                color="activity_type",
                marginal="box",
                labels={"moving_time_minutes": "Moving time (min)"},
                title="Duration Distribution",
            ),
            width="stretch",
        )
    with stat_col2:
        st.plotly_chart(
            px.scatter(
                filtered,
                x="average_heartrate",
                y="performance_score",
                color="activity_type",
                size="distance_km",
                hover_name="activity_name",
                labels={
                    "average_heartrate": "Avg heart rate",
                    "performance_score": "Performance",
                    "distance_km": "Distance (km)",
                },
                title="Heart Rate vs Performance",
            ),
            width="stretch",
        )
        st.plotly_chart(
            px.violin(
                filtered,
                x="activity_type",
                y="average_pace_min_km",
                color="activity_type",
                box=True,
                labels={
                    "activity_type": "Type",
                    "average_pace_min_km": "Pace (min/km)",
                },
                title="Pace Distribution by Activity Type",
            ),
            width="stretch",
        )

    numeric_columns = [
        "distance_km",
        "moving_time_minutes",
        "average_speed_kmh",
        "average_heartrate",
        "average_pace_min_km",
        "total_elevation_gain",
        "calories",
        "performance_score",
        "training_load",
    ]
    corr = filtered[numeric_columns].corr(numeric_only=True).round(2)
    st.plotly_chart(
        px.imshow(
            corr,
            text_auto=True,
            aspect="auto",
            color_continuous_scale="RdBu",
            zmin=-1,
            zmax=1,
            title="Metric Correlation Matrix",
        ),
        width="stretch",
    )

with tab_geo:
    st.subheader("GPS Area Analysis")
    st.markdown(
        '<p class="section-note">Areas where you move most and areas with stronger average performance, filtered by year, month and activity type.</p>',
        unsafe_allow_html=True,
    )
    geo_type_options = sorted(geo_filtered["activity_type"].dropna().unique().tolist())
    selected_geo_types = st.multiselect(
        "Activity types on map",
        geo_type_options,
        default=geo_type_options,
    )
    mapped_geo = geo_filtered.copy()
    if selected_geo_types:
        mapped_geo = mapped_geo[mapped_geo["activity_type"].isin(selected_geo_types)]

    map_col1, map_col2 = st.columns(2)
    with map_col1:
        render_geo_map(
            mapped_geo,
            color_metric="samples",
            title="Most Frequent Areas",
            color_scale="Oranges",
        )
    with map_col2:
        render_geo_map(
            mapped_geo.dropna(subset=["avg_performance"]),
            color_metric="avg_performance",
            title="Best Performance Areas",
            color_scale="Viridis",
        )

    top_areas = (
        mapped_geo.groupby(["latitude", "longitude", "activity_type"], as_index=False)
        .agg(
            samples=("samples", "sum"),
            avg_performance=("avg_performance", "mean"),
            avg_speed_kmh=("avg_speed_kmh", "mean"),
            avg_heartrate=("avg_heartrate", "mean"),
        )
        .sort_values(["samples", "avg_performance"], ascending=[False, False])
        .head(30)
        .round(2)
    )
    st.subheader("Top GPS Areas")
    st.dataframe(top_areas, width="stretch", hide_index=True)

with tab_heatmaps:
    st.subheader("Run and Ride Heatmaps")
    heat_col1, heat_col2 = st.columns(2)
    with heat_col1:
        render_activity_heatmap(filtered, "Run")
    with heat_col2:
        render_activity_heatmap(filtered, "Ride")

with tab_activities:
    activities = filtered.sort_values(["activity_date", "activity_id"], ascending=False)

    filter_col1, filter_col2 = st.columns([2, 1])
    with filter_col1:
        type_filter = st.multiselect(
            "Activity type for detail table",
            available_types,
            default=selected_types or available_types,
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
                "some export files may not include route points."
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
            filtered_activities.drop(
                columns=["activity_id", "activity_year", "activity_month"],
                errors="ignore",
            ),
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
