# System Architecture

## Overview

**strava-performance-coach** is a personal performance analysis and coaching system that integrates with Strava. It automatically extracts your activities, stores them locally, analyzes your performance, and provides data-driven coaching recommendations.

The system is designed to be:
- **Privacy-focused**: All data stored locally (DuckDB)
- **Modular**: Clean separation of concerns
- **Explainable**: All metrics and recommendations are clearly explained
- **Scalable**: Prepared for future expansions

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Strava Platform                      │
│  (OAuth 2.0, Webhooks, REST API)                        │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
        ┌──────────────────┐
        │  Strava Webhook  │
        │   + API Client   │
        │   (FastAPI)      │
        └────────┬─────────┘
                 │
        ┌────────▼──────────┐
        │  Raw Data Layer   │
        │  (DuckDB)         │
        │ - raw_events      │
        │ - raw_activities  │
        └────────┬──────────┘
                 │
        ┌────────▼──────────┐
        │  Processing Layer │
        │ - Normalization   │
        │ - Cleaning        │
        │ - Validation      │
        └────────┬──────────┘
                 │
        ┌────────▼──────────┐
        │  Analytics Layer  │
        │ - Metrics         │
        │ - Aggregations    │
        │ - Scores          │
        └────────┬──────────┘
                 │
        ┌────────▼────────┐
        │  Coach Engine   │
        │ - Rule-based    │
        │ - ML Models     │
        └────────┬────────┘
                 │
    ┌────────────▼──────────────┐
    │   Presentation Layer      │
    │  (Streamlit Dashboard)    │
    │  + Multiple Pages         │
    └───────────────────────────┘
```

## Components

### 1. Strava OAuth & Authentication (`src/auth/`)
- **Responsibility**: Manage Strava OAuth 2.0 flow
- **Key Functions**:
  - Generate authorization URL
  - Exchange code for tokens
  - Refresh access tokens
  - Store credentials securely (local file with permissions)

### 2. Strava Connector (`src/connector/`)
- **Responsibility**: Handle API communication and webhooks
- **Components**:
  - `strava_client.py`: HTTP client for Strava API v3
  - `strava_webhook.py`: FastAPI endpoints for webhook validation and events
  - `webhook_events.py`: Event processing logic

### 3. Data Layer (`src/database/`)
- **Responsibility**: Database operations and schema management
- **Tech**: DuckDB (local, SQL-based)
- **Key Functions**:
  - Create/manage schema
  - Raw data ingestion
  - Query abstraction layer

### 4. Processing Layer (`src/processing/`)
- **Responsibility**: Data cleaning, normalization, validation
- **Key Operations**:
  - Convert units (m → km, s → min, m/s → km/h)
  - Calculate derived metrics (pace, efficiency)
  - Handle nulls and outliers
  - Data quality checks

### 5. Analytics Layer (`src/metrics/`)
- **Responsibility**: Calculate performance metrics
- **Key Metrics**:
  - Performance Score (0-100)
  - Training Load (cumulative stress)
  - Fatigue Score (accumulated fatigue)
  - Readiness Score (ability to train)
  - Trend Analysis (improvement detection)

### 6. Coach Engine (`src/coach/`)
- **Responsibility**: Generate recommendations
- **Approach**: Rule-based system with optional ML
- **Output**: Actionable recommendations with explanations

### 7. ML Module (`src/ml/`)
- **Responsibility**: Optional advanced analysis
- **Capabilities**:
  - Activity clustering
  - Performance prediction
  - Pattern detection

### 8. Dashboard (`app/`)
- **Responsibility**: User-facing interface
- **Tech**: Streamlit
- **Pages**: Overview, Activities, Performance, Training Load, Fatigue, Coach, ML

## Data Model

### Raw Layer
```
raw_strava_events
├── Event ID
├── Object Type (activity, athlete)
├── Aspect Type (create, update, delete)
└── Raw Payload (JSON)

raw_strava_activities
├── Raw Activity ID
├── Source Activity ID (from Strava)
└── Raw Payload (JSON from API)
```

### Staging Layer
```
stg_activities
├── Activity ID (local unique)
├── Source Activity ID (Strava)
├── Basic Info (name, type, date)
├── Distances (km, elevation)
├── Times (duration, moving)
├── Effort (pace, HR, power)
└── Device Info
```

### Fact Layer
```
fct_activity_metrics
├── Activity ID
├── Performance Score
├── Training Load
├── Intensity Score
└── Other Calculated Metrics

daily_summary
├── Date
├── Total Activities
├── Total Distance
├── Aggregated Load
└── Daily Metrics

weekly_summary
├── Week ID
├── Weekly Totals
├── Weekly Load
└── Acute/Chronic Ratio
```

### Recommendations
```
coach_recommendations
├── Recommendation ID
├── Date Generated
├── Type (rest, easy, intervals, etc.)
├── Explanation Text
├── Underlying Metrics
└── Confidence Level
```

## Data Flow

### New Activity Webhook Flow
```
1. Strava sends webhook event
2. FastAPI endpoint receives event
3. Event stored in raw_strava_events
4. If activity created:
   a. Fetch full activity from Strava API
   b. Store raw payload in raw_strava_activities
   c. Normalize to stg_activities
   d. Calculate metrics → fct_activity_metrics
   e. Update daily_summary
   f. Update weekly_summary
   g. Dashboard data refreshed
5. Event marked as processed
```

### Manual Data Load Flow
```
1. User triggers manual sync
2. Fetch recent activities from Strava API
3. Skip already stored (by source_activity_id)
4. Process new activities through pipeline
5. Update summaries
6. Refresh dashboard
```

## Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Web Framework | FastAPI | Fast, type-safe, easy to test |
| Dashboard | Streamlit | Rapid dashboard development |
| Database | DuckDB | Local, SQL, OLAP-optimized, no setup |
| Data Processing | Pandas | Flexible, familiar, excellent ecosystem |
| Visualization | Plotly | Interactive, publication-ready |
| ML | Scikit-learn | Simple, interpretable models |
| Testing | Pytest | Industry standard, excellent fixtures |
| Secrets | .env file | Simple, secure for local development |

## Security Considerations

1. **Credentials**: 
   - Stored in `.env` (not in repo)
   - Read with python-dotenv
   - Never log tokens

2. **Local Storage**:
   - All data stored in `database/` directory
   - Database file not in version control
   - File permissions restricted (should be 0600)

3. **API Communication**:
   - Use HTTPS for Strava API
   - Validate webhook verify token
   - Rate limit awareness

4. **Data Privacy**:
   - Only store own activities
   - Don't upload to external services
   - No public sharing of raw data

## Deployment Scenarios

### Local Development
- Python venv
- FastAPI with uvicorn
- Streamlit dev server
- Local DuckDB

### Local Persistent
- Python venv
- FastAPI as service/daemon
- Streamlit as web app
- DuckDB database

### Future: Cloud Deployment
- Cloud function for webhooks
- Cloud database (optional)
- Cloud hosting for dashboard
- Proper secrets management

## Extensibility Points

1. **New Metrics**: Add to `src/metrics/`
2. **New Data Sources**: Add connector in `src/connector/`
3. **Dashboard Pages**: Add to `app/pages/`
4. **ML Models**: Add to `src/ml/`
5. **Data Validation**: Extend `src/processing/data_quality.py`

## Performance Considerations

1. **Database**:
   - DuckDB optimized for analytical queries
   - Proper indexing on common filters
   - Partitioning by date when large

2. **Processing**:
   - Incremental updates (only new activities)
   - Efficient pandas operations
   - Caching summaries

3. **API**:
   - Strava rate limits: 600 req/15min per token
   - Respect retry-after headers
   - Implement exponential backoff

## Monitoring & Logging

- Logs written to `logs/` directory
- Structured logging with timestamps
- Error tracking in webhook processing
- Dashboard for data quality checks

## Future Enhancements

- Integration with Garmin Connect
- Sleep and HRV data (if available)
- Advanced ML predictions
- Mobile app
- Cloud sync
- Social features (anonymous benchmarking)
