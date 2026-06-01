import sys
import pathlib
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

# Ensure project root is importable when running script directly
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from src.config import (
    AI_TRAFFIC_CSV,
    BROWSERS,
    BROWSER_CSV,
    EVENTS_CSV,
    GOOGLE_TRENDS_KEYWORDS,
    GOOGLE_TRENDS_OUTPUT,
    RAW_DIR,
    REGIONS,
    SEARCH_ENGINE_CSV,
    SEARCH_ENGINES,
    AI_TOOLS,
)
from src.utils.helpers import ensure_directory


def create_date_index(start_date: str = "2019-01-01") -> pd.DatetimeIndex:
    end_date = pd.Timestamp(datetime.now()).to_period("M").to_timestamp()
    return pd.date_range(start=start_date, end=end_date, freq="MS")


def seasonal_factor(dates: pd.DatetimeIndex, amplitude: float = 0.1) -> np.ndarray:
    months = dates.month.values
    return 1.0 + amplitude * np.sin((months - 1) / 12 * 2 * np.pi)


def create_google_trends() -> pd.DataFrame:
    dates = create_date_index()
    rows = []
    for region in REGIONS:
        region_factor = 1.0 + 0.1 * (REGIONS.index(region) / max(1, len(REGIONS) - 1))
        for keyword in GOOGLE_TRENDS_KEYWORDS:
            base = 10 + 5 * np.random.rand()
            growth = np.linspace(0, 60 if "AI" in keyword or "ChatGPT" in keyword or "Copilot" in keyword else 10, len(dates))
            trend = base + growth * region_factor
            trend *= seasonal_factor(dates, amplitude=0.15)
            trend += np.random.normal(0, 5, len(dates))
            trend = np.clip(trend, 0, 100)
            for date, interest in zip(dates, trend):
                rows.append(
                    {
                        "date": date.strftime("%Y-%m-%d"),
                        "region": region,
                        "keyword": keyword,
                        "interest": float(round(interest, 1)),
                    }
                )
    return pd.DataFrame(rows)


def create_share_matrix(items: list[str], base_values: list[float], growth: list[float], dates: pd.DatetimeIndex, region: str) -> pd.DataFrame:
    rows = []
    seasonal = seasonal_factor(dates, amplitude=0.07)
    for item, base, trend in zip(items, base_values, growth):
        values = base + np.linspace(0, trend, len(dates)) * (1.0 + 0.05 * REGIONS.index(region))
        values *= seasonal
        values += np.random.normal(0, 1.5, len(dates))
        values = np.clip(values, 0.5, None)
        for date, value in zip(dates, values):
            rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "region": region,
                    "platform": item,
                    "category": "search_engine" if item in SEARCH_ENGINES else "browser",
                    "value_percent": float(round(value, 2)),
                }
            )
    return pd.DataFrame(rows)


def create_search_engine_share() -> pd.DataFrame:
    dates = create_date_index()
    rows = []
    base_values = [70.0, 8.0, 6.0, 5.0, 4.0, 3.0]
    growth = [-5.0, 2.0, -1.0, 1.5, 0.5, 0.0]
    for region in REGIONS:
        df = create_share_matrix(SEARCH_ENGINES, base_values, growth, dates, region)
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


def create_browser_share() -> pd.DataFrame:
    dates = create_date_index()
    rows = []
    base_values = [55.0, 20.0, 8.0, 6.0, 7.0, 4.0]
    growth = [-3.0, 0.0, 2.0, -2.0, 0.5, 0.5]
    for region in REGIONS:
        df = create_share_matrix(BROWSERS, base_values, growth, dates, region)
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


def create_ai_tool_traffic() -> pd.DataFrame:
    dates = create_date_index()
    rows = []
    tool_baseline = {
        "ChatGPT": 5.0,
        "Gemini": 1.0,
        "Copilot": 2.5,
        "Perplexity": 1.2,
        "Claude": 0.8,
        "DeepSeek": 0.3,
        "Grok": 0.2,
    }
    for region in REGIONS:
        region_factor = 1.0 + 0.1 * REGIONS.index(region)
        for tool in AI_TOOLS:
            base = tool_baseline[tool] * region_factor
            growth = 40.0 if tool in ["ChatGPT", "Gemini"] else 20.0
            trend = base + np.linspace(0, growth, len(dates))
            trend *= seasonal_factor(dates, amplitude=0.12)
            trend += np.random.normal(0, 1.5, len(dates))
            trend = np.clip(trend, 0, None)
            visits = trend * 100000
            share = np.clip(5 + trend / 20, 0, 100)
            for date, v, s in zip(dates, visits, share):
                rows.append(
                    {
                        "date": date.strftime("%Y-%m-%d"),
                        "region": region,
                        "ai_tool": tool,
                        "visits": int(round(v)),
                        "traffic_share_percent": float(round(min(s, 100), 2)),
                        "avg_visit_duration": float(round(120 + np.random.normal(0, 10), 1)),
                        "pages_per_visit": float(round(3 + np.random.normal(0, 0.4), 2)),
                        "bounce_rate": float(round(40 + np.random.normal(0, 5), 2)),
                    }
                )
    return pd.DataFrame(rows)


def create_events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_date": "2020-11-30",
                "event_name": "ChatGPT launch",
                "event_type": "product",
                "affected_platform": "ChatGPT",
                "description": "OpenAI releases ChatGPT, accelerating interest in AI assistants.",
            },
            {
                "event_date": "2023-05-10",
                "event_name": "Gemini launch",
                "event_type": "product",
                "affected_platform": "Gemini",
                "description": "Google launches Gemini, boosting AI adoption in search contexts.",
            },
            {
                "event_date": "2023-11-15",
                "event_name": "Copilot launch",
                "event_type": "product",
                "affected_platform": "Copilot",
                "description": "Microsoft Copilot becomes available, linking AI assistant experiences to search and browser use.",
            },
            {
                "event_date": "2024-04-01",
                "event_name": "AI Overviews release",
                "event_type": "feature",
                "affected_platform": "Google",
                "description": "Search engines add AI overview experiences, altering traditional search behavior.",
            },
        ]
    )


def write_demo_data() -> None:
    ensure_directory(GOOGLE_TRENDS_OUTPUT.parent)
    ensure_directory(SEARCH_ENGINE_CSV.parent)
    ensure_directory(BROWSER_CSV.parent)
    ensure_directory(AI_TRAFFIC_CSV.parent)
    ensure_directory(EVENTS_CSV.parent)

    create_google_trends().to_csv(GOOGLE_TRENDS_OUTPUT, index=False)
    create_search_engine_share().to_csv(SEARCH_ENGINE_CSV, index=False)
    create_browser_share().to_csv(BROWSER_CSV, index=False)
    create_ai_tool_traffic().to_csv(AI_TRAFFIC_CSV, index=False)
    create_events().to_csv(EVENTS_CSV, index=False)

    print("Demo data files created:")
    print(f"- {GOOGLE_TRENDS_OUTPUT}")
    print(f"- {SEARCH_ENGINE_CSV}")
    print(f"- {BROWSER_CSV}")
    print(f"- {AI_TRAFFIC_CSV}")
    print(f"- {EVENTS_CSV}")


if __name__ == "__main__":
    write_demo_data()
