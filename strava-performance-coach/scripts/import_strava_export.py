"""Import a Strava account export zip into the local database."""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.processing.strava_export_importer import StravaExportImporter


def parse_args():
    parser = argparse.ArgumentParser(description="Import Strava export zip offline.")
    parser.add_argument("zip_path", help="Path to Strava export zip.")
    parser.add_argument(
        "--database",
        default=settings.duckdb_path,
        help="DuckDB database path.",
    )
    parser.add_argument(
        "--skip-analytics",
        action="store_true",
        help="Only import activities; do not refresh metrics/recommendations.",
    )
    parser.add_argument(
        "--only-new",
        action="store_true",
        help="Skip activities already present in the database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    with StravaExportImporter(args.zip_path, database_path=args.database) as importer:
        result = importer.import_export(
            refresh_outputs=not args.skip_analytics,
            only_new=args.only_new,
        )

    print(
        "Imported Strava export: athlete={athlete}, rows={rows}, loaded={loaded}, "
        "skipped={skipped}, failed={failed}, "
        "streams={streams} points/{stream_activities} activities, "
        "metrics={metrics}, recommendations={recommendations}".format(
            athlete=result.athlete_id,
            rows=result.rows_seen,
            loaded=result.activities_loaded,
            skipped=result.activities_skipped,
            failed=result.activities_failed,
            streams=result.stream_points_loaded,
            stream_activities=result.activities_with_streams,
            metrics=result.metrics_rows,
            recommendations=result.recommendations_created,
        )
    )


if __name__ == "__main__":
    main()
