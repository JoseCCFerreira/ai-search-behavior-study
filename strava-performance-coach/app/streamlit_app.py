"""Streamlit dashboard for Strava Performance Coach."""

from __future__ import annotations

import gzip
import hashlib
import html
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
        :root {
            --surface: #ffffff;
            --surface-soft: #f8fafc;
            --border: #e2e8f0;
            --text-muted: #64748b;
            --accent: #2563eb;
        }
        @keyframes page-slide-in {
            from {
                opacity: 0;
                transform: translateX(14px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        .stApp {
            background: #f6f8fb;
        }
        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 3rem;
            max-width: 1440px;
            animation: page-slide-in 220ms ease-out;
        }
        [data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px 18px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        [data-testid="stMetricLabel"] {
            color: var(--text-muted);
            font-weight: 650;
        }
        [data-testid="stMetricValue"] {
            color: #0f172a;
        }
        [data-testid="stSidebar"] {
            background: #0f172a;
        }
        [data-testid="stSidebar"] * {
            color: #e5e7eb;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label {
            border-radius: 8px;
            padding: 8px 10px;
            margin-bottom: 3px;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:hover {
            background: rgba(255, 255, 255, 0.08);
        }
        [data-testid="stSidebar"] hr {
            border-color: rgba(255, 255, 255, 0.14);
        }
        .app-hero {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 58%, #2563eb 100%);
            color: #ffffff;
            border-radius: 8px;
            padding: 22px 24px;
            margin-bottom: 18px;
            box-shadow: 0 14px 32px rgba(15, 23, 42, 0.16);
        }
        .app-hero h1 {
            margin: 0;
            font-size: 2rem;
            letter-spacing: 0;
        }
        .app-hero p {
            margin: 6px 0 0;
            color: #dbeafe;
            font-size: 0.98rem;
        }
        .section-note {
            color: var(--text-muted);
            margin-top: -0.5rem;
            margin-bottom: 1rem;
        }
        .page-kicker {
            color: var(--accent);
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 0.15rem;
        }
        .page-title {
            color: #0f172a;
            font-size: 1.65rem;
            font-weight: 800;
            margin-bottom: 0.25rem;
        }
        .hub-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin: 12px 0 18px;
        }
        .hub-card,
        .feed-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .hub-card small,
        .feed-card small {
            display: block;
            color: #64748b;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 4px;
        }
        .hub-card strong {
            display: block;
            color: #0f172a;
            font-size: 1.35rem;
            line-height: 1.2;
        }
        .hub-card span,
        .feed-card span {
            color: #64748b;
            font-size: 0.9rem;
        }
        .feed-card {
            margin-bottom: 10px;
        }
        .feed-card h4 {
            margin: 2px 0 8px;
            color: #0f172a;
            font-size: 1rem;
        }
        .feed-metrics {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .feed-metrics b {
            background: #f1f5f9;
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 0.82rem;
            color: #334155;
        }
        @media (max-width: 900px) {
            .hub-grid {
                grid-template-columns: 1fr;
            }
        }
        div[data-testid="stDataFrame"],
        div[data-testid="stPlotlyChart"] {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header(page_title: str) -> None:
    st.markdown(
        f"""
        <div class="app-hero">
            <h1>Strava Performance Coach</h1>
            <p>Offline activity database, performance analytics, GPS maps, and explainable coaching.</p>
        </div>
        <div class="page-kicker">Dashboard</div>
        <div class="page-title">{page_title}</div>
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


def build_record_rows(df: pd.DataFrame) -> pd.DataFrame:
    record_specs = [
        ("Longest distance", "distance_km", "max", "km", "distance"),
        ("Longest duration", "moving_time_minutes", "max", "min", "endurance"),
        ("Highest elevation gain", "total_elevation_gain", "max", "m", "climbing"),
        ("Highest calories", "calories", "max", "kcal", "effort"),
        ("Highest avg speed", "average_speed_kmh", "max", "km/h", "speed"),
        ("Fastest pace", "average_pace_min_km", "min", "min/km", "pace"),
        ("Highest avg heart rate", "average_heartrate", "max", "bpm", "heart rate"),
        ("Highest max heart rate", "max_heartrate", "max", "bpm", "heart rate"),
        ("Best performance", "performance_score", "max", "score", "performance"),
        ("Highest training load", "training_load", "max", "load", "load"),
    ]
    rows = []
    scopes = [("All", df)]
    for activity_type in sorted(df["activity_type"].dropna().unique()):
        scopes.append((activity_type, df[df["activity_type"] == activity_type]))

    for scope, scoped_df in scopes:
        for label, column, direction, unit, category in record_specs:
            if column not in scoped_df.columns:
                continue
            values = scoped_df.dropna(subset=[column])
            values = values[values[column] > 0]
            if values.empty:
                continue
            idx = values[column].idxmin() if direction == "min" else values[column].idxmax()
            record = values.loc[idx]
            rows.append(
                {
                    "scope": scope,
                    "category": category,
                    "record": label,
                    "value": record[column],
                    "unit": unit,
                    "date": record["activity_date"].date(),
                    "activity_type": record["activity_type"],
                    "activity": record["activity_name"],
                    "distance_km": record["distance_km"],
                    "performance": record["performance_score"],
                }
            )
    return pd.DataFrame(rows).round({"value": 2, "distance_km": 2, "performance": 1})


def monthly_metric(
    df: pd.DataFrame,
    activity_type: str,
    metric: str,
    aggregation: str,
) -> pd.DataFrame:
    activity_df = df[df["activity_type"] == activity_type].dropna(subset=[metric]).copy()
    activity_df = activity_df[activity_df[metric] > 0]
    if activity_df.empty:
        return pd.DataFrame(columns=["activity_month", metric])

    return (
        activity_df.groupby("activity_month", as_index=False)
        .agg(**{metric: (metric, aggregation)})
        .sort_values("activity_month")
    )


def linear_fit(values: list[float]) -> tuple[float, float, list[float]]:
    if not values:
        return 0.0, 0.0, []

    x_values = list(range(len(values)))
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(values) / len(values)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values)) / denominator
        if denominator
        else 0.0
    )
    intercept = y_mean - slope * x_mean
    fitted = [intercept + slope * x for x in x_values]
    return slope, intercept, fitted


def forecast_monthly_metric(
    df: pd.DataFrame,
    activity_type: str,
    metric: str,
    aggregation: str,
    periods: int = 6,
) -> tuple[pd.DataFrame, dict[str, float | None]]:
    monthly_df = monthly_metric(df, activity_type, metric, aggregation)
    if len(monthly_df) < 2:
        monthly_df["kind"] = "actual"
        return monthly_df, {
            "slope": None,
            "last_actual": monthly_df[metric].iloc[-1] if len(monthly_df) else None,
            "next_forecast": None,
            "six_month_forecast": None,
        }

    actual = monthly_df.copy()
    actual["kind"] = "actual"
    y_values = monthly_df[metric].astype(float).tolist()
    slope, intercept, fitted = linear_fit(y_values)
    trend = monthly_df.copy()
    trend[metric] = fitted
    trend["kind"] = "trend"

    last_month = monthly_df["activity_month"].max()
    forecast_rows = []
    for step in range(1, periods + 1):
        next_x = len(monthly_df) + step - 1
        forecast_rows.append(
            {
                "activity_month": last_month + pd.DateOffset(months=step),
                metric: max(0.0, intercept + slope * next_x),
                "kind": "forecast",
            }
        )
    forecast_df = pd.concat(
        [actual, trend, pd.DataFrame(forecast_rows)],
        ignore_index=True,
    )
    summary = {
        "slope": slope,
        "last_actual": y_values[-1],
        "next_forecast": forecast_rows[0][metric],
        "six_month_forecast": forecast_rows[-1][metric],
    }
    return forecast_df, summary


def render_trend_forecast(
    df: pd.DataFrame,
    activity_type: str,
    metric: str,
    label: str,
    unit: str,
    aggregation: str,
) -> None:
    trend_df, summary = forecast_monthly_metric(df, activity_type, metric, aggregation)
    if trend_df.empty:
        st.info(f"No {activity_type.lower()} data for {label.lower()}.")
        return
    fig = px.line(
        trend_df,
        x="activity_month",
        y=metric,
        color="kind",
        markers=True,
        labels={"activity_month": "Month", metric: f"{label} ({unit})", "kind": "Series"},
        title=f"{activity_type}: {label} trend and forecast",
    )
    fig.for_each_trace(
        lambda trace: trace.update(
            line={
                "dash": "dash"
                if trace.name == "forecast"
                else "dot"
                if trace.name == "trend"
                else "solid"
            }
        )
    )
    st.plotly_chart(fig, width="stretch")

    if summary["slope"] is not None:
        direction = "improving" if summary["slope"] > 0 else "declining"
        if metric == "average_pace_min_km":
            direction = "improving" if summary["slope"] < 0 else "slowing"
        st.caption(
            f"Monthly trend: {summary['slope']:+.2f} {unit}/month, "
            f"next month forecast: {summary['next_forecast']:.2f} {unit}, "
            f"6-month forecast: {summary['six_month_forecast']:.2f} {unit} "
            f"({direction})."
        )


def build_forecast_summary(
    df: pd.DataFrame,
    activity_type: str,
    metric_specs: dict[str, tuple[str, str, str]],
) -> pd.DataFrame:
    rows = []
    for label, (metric, aggregation, unit) in metric_specs.items():
        _, summary = forecast_monthly_metric(df, activity_type, metric, aggregation)
        if summary["slope"] is None:
            continue
        rows.append(
            {
                "activity_type": activity_type,
                "metric": label,
                "trend_per_month": summary["slope"],
                "last_actual": summary["last_actual"],
                "next_month_forecast": summary["next_forecast"],
                "six_month_forecast": summary["six_month_forecast"],
                "unit": unit,
            }
        )
    return pd.DataFrame(rows).round(2)


def percent_delta(current_value: float, previous_value: float) -> str | None:
    if pd.isna(previous_value) or previous_value == 0:
        return None
    return format_percent(((current_value - previous_value) / previous_value) * 100)


def period_value(df: pd.DataFrame, metric: str, aggregation: str) -> float:
    series = df[metric].dropna()
    if series.empty:
        return 0.0
    if aggregation == "mean":
        return float(series.mean())
    return float(series.sum())


def render_metric_grid(df: pd.DataFrame, previous_df: pd.DataFrame | None = None) -> None:
    metric_defs = [
        ("Activities", "activity_id", "count", "{:,.0f}"),
        ("Distance", "distance_km", "sum", "{:,.1f} km"),
        ("Moving Time", "moving_time_minutes", "sum_hours", "{:,.1f} h"),
        ("Elevation", "total_elevation_gain", "sum", "{:,.0f} m"),
        ("Avg Pace", "average_pace_min_km", "mean", "{:,.2f} min/km"),
        ("Performance", "performance_score", "mean", "{:,.1f}"),
    ]
    cols = st.columns(len(metric_defs))
    for col, (label, metric, aggregation, template) in zip(cols, metric_defs):
        if aggregation == "count":
            value = float(len(df))
            previous_value = float(len(previous_df)) if previous_df is not None else 0.0
        elif aggregation == "sum_hours":
            value = period_value(df, metric, "sum") / 60
            previous_value = (
                period_value(previous_df, metric, "sum") / 60
                if previous_df is not None
                else 0.0
            )
        else:
            value = period_value(df, metric, aggregation)
            previous_value = (
                period_value(previous_df, metric, aggregation)
                if previous_df is not None
                else 0.0
            )

        delta = percent_delta(value, previous_value) if previous_df is not None else None
        col.metric(label, template.format(value), delta)


def build_training_status(df: pd.DataFrame) -> tuple[str, str, pd.DataFrame]:
    if df.empty:
        return "No data", "No activities available to assess training load.", pd.DataFrame()

    latest_day = df["activity_date"].max().normalize()
    last_7_start = latest_day - pd.Timedelta(days=6)
    previous_28_start = latest_day - pd.Timedelta(days=34)
    previous_28_end = last_7_start - pd.Timedelta(days=1)

    last_7 = df[
        (df["activity_date"] >= last_7_start)
        & (df["activity_date"] <= latest_day + pd.Timedelta(days=1))
    ]
    previous_28 = df[
        (df["activity_date"] >= previous_28_start)
        & (df["activity_date"] <= previous_28_end)
    ]

    load_metric = "training_load"
    if df[load_metric].dropna().sum() <= 0:
        load_metric = "moving_time_minutes"

    acute_load = period_value(last_7, load_metric, "sum")
    chronic_weekly_load = period_value(previous_28, load_metric, "sum") / 4
    load_ratio = acute_load / chronic_weekly_load if chronic_weekly_load > 0 else None
    last_7_performance = period_value(last_7, "performance_score", "mean")
    previous_performance = period_value(previous_28, "performance_score", "mean")
    last_7_hr = period_value(last_7, "average_heartrate", "mean")
    previous_hr = period_value(previous_28, "average_heartrate", "mean")

    intensity_series = last_7["intensity_level"].fillna("").astype(str).str.lower()
    high_intensity_share = (
        intensity_series.str.contains("high|hard|intense|very").mean()
        if len(intensity_series)
        else 0
    )
    recovery_series = last_7["recovery_indicator"].fillna("").astype(str).str.lower()
    poor_recovery_count = int(
        recovery_series.str.contains("poor|low|bad|insufficient|limited").sum()
    )
    fatigue_series = pd.to_numeric(last_7["fatigue_impact"], errors="coerce").dropna()
    fatigue_avg = float(fatigue_series.mean()) if not fatigue_series.empty else None

    risk_points = 0
    reasons = []
    if load_ratio is not None:
        if load_ratio >= 1.5:
            risk_points += 3
            reasons.append("acute load is much higher than the previous 4-week baseline")
        elif load_ratio >= 1.25:
            risk_points += 2
            reasons.append("acute load is rising above the previous 4-week baseline")
        elif load_ratio < 0.65:
            reasons.append("recent load is well below the previous baseline")
    if previous_performance and last_7_performance < previous_performance * 0.9:
        risk_points += 1
        reasons.append("recent performance is lower than the previous baseline")
    if previous_hr and last_7_hr > previous_hr * 1.08:
        risk_points += 1
        reasons.append("average heart rate is elevated versus the previous baseline")
    if high_intensity_share >= 0.45:
        risk_points += 1
        reasons.append("a high share of recent sessions are high intensity")
    if poor_recovery_count >= 2:
        risk_points += 1
        reasons.append("multiple recent sessions show weak recovery")
    if fatigue_avg is not None and fatigue_avg >= 70:
        risk_points += 1
        reasons.append("fatigue impact is high")

    if load_ratio is None:
        status = "Needs more history"
        message = "Add more activities across several weeks to compare acute and baseline load."
    elif risk_points >= 4:
        status = "Potentially excessive"
        message = "Training load looks high. Consider recovery, easier sessions, or a rest day."
    elif risk_points >= 2:
        status = "Elevated load"
        message = "Training is productive but demanding. Watch recovery and avoid stacking hard days."
    elif load_ratio < 0.65:
        status = "Low recent load"
        message = "Recent training is below your baseline. Good for recovery, but fitness stimulus may be lower."
    else:
        status = "Balanced"
        message = "Recent training load looks controlled against your recent baseline."

    if reasons:
        message = f"{message} Signals: {', '.join(reasons)}."

    unit = "load" if load_metric == "training_load" else "min"
    rows = [
        ("Last 7 days load", acute_load, unit),
        ("Previous 4-week weekly baseline", chronic_weekly_load, unit),
        ("Acute/baseline ratio", load_ratio, "ratio"),
        ("Last 7 days performance", last_7_performance, "score"),
        ("Previous baseline performance", previous_performance, "score"),
        ("Last 7 days heart rate", last_7_hr, "bpm"),
        ("Previous baseline heart rate", previous_hr, "bpm"),
        ("High intensity share", high_intensity_share * 100, "%"),
        ("Poor recovery sessions", poor_recovery_count, "activities"),
    ]
    if fatigue_avg is not None:
        rows.append(("Average fatigue impact", fatigue_avg, "score"))

    indicators = pd.DataFrame(
        [
            {
                "indicator": label,
                "value": None if value is None or pd.isna(value) else round(float(value), 2),
                "unit": unit,
            }
            for label, value, unit in rows
        ]
    )
    return status, message, indicators


def render_training_status(df: pd.DataFrame) -> None:
    status, message, indicators = build_training_status(df)
    st.subheader("Training Load Status")
    if status == "Potentially excessive":
        st.error(f"**{status}:** {message}")
    elif status == "Elevated load":
        st.warning(f"**{status}:** {message}")
    elif status == "Low recent load":
        st.info(f"**{status}:** {message}")
    elif status == "Balanced":
        st.success(f"**{status}:** {message}")
    else:
        st.info(f"**{status}:** {message}")

    if not indicators.empty:
        st.dataframe(indicators, width="stretch", hide_index=True)


def render_hub_card(label: str, value: str, note: str) -> None:
    st.markdown(
        f"""
        <div class="hub-card">
            <small>{html.escape(label)}</small>
            <strong>{html.escape(value)}</strong>
            <span>{html.escape(note)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_activity_feed(df: pd.DataFrame, limit: int = 8) -> None:
    recent = df.sort_values("activity_date", ascending=False).head(limit)
    if recent.empty:
        st.info("No recent activities available.")
        return

    for activity in recent.itertuples(index=False):
        pace = (
            f"{activity.average_pace_min_km:.2f} min/km"
            if not pd.isna(activity.average_pace_min_km)
            else "-"
        )
        speed = (
            f"{activity.average_speed_kmh:.1f} km/h"
            if not pd.isna(activity.average_speed_kmh)
            else "-"
        )
        hr = (
            f"{activity.average_heartrate:.0f} bpm"
            if not pd.isna(activity.average_heartrate)
            else "-"
        )
        performance = (
            f"{activity.performance_score:.0f}"
            if not pd.isna(activity.performance_score)
            else "-"
        )
        st.markdown(
            f"""
            <div class="feed-card">
                <small>{html.escape(str(activity.activity_type))} | {activity.activity_date.date()}</small>
                <h4>{html.escape(str(activity.activity_name))}</h4>
                <div class="feed-metrics">
                    <b>{activity.distance_km:.2f} km</b>
                    <b>{activity.moving_time_minutes:.0f} min</b>
                    <b>{pace}</b>
                    <b>{speed}</b>
                    <b>{hr}</b>
                    <b>{activity.total_elevation_gain:.0f} m</b>
                    <b>score {performance}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_strava_garmin_hub(df: pd.DataFrame, geo_df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No activities available for the selected filters.")
        return

    st.subheader("Training Hub")
    st.markdown(
        '<p class="section-note">A Strava-style activity feed combined with Garmin-style training load, goals, status and performance insights.</p>',
        unsafe_allow_html=True,
    )

    latest_day = df["activity_date"].max().normalize()
    last_7 = df[df["activity_date"] >= latest_day - pd.Timedelta(days=6)]
    last_30 = df[df["activity_date"] >= latest_day - pd.Timedelta(days=29)]
    previous_30 = df[
        (df["activity_date"] >= latest_day - pd.Timedelta(days=59))
        & (df["activity_date"] < latest_day - pd.Timedelta(days=29))
    ]
    status, message, indicators = build_training_status(df)

    monthly = (
        df.groupby("activity_month", as_index=False)
        .agg(
            distance_km=("distance_km", "sum"),
            moving_time_minutes=("moving_time_minutes", "sum"),
            total_elevation_gain=("total_elevation_gain", "sum"),
            training_load=("training_load", "sum"),
            performance_score=("performance_score", "mean"),
        )
        .sort_values("activity_month")
    )
    monthly_baseline = monthly.iloc[:-1] if len(monthly) > 1 else monthly
    current_month = monthly.iloc[-1] if not monthly.empty else None
    distance_goal = max(1.0, float(monthly_baseline["distance_km"].mean() or 0))
    time_goal = max(1.0, float(monthly_baseline["moving_time_minutes"].mean() or 0))
    elevation_goal = max(1.0, float(monthly_baseline["total_elevation_gain"].mean() or 0))

    st.markdown('<div class="hub-grid">', unsafe_allow_html=True)
    hub_cols = st.columns(3)
    with hub_cols[0]:
        render_hub_card(
            "Training status",
            status,
            message[:115] + ("..." if len(message) > 115 else ""),
        )
    with hub_cols[1]:
        render_hub_card(
            "Last 7 days",
            f"{last_7['distance_km'].sum():,.1f} km",
            f"{len(last_7)} activities | {last_7['moving_time_minutes'].sum() / 60:,.1f} h",
        )
    with hub_cols[2]:
        render_hub_card(
            "Last 30 days",
            f"{last_30['distance_km'].sum():,.1f} km",
            f"{format_percent(((last_30['distance_km'].sum() - previous_30['distance_km'].sum()) / previous_30['distance_km'].sum()) * 100) if previous_30['distance_km'].sum() else '-'} vs previous 30d",
        )
    st.markdown('</div>', unsafe_allow_html=True)

    goal_col1, goal_col2, goal_col3 = st.columns(3)
    if current_month is not None:
        current_distance = float(current_month["distance_km"])
        current_time = float(current_month["moving_time_minutes"])
        current_elevation = float(current_month["total_elevation_gain"])
        with goal_col1:
            st.metric("Monthly Distance Goal", f"{current_distance:,.1f} km", f"baseline {distance_goal:,.1f} km")
            st.progress(min(1.0, current_distance / distance_goal))
        with goal_col2:
            st.metric("Monthly Time Goal", f"{current_time / 60:,.1f} h", f"baseline {time_goal / 60:,.1f} h")
            st.progress(min(1.0, current_time / time_goal))
        with goal_col3:
            st.metric("Monthly Elevation Goal", f"{current_elevation:,.0f} m", f"baseline {elevation_goal:,.0f} m")
            st.progress(min(1.0, current_elevation / elevation_goal))

    hub_left, hub_right = st.columns([1.1, 0.9])
    with hub_left:
        st.subheader("Activity Feed")
        render_activity_feed(df)

    with hub_right:
        st.subheader("Garmin-style Metrics")
        if not indicators.empty:
            st.dataframe(indicators, width="stretch", hide_index=True)

        records = build_record_rows(df)
        records = records[records["scope"] == "All"].head(6)
        st.subheader("Recent PR Board")
        if records.empty:
            st.info("No records available.")
        else:
            st.dataframe(
                records[["category", "record", "value", "unit", "date", "activity_type"]],
                width="stretch",
                hide_index=True,
            )

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        type_mix = (
            df.groupby("activity_type", as_index=False)
            .agg(distance_km=("distance_km", "sum"), activities=("activity_id", "count"))
            .sort_values("distance_km", ascending=False)
        )
        st.plotly_chart(
            px.pie(
                type_mix,
                names="activity_type",
                values="distance_km",
                hole=0.45,
                title="Sport Mix by Distance",
            ),
            width="stretch",
        )
    with chart_col2:
        intensity = (
            df.assign(intensity_level=df["intensity_level"].fillna("unknown"))
            .groupby("intensity_level", as_index=False)
            .agg(activities=("activity_id", "count"), training_load=("training_load", "sum"))
        )
        st.plotly_chart(
            px.bar(
                intensity,
                x="intensity_level",
                y="activities",
                color="training_load",
                color_continuous_scale="Oranges",
                labels={
                    "intensity_level": "Intensity",
                    "activities": "Activities",
                    "training_load": "Training load",
                },
                title="Intensity Distribution",
            ),
            width="stretch",
        )

    if not geo_df.empty:
        st.subheader("Favorite Areas")
        favorite_areas = (
            geo_df.groupby(["latitude", "longitude", "activity_type"], as_index=False)
            .agg(
                samples=("samples", "sum"),
                avg_performance=("avg_performance", "mean"),
                avg_speed_kmh=("avg_speed_kmh", "mean"),
            )
            .sort_values(["samples", "avg_performance"], ascending=[False, False])
            .head(10)
            .round(2)
        )
        st.dataframe(favorite_areas, width="stretch", hide_index=True)


def render_results_dashboard(df: pd.DataFrame, title: str, show_type_breakdown: bool) -> None:
    if df.empty:
        st.info("No activities available for this view.")
        return

    st.subheader(title)
    min_day = df["activity_date"].min().date()
    max_day = df["activity_date"].max().date()
    st.markdown(
        f'<p class="section-note">Analysis from {min_day} to {max_day}, using the active sidebar timeline filters.</p>',
        unsafe_allow_html=True,
    )

    latest_day = df["activity_date"].max().normalize()
    last_30_start = latest_day - pd.Timedelta(days=29)
    previous_30_start = latest_day - pd.Timedelta(days=59)
    previous_30_end = last_30_start - pd.Timedelta(days=1)
    last_30 = df[
        (df["activity_date"] >= last_30_start)
        & (df["activity_date"] <= latest_day + pd.Timedelta(days=1))
    ]
    previous_30 = df[
        (df["activity_date"] >= previous_30_start)
        & (df["activity_date"] <= previous_30_end)
    ]

    st.markdown("**Selected Period**")
    render_metric_grid(df)
    st.markdown("**Last 30 Days vs Previous 30 Days**")
    render_metric_grid(last_30, previous_30)
    render_training_status(df)

    monthly = (
        df.groupby("activity_month", as_index=False)
        .agg(
            activities=("activity_id", "count"),
            distance_km=("distance_km", "sum"),
            moving_time_minutes=("moving_time_minutes", "sum"),
            elevation_gain=("total_elevation_gain", "sum"),
            calories=("calories", "sum"),
            average_pace_min_km=("average_pace_min_km", "mean"),
            average_speed_kmh=("average_speed_kmh", "mean"),
            average_heartrate=("average_heartrate", "mean"),
            performance_score=("performance_score", "mean"),
            training_load=("training_load", "sum"),
        )
        .sort_values("activity_month")
    )
    monthly["moving_hours"] = monthly["moving_time_minutes"] / 60

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.plotly_chart(
            px.area(
                monthly,
                x="activity_month",
                y=["distance_km", "moving_hours"],
                labels={"activity_month": "Month", "value": "Total", "variable": "Metric"},
                title="Monthly Volume: Distance and Time",
            ),
            width="stretch",
        )
    with chart_col2:
        st.plotly_chart(
            px.line(
                monthly,
                x="activity_month",
                y=["performance_score", "average_heartrate"],
                markers=True,
                labels={"activity_month": "Month", "value": "Value", "variable": "Metric"},
                title="Monthly Performance and Heart Rate",
            ),
            width="stretch",
        )

    chart_col3, chart_col4 = st.columns(2)
    with chart_col3:
        st.plotly_chart(
            px.bar(
                monthly,
                x="activity_month",
                y=["elevation_gain", "calories"],
                barmode="group",
                labels={"activity_month": "Month", "value": "Total", "variable": "Metric"},
                title="Elevation and Calories",
            ),
            width="stretch",
        )
    with chart_col4:
        st.plotly_chart(
            px.scatter(
                df.assign(chart_elevation_gain=df["total_elevation_gain"].fillna(0).clip(lower=0)),
                x="distance_km",
                y="performance_score",
                color="activity_type" if show_type_breakdown else "intensity_level",
                size="chart_elevation_gain",
                hover_name="activity_name",
                labels={
                    "distance_km": "Distance (km)",
                    "performance_score": "Performance",
                    "chart_elevation_gain": "Elevation gain",
                },
                title="Performance by Distance and Elevation",
            ),
            width="stretch",
        )

    analysis_col1, analysis_col2 = st.columns(2)
    with analysis_col1:
        if show_type_breakdown:
            by_type = (
                df.groupby("activity_type", as_index=False)
                .agg(
                    activities=("activity_id", "count"),
                    distance_km=("distance_km", "sum"),
                    moving_time_minutes=("moving_time_minutes", "sum"),
                    elevation_gain=("total_elevation_gain", "sum"),
                    performance_score=("performance_score", "mean"),
                )
                .sort_values("distance_km", ascending=False)
            )
            st.plotly_chart(
                px.treemap(
                    by_type,
                    path=["activity_type"],
                    values="distance_km",
                    color="performance_score",
                    color_continuous_scale="Viridis",
                    title="Contribution by Activity Type",
                ),
                width="stretch",
            )
        else:
            st.plotly_chart(
                px.histogram(
                    df,
                    x="distance_km",
                    nbins=25,
                    labels={"distance_km": "Distance (km)"},
                    title="Distance Distribution",
                ),
                width="stretch",
            )
    with analysis_col2:
        weekday_order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        weekday = df.copy()
        weekday["weekday"] = weekday["activity_date"].dt.day_name()
        weekday = (
            weekday.groupby("weekday", as_index=False)
            .agg(distance_km=("distance_km", "sum"), performance_score=("performance_score", "mean"))
            .set_index("weekday")
            .reindex(weekday_order)
            .reset_index()
        )
        st.plotly_chart(
            px.bar(
                weekday,
                x="weekday",
                y="distance_km",
                color="performance_score",
                color_continuous_scale="Blues",
                labels={
                    "weekday": "Weekday",
                    "distance_km": "Distance (km)",
                    "performance_score": "Performance",
                },
                title="Best Days by Volume and Performance",
            ),
            width="stretch",
        )

    st.subheader("Statistical Indicators")
    st.dataframe(build_stat_summary(df), width="stretch", hide_index=True)

    st.subheader("Last Month Activities")
    recent_columns = [
        "activity_date",
        "activity_type",
        "activity_name",
        "distance_km",
        "moving_time_minutes",
        "average_pace_min_km",
        "average_speed_kmh",
        "average_heartrate",
        "total_elevation_gain",
        "performance_score",
    ]
    recent_display = last_30.sort_values("activity_date", ascending=False)[recent_columns].copy()
    numeric_recent = recent_display.select_dtypes(include="number").columns
    recent_display[numeric_recent] = recent_display[numeric_recent].round(2)
    st.dataframe(recent_display, width="stretch", hide_index=True)


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

with st.sidebar:
    st.markdown("## Performance Coach")
    page_options = [
        "Overview",
        "Training Hub",
        "General Results",
        "Activity Deep Dive",
        "Records & Forecasts",
        "Timeline",
        "Statistics",
        "Geo Map",
        "Heatmaps",
        "Activities",
        "Profile",
        "Coach",
    ]
    current_page = st.radio(
        "Pages",
        page_options,
        label_visibility="collapsed",
    )
    st.markdown("---")
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

render_app_header(current_page)


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
        a.max_heartrate,
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
    st.info("No activities loaded yet. Upload a Strava export or activity file to start.")
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

if current_page == "Overview":
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

if current_page == "Training Hub":
    render_strava_garmin_hub(filtered, geo_filtered)

if current_page == "General Results":
    render_results_dashboard(
        filtered,
        "General Results",
        show_type_breakdown=True,
    )

if current_page == "Activity Deep Dive":
    st.markdown(
        '<p class="section-note">Choose one activity type to see a dedicated overview, last-month comparison, charts, records and statistical indicators.</p>',
        unsafe_allow_html=True,
    )
    activity_options = filtered["activity_type"].dropna().drop_duplicates().tolist()
    selected_activity_page = st.selectbox("Activity type", activity_options)
    activity_filtered = filtered[filtered["activity_type"] == selected_activity_page]
    render_results_dashboard(
        activity_filtered,
        f"{selected_activity_page} Results",
        show_type_breakdown=False,
    )

    st.subheader(f"{selected_activity_page} Records")
    activity_records = build_record_rows(activity_filtered)
    activity_records = activity_records[activity_records["scope"] == "All"]
    if activity_records.empty:
        st.info("No records available for this activity type.")
    else:
        st.dataframe(
            activity_records[
                [
                    "category",
                    "record",
                    "value",
                    "unit",
                    "date",
                    "activity",
                    "distance_km",
                    "performance",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

if current_page == "Records & Forecasts":
    st.subheader("Personal Records")
    st.markdown(
        '<p class="section-note">Records respect the current filters, so you can inspect all-time, one year, one month, or one activity type.</p>',
        unsafe_allow_html=True,
    )

    records = build_record_rows(filtered)
    if records.empty:
        st.info("No records available for the selected filters.")
    else:
        record_scope = st.selectbox(
            "Record scope",
            records["scope"].drop_duplicates().tolist(),
        )
        category_options = records["category"].drop_duplicates().tolist()
        selected_categories = st.multiselect(
            "Record categories",
            category_options,
            default=category_options,
        )
        visible_records = records[records["scope"] == record_scope]
        if selected_categories:
            visible_records = visible_records[
                visible_records["category"].isin(selected_categories)
            ]

        record_cols = st.columns(4)
        highlight_records = visible_records.head(4).to_dict("records")
        for col, record in zip(record_cols, highlight_records):
            col.metric(
                record["record"],
                f"{record['value']:,.2f} {record['unit']}",
                f"{record['activity_type']} | {record['date']}",
            )

        st.dataframe(
            visible_records[
                [
                    "category",
                    "record",
                    "value",
                    "unit",
                    "date",
                    "activity_type",
                    "activity",
                    "distance_km",
                    "performance",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    st.subheader("Trends and Forecasts")
    st.markdown(
        '<p class="section-note">Actual monthly values are shown with a solid line, the trend with a dotted line, and the forecast with a dashed line.</p>',
        unsafe_allow_html=True,
    )

    metric_specs = {
        "Distance": ("distance_km", "sum", "km"),
        "Moving time": ("moving_time_minutes", "sum", "min"),
        "Elevation gain": ("total_elevation_gain", "sum", "m"),
        "Average pace": ("average_pace_min_km", "mean", "min/km"),
        "Average speed": ("average_speed_kmh", "mean", "km/h"),
        "Average heart rate": ("average_heartrate", "mean", "bpm"),
        "Max heart rate": ("max_heartrate", "mean", "bpm"),
        "Performance": ("performance_score", "mean", "score"),
        "Training load": ("training_load", "sum", "load"),
    }
    filtered_types = filtered["activity_type"].dropna().drop_duplicates().tolist()
    preferred_types = [activity for activity in ["Run", "Ride"] if activity in filtered_types]
    forecast_types = preferred_types + [
        activity for activity in filtered_types if activity not in preferred_types
    ]
    selected_forecast_type = st.selectbox(
        "Activity type for forecasts",
        forecast_types,
    )
    default_metrics = [
        metric for metric in ["Distance", "Average pace", "Elevation gain", "Average heart rate"]
        if metric in metric_specs
    ]
    selected_forecast_metrics = st.multiselect(
        "Forecast metrics",
        list(metric_specs.keys()),
        default=default_metrics,
    )

    summary = build_forecast_summary(filtered, selected_forecast_type, metric_specs)
    if summary.empty:
        st.info("At least two monthly data points are needed to calculate trend forecasts.")
    else:
        st.dataframe(summary, width="stretch", hide_index=True)

    for index in range(0, len(selected_forecast_metrics), 2):
        chart_cols = st.columns(2)
        for col, label in zip(chart_cols, selected_forecast_metrics[index : index + 2]):
            metric, aggregation, unit = metric_specs[label]
            with col:
                render_trend_forecast(
                    filtered,
                    selected_forecast_type,
                    metric,
                    label,
                    unit,
                    aggregation,
                )

    st.subheader("Run and Ride Direction")
    comparison_base = filtered[filtered["activity_type"].isin(["Run", "Ride"])].copy()
    if comparison_base.empty:
        st.info("No run or ride data available in the selected filters.")
    else:
        comparison_base["chart_elevation_gain"] = (
            comparison_base["total_elevation_gain"].fillna(0).clip(lower=0)
        )
        comparison_monthly = (
            comparison_base.groupby(["activity_month", "activity_type"], as_index=False)
            .agg(
                distance_km=("distance_km", "sum"),
                elevation_gain=("total_elevation_gain", "sum"),
                average_heartrate=("average_heartrate", "mean"),
                performance_score=("performance_score", "mean"),
            )
            .sort_values("activity_month")
        )
        compare_col1, compare_col2 = st.columns(2)
        with compare_col1:
            st.plotly_chart(
                px.line(
                    comparison_monthly,
                    x="activity_month",
                    y="distance_km",
                    color="activity_type",
                    markers=True,
                    labels={
                        "activity_month": "Month",
                        "distance_km": "Distance (km)",
                        "activity_type": "Type",
                    },
                    title="Run vs Ride Monthly Distance",
                ),
                width="stretch",
            )
        with compare_col2:
            st.plotly_chart(
                px.scatter(
                    comparison_base,
                    x="distance_km",
                    y="performance_score",
                    color="activity_type",
                    size="chart_elevation_gain",
                    hover_name="activity_name",
                    labels={
                        "distance_km": "Distance (km)",
                        "performance_score": "Performance",
                        "chart_elevation_gain": "Elevation gain",
                    },
                    title="Performance by Distance and Altitude",
                ),
                width="stretch",
            )

if current_page == "Timeline":
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

if current_page == "Statistics":
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

if current_page == "Geo Map":
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

if current_page == "Heatmaps":
    st.subheader("Run and Ride Heatmaps")
    heat_col1, heat_col2 = st.columns(2)
    with heat_col1:
        render_activity_heatmap(filtered, "Run")
    with heat_col2:
        render_activity_heatmap(filtered, "Ride")

if current_page == "Activities":
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

if current_page == "Profile":
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

if current_page == "Coach":
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
