"""Run a Strava activity sync from the command line."""

import argparse
import logging
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.connector import StravaConnector


def parse_args():
    parser = argparse.ArgumentParser(description="Sync Strava activities into DuckDB.")
    parser.add_argument("--days", type=int, default=30, help="Sync activities from the last N days.")
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Check at most once per day and load only new activity IDs.",
    )
    parser.add_argument("--per-page", type=int, default=200, help="Strava page size, max 200.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages for test runs.")
    parser.add_argument(
        "--hydrate-details",
        action="store_true",
        help="Fetch detailed activity payloads before saving.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    after = int(time.time()) - args.days * 24 * 60 * 60
    with StravaConnector() as connector:
        if args.daily:
            result = connector.sync_daily_if_needed(
                initial_days=args.days,
                per_page=args.per_page,
                max_pages=args.max_pages,
                hydrate_details=args.hydrate_details,
            )
        else:
            result = connector.sync_activities(
                after=after,
                per_page=args.per_page,
                max_pages=args.max_pages,
                hydrate_details=args.hydrate_details,
            )

    print(
        "Strava sync {status}: fetched={fetched}, loaded={loaded}, failed={failed}, "
        "metrics={metrics}, recommendations={recommendations}".format(
            status=result.status,
            fetched=result.activities_fetched,
            loaded=result.activities_loaded,
            failed=result.activities_failed,
            metrics=result.analytics_metrics_rows,
            recommendations=result.recommendations_created,
        )
    )


if __name__ == "__main__":
    main()
