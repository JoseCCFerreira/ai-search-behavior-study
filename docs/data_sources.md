# Data Sources

## Google Trends

- Use `pytrends` to fetch keyword interest over time.
- The project supports manual CSV exports from Google Trends.
- Keywords are normalized to compare AI tools and search interest.

## StatCounter GlobalStats

- Import search engine market share CSV files.
- Import browser market share CSV files.
- The expected schema includes `date`, `region`, `platform`, `category`, and `value_percent`.

## Similarweb / AI traffic

- The project supports manual CSV import for AI traffic metrics.
- Expected fields include `date`, `region`, `ai_tool`, `visits`, `traffic_share_percent`, `avg_visit_duration`, `pages_per_visit`, and `bounce_rate`.

## Events

- Use `events.csv` to store major product launches, feature announcements, and regulatory changes.
- Fields: `event_date`, `event_name`, `event_type`, `affected_platform`, `description`.

## Synthetic data

- The demo data generator creates realistic synthetic time series from January 2019 to today.
- Synthetic data is useful for development and dashboard testing.
- Real data should replace synthetic CSVs in `data/raw/`.
