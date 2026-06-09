-- ============================================================================
-- Strava Performance Coach - DuckDB Schema
-- Medallion Architecture: Bronze -> Silver -> Gold
-- ============================================================================

-- ============================================================================
-- BRONZE LAYER - Raw Data (Exactly as received from Strava)
-- ============================================================================

CREATE SEQUENCE IF NOT EXISTS seq_raw_activity_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_raw_event_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_stg_event_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_activity_metric_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_daily_summary_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_weekly_summary_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_recommendation_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_data_load_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_data_quality_metric_id START 1;

-- Raw Strava Activities (webhook events received)
CREATE TABLE IF NOT EXISTS raw_strava_activities (
    raw_activity_id INTEGER PRIMARY KEY DEFAULT nextval('seq_raw_activity_id'),
    source_activity_id BIGINT NOT NULL,
    athlete_id BIGINT NOT NULL,
    raw_payload JSON NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Raw Strava Events (webhook data)
CREATE TABLE IF NOT EXISTS raw_strava_events (
    raw_event_id INTEGER PRIMARY KEY DEFAULT nextval('seq_raw_event_id'),
    event_type VARCHAR NOT NULL,
    raw_payload JSON NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP
);

-- ============================================================================
-- SILVER LAYER - Cleaned & Normalized Data
-- ============================================================================

-- Staged Activities (normalized, deduplicated)
CREATE TABLE IF NOT EXISTS stg_activities (
    activity_id BIGINT PRIMARY KEY,
    athlete_id BIGINT NOT NULL,
    activity_name VARCHAR NOT NULL,
    activity_type VARCHAR NOT NULL,
    activity_date DATE NOT NULL,
    
    -- Distance and Time
    distance_meters INTEGER NOT NULL,
    distance_km FLOAT GENERATED ALWAYS AS (distance_meters / 1000.0),
    moving_time_seconds INTEGER NOT NULL,
    moving_time_minutes FLOAT GENERATED ALWAYS AS (moving_time_seconds / 60.0),
    elapsed_time_seconds INTEGER NOT NULL,
    elapsed_time_minutes FLOAT GENERATED ALWAYS AS (elapsed_time_seconds / 60.0),
    
    -- Speed and Pace
    average_speed_mps FLOAT,
    average_speed_kmh FLOAT GENERATED ALWAYS AS (average_speed_mps * 3.6),
    max_speed_mps FLOAT,
    average_pace_min_km FLOAT GENERATED ALWAYS AS (
        CASE WHEN distance_km > 0 THEN moving_time_minutes / distance_km ELSE NULL END
    ),
    
    -- Heart Rate
    average_heartrate INTEGER,
    max_heartrate INTEGER,
    
    -- Elevation
    total_elevation_gain FLOAT,
    total_elevation_loss FLOAT,
    calories FLOAT,
    
    -- Other metrics
    kudos_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    photo_count INTEGER DEFAULT 0,
    trainer BOOLEAN DEFAULT FALSE,
    commute BOOLEAN DEFAULT FALSE,
    manual BOOLEAN DEFAULT FALSE,
    private BOOLEAN DEFAULT FALSE,
    flagged BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    CONSTRAINT unique_activity_id UNIQUE(activity_id)
);

CREATE INDEX IF NOT EXISTS idx_stg_activities_athlete ON stg_activities(athlete_id);
CREATE INDEX IF NOT EXISTS idx_stg_activities_date ON stg_activities(activity_date);
CREATE INDEX IF NOT EXISTS idx_stg_activities_type ON stg_activities(activity_type);

-- Activity GPS/stream points from Strava account export files.
CREATE TABLE IF NOT EXISTS activity_streams (
    activity_id BIGINT NOT NULL,
    point_index INTEGER NOT NULL,
    point_time TIMESTAMP,
    latitude DOUBLE,
    longitude DOUBLE,
    elevation_m FLOAT,
    distance_m FLOAT,
    speed_mps FLOAT,
    heartrate INTEGER,
    pace_min_km FLOAT,
    source_file VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, point_index)
);

CREATE INDEX IF NOT EXISTS idx_activity_streams_activity ON activity_streams(activity_id);
CREATE INDEX IF NOT EXISTS idx_activity_streams_time ON activity_streams(point_time);

-- Staged Events (processed)
CREATE TABLE IF NOT EXISTS stg_events (
    event_id INTEGER PRIMARY KEY DEFAULT nextval('seq_stg_event_id'),
    source_event_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    athlete_id BIGINT NOT NULL,
    activity_id BIGINT,
    event_data JSON,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_source_event UNIQUE(source_event_id)
);

CREATE INDEX IF NOT EXISTS idx_stg_events_athlete ON stg_events(athlete_id);
CREATE INDEX IF NOT EXISTS idx_stg_events_type ON stg_events(event_type);

-- ============================================================================
-- GOLD LAYER - Business Insights & Aggregations
-- ============================================================================

-- Activity Metrics (calculated performance scores)
CREATE TABLE IF NOT EXISTS fct_activity_metrics (
    metric_id INTEGER PRIMARY KEY DEFAULT nextval('seq_activity_metric_id'),
    activity_id BIGINT NOT NULL UNIQUE,
    athlete_id BIGINT NOT NULL,
    activity_date DATE NOT NULL,
    
    -- Performance Score (0-100)
    performance_score INTEGER,
    
    -- Training Load (time × HR/max HR)
    training_load FLOAT,
    
    -- Intensity Level (low/moderate/high)
    intensity_level VARCHAR,
    intensity_score INTEGER,
    
    -- Efficiency (distance vs time)
    efficiency_score FLOAT,
    
    -- Fatigue Impact (subjective, can be updated by user)
    fatigue_impact INTEGER,
    
    -- Recovery indicator
    recovery_indicator VARCHAR,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_activity_metrics_activity FOREIGN KEY (activity_id) REFERENCES stg_activities(activity_id)
);

CREATE INDEX IF NOT EXISTS idx_fct_activity_metrics_athlete ON fct_activity_metrics(athlete_id);
CREATE INDEX IF NOT EXISTS idx_fct_activity_metrics_date ON fct_activity_metrics(activity_date);
CREATE INDEX IF NOT EXISTS idx_fct_activity_metrics_score ON fct_activity_metrics(performance_score);

-- Daily Summary (aggregated by day)
CREATE TABLE IF NOT EXISTS daily_summary (
    summary_id INTEGER PRIMARY KEY DEFAULT nextval('seq_daily_summary_id'),
    athlete_id BIGINT NOT NULL,
    summary_date DATE NOT NULL UNIQUE,
    
    -- Daily totals
    num_activities INTEGER DEFAULT 0,
    total_distance_km FLOAT DEFAULT 0,
    total_moving_time_minutes FLOAT DEFAULT 0,
    total_elapsed_time_minutes FLOAT DEFAULT 0,
    
    -- Heart Rate stats
    avg_heartrate INTEGER,
    max_heartrate INTEGER,
    
    -- Performance stats
    avg_performance_score FLOAT,
    total_training_load FLOAT,
    
    -- Elevation
    total_elevation_gain FLOAT DEFAULT 0,
    
    -- Activity breakdown
    num_runs INTEGER DEFAULT 0,
    num_rides INTEGER DEFAULT 0,
    num_walks INTEGER DEFAULT 0,
    num_hikes INTEGER DEFAULT 0,
    
    -- Daily score (0-100)
    daily_score INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_summary_athlete ON daily_summary(athlete_id);
CREATE INDEX IF NOT EXISTS idx_daily_summary_date ON daily_summary(summary_date);

-- Weekly Summary (aggregated by ISO week)
CREATE TABLE IF NOT EXISTS weekly_summary (
    summary_id INTEGER PRIMARY KEY DEFAULT nextval('seq_weekly_summary_id'),
    athlete_id BIGINT NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    
    -- Weekly totals
    num_activities INTEGER DEFAULT 0,
    total_distance_km FLOAT DEFAULT 0,
    total_moving_time_minutes FLOAT DEFAULT 0,
    
    -- Heart Rate stats
    avg_heartrate INTEGER,
    max_heartrate INTEGER,
    
    -- Performance
    avg_performance_score FLOAT,
    total_training_load FLOAT,
    
    -- Elevation
    total_elevation_gain FLOAT DEFAULT 0,
    
    -- Weekly status
    weekly_score INTEGER,
    fatigue_level VARCHAR,
    recovery_status VARCHAR,
    
    -- Recommendations pending
    has_recommendation BOOLEAN DEFAULT FALSE,
    recommendation_text VARCHAR,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_weekly_summary UNIQUE(athlete_id, iso_year, iso_week)
);

CREATE INDEX IF NOT EXISTS idx_weekly_summary_athlete ON weekly_summary(athlete_id);
CREATE INDEX IF NOT EXISTS idx_weekly_summary_date ON weekly_summary(week_start);
CREATE INDEX IF NOT EXISTS idx_weekly_summary_iso ON weekly_summary(iso_year, iso_week);

-- Coach Recommendations (AI-generated insights)
CREATE TABLE IF NOT EXISTS coach_recommendations (
    recommendation_id INTEGER PRIMARY KEY DEFAULT nextval('seq_recommendation_id'),
    athlete_id BIGINT NOT NULL,
    activity_id BIGINT,
    week_id INTEGER,
    
    recommendation_type VARCHAR NOT NULL,  -- 'pace_adjustment', 'recovery_needed', 'intensity_increase', etc.
    recommendation_text VARCHAR NOT NULL,
    confidence_score FLOAT,  -- 0-1
    
    action_suggested VARCHAR,
    priority_level VARCHAR,  -- 'low', 'medium', 'high'
    
    status VARCHAR DEFAULT 'pending',  -- 'pending', 'accepted', 'rejected', 'completed'
    status_updated_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_coach_recommendations_athlete ON coach_recommendations(athlete_id);
CREATE INDEX IF NOT EXISTS idx_coach_recommendations_status ON coach_recommendations(status);
CREATE INDEX IF NOT EXISTS idx_coach_recommendations_priority ON coach_recommendations(priority_level);

-- ============================================================================
-- UTILITY TABLES
-- ============================================================================

-- Athlete Profile Cache (for quick lookups)
CREATE TABLE IF NOT EXISTS athlete_profile (
    athlete_id BIGINT PRIMARY KEY,
    athlete_name VARCHAR NOT NULL,
    profile_picture_url VARCHAR,
    city VARCHAR,
    state VARCHAR,
    country VARCHAR,
    sex VARCHAR,
    premium BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Activity Types (reference table)
CREATE TABLE IF NOT EXISTS ref_activity_types (
    activity_type VARCHAR PRIMARY KEY,
    display_name VARCHAR NOT NULL,
    icon_emoji VARCHAR,
    is_cardio BOOLEAN DEFAULT TRUE,
    description VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert common activity types
INSERT OR IGNORE INTO ref_activity_types (activity_type, display_name, icon_emoji, is_cardio) VALUES
    ('Run', 'Running', '🏃', TRUE),
    ('Ride', 'Cycling', '🚴', TRUE),
    ('Walk', 'Walking', '🚶', TRUE),
    ('Hike', 'Hiking', '⛰️', TRUE),
    ('Swim', 'Swimming', '🏊', TRUE),
    ('Workout', 'Workout', '💪', TRUE),
    ('Yoga', 'Yoga', '🧘', FALSE),
    ('Pilates', 'Pilates', '🧘‍♀️', FALSE);

-- Data Load Tracking
CREATE TABLE IF NOT EXISTS data_load_history (
    load_id INTEGER PRIMARY KEY DEFAULT nextval('seq_data_load_id'),
    load_type VARCHAR NOT NULL,  -- 'initial', 'incremental', 'full_refresh'
    load_start TIMESTAMP NOT NULL,
    load_end TIMESTAMP,
    num_records_loaded INTEGER,
    num_records_failed INTEGER,
    status VARCHAR DEFAULT 'running',  -- 'running', 'completed', 'failed'
    error_message VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Data Quality Metrics
CREATE TABLE IF NOT EXISTS data_quality_metrics (
    metric_id INTEGER PRIMARY KEY DEFAULT nextval('seq_data_quality_metric_id'),
    check_date DATE NOT NULL,
    check_type VARCHAR NOT NULL,  -- 'bronze_completeness', 'silver_validation', etc.
    total_records INTEGER,
    valid_records INTEGER,
    invalid_records INTEGER,
    quality_score FLOAT,  -- 0-1
    details JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- VIEWS for Easy Access
-- ============================================================================

-- Recent Activities View
CREATE OR REPLACE VIEW v_recent_activities AS
SELECT 
    a.activity_id,
    a.athlete_id,
    a.activity_name,
    a.activity_type,
    a.activity_date,
    a.distance_km,
    a.moving_time_minutes,
    a.average_speed_kmh,
    a.average_heartrate,
    a.average_pace_min_km,
    m.performance_score,
    m.intensity_level
FROM stg_activities a
LEFT JOIN fct_activity_metrics m ON a.activity_id = m.activity_id
WHERE a.activity_date >= CURRENT_DATE - INTERVAL 30 DAY
ORDER BY a.activity_date DESC;

-- Performance Trend View
CREATE OR REPLACE VIEW v_performance_trend AS
SELECT
    d.athlete_id,
    d.summary_date,
    d.num_activities,
    d.total_distance_km,
    d.total_moving_time_minutes,
    d.avg_performance_score,
    d.daily_score,
    w.weekly_score,
    w.fatigue_level
FROM daily_summary d
LEFT JOIN weekly_summary w 
    ON d.athlete_id = w.athlete_id 
    AND d.summary_date >= w.week_start 
    AND d.summary_date <= w.week_end
ORDER BY d.athlete_id, d.summary_date DESC;

-- Coach Recommendations View (pending only)
CREATE OR REPLACE VIEW v_pending_recommendations AS
SELECT
    c.recommendation_id,
    c.athlete_id,
    c.recommendation_type,
    c.recommendation_text,
    c.priority_level,
    c.confidence_score,
    c.created_at
FROM coach_recommendations c
WHERE c.status = 'pending'
ORDER BY c.priority_level DESC, c.confidence_score DESC;

-- Activity Type Distribution
CREATE OR REPLACE VIEW v_activity_distribution AS
SELECT
    a.athlete_id,
    a.activity_type,
    COUNT(*) as num_activities,
    SUM(a.distance_km) as total_distance_km,
    AVG(a.average_speed_kmh) as avg_speed_kmh,
    AVG(a.average_heartrate) as avg_heartrate
FROM stg_activities a
WHERE a.activity_date >= CURRENT_DATE - INTERVAL 30 DAY
GROUP BY a.athlete_id, a.activity_type
ORDER BY a.athlete_id, num_activities DESC;

-- ============================================================================
-- INDEXES for Performance
-- ============================================================================

-- Common query patterns
CREATE INDEX IF NOT EXISTS idx_raw_strava_activities_athlete ON raw_strava_activities(athlete_id);
CREATE INDEX IF NOT EXISTS idx_raw_strava_activities_imported ON raw_strava_activities(imported_at);

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
