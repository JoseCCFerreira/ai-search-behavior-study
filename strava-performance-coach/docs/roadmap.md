# Project Roadmap

## Vision
Create a personal performance coaching system that uses your Strava data to provide explainable, actionable insights and recommendations for training optimization.

## Phases

### ✅ Phase 1: Project Setup
**Status**: In Progress
- Create project structure
- Set up configuration management
- Create documentation framework
- Initialize Git repository
- Create README and guides

**Deliverables**:
- Folder structure
- Basic configuration
- Requirements and dependencies
- Git repository ready

---

### 📋 Phase 2: Strava Developer Configuration
**Status**: Not Started
- Create Strava Developer app
- Document OAuth 2.0 flow
- Create local token storage mechanism
- Implement token refresh logic

**Deliverables**:
- `docs/strava_api.md`
- `src/auth/strava_oauth.py`
- Token management helpers

---

### 🗄️ Phase 3: Database Setup
**Status**: Not Started
- Design DuckDB schema
- Create schema migration scripts
- Set up database connection pool
- Create data insertion utilities

**Deliverables**:
- `database/schema.sql`
- `src/database/db_connection.py`
- `src/database/create_database.py`
- Database ready for data

---

### 🔌 Phase 4: Strava API Client
**Status**: Not Started
- Create HTTP client for Strava API
- Implement activity fetching
- Add error handling and rate limiting
- Create mock responses for testing

**Deliverables**:
- `src/connector/strava_client.py`
- Rate limit handling
- Error recovery

---

### 🪝 Phase 5: Webhook Integration
**Status**: Not Started
- Create FastAPI server
- Implement webhook validation endpoint
- Implement webhook event processing
- Create event queue/queue processing

**Deliverables**:
- `src/connector/strava_webhook.py`
- `src/connector/webhook_events.py`
- Webhook listener running on localhost

---

### 🧹 Phase 6: Data Normalization
**Status**: Not Started
- Create unit conversion functions
- Implement data cleaning
- Add data validation
- Generate quality reports

**Deliverables**:
- `src/processing/normalize_activities.py`
- `src/processing/clean_activities.py`
- `src/processing/data_quality.py`
- Pipeline tested with mock data

---

### 📊 Phase 7: Performance Metrics
**Status**: Not Started
- Implement Performance Score (0-100)
- Implement Training Load calculation
- Implement Fatigue Score
- Implement Readiness Score
- Implement Trend Analysis

**Deliverables**:
- `src/metrics/performance_score.py`
- `src/metrics/training_load.py`
- `src/metrics/fatigue_score.py`
- `src/metrics/readiness_score.py`
- `src/metrics/trend_analysis.py`
- All metrics tested and documented

---

### 🧠 Phase 8: Coach Engine
**Status**: Not Started
- Create rule-based recommendation system
- Implement recommendation types
- Add explanation generation
- Create confidence scoring

**Deliverables**:
- `src/coach/rule_based_coach.py`
- `src/coach/recommendation_engine.py`
- `src/coach/coach_explanations.py`
- Coach tested with various scenarios

---

### 📈 Phase 9: Streamlit Dashboard
**Status**: Not Started
- Create main dashboard (`app/streamlit_app.py`)
- Create 7 dashboard pages
- Implement filters and interactivity
- Add KPI cards and visualizations
- Create reusable components

**Deliverables**:
- `app/streamlit_app.py`
- `app/pages/01_Overview.py`
- `app/pages/02_Activities.py`
- `app/pages/03_Performance.py`
- `app/pages/04_Training_Load.py`
- `app/pages/05_Fatigue_Recovery.py`
- `app/pages/06_Coach.py`
- `app/pages/07_Machine_Learning.py`
- `app/components/filters.py`
- `app/components/charts.py`
- `app/components/kpi_cards.py`

---

### 🤖 Phase 10: Machine Learning (Optional)
**Status**: Not Started
- Implement activity clustering
- Implement performance prediction
- Add model evaluation utilities
- Create explainability features

**Deliverables**:
- `src/ml/clustering.py`
- `src/ml/performance_prediction.py`
- `src/ml/model_evaluation.py`
- ML features in dashboard

---

### ✅ Phase 11: Testing & Quality
**Status**: Not Started
- Create comprehensive test suite
- Add code coverage reporting
- Create integration tests
- Add performance tests

**Deliverables**:
- `tests/test_database.py`
- `tests/test_strava_client.py`
- `tests/test_metrics.py`
- `tests/test_processing.py`
- `tests/test_coach.py`
- >80% code coverage

---

### 🎯 Phase 12: Mock Data Pipeline
**Status**: Not Started
- Create realistic mock activities
- Generate various activity types
- Create date variation
- Load mock data into database

**Deliverables**:
- `data/mock/mock_activities.csv`
- `src/database/load_mock_data.py`
- Dashboard fully functional with mock data

---

### 📚 Phase 13: Documentation & GitHub Setup
**Status**: Not Started
- Create comprehensive README
- Create architecture documentation
- Create API documentation
- Set up GitHub repository
- Create GitHub issues and projects
- Configure CI/CD basics

**Deliverables**:
- Complete README.md
- docs/strava_api.md
- docs/data_model.md
- docs/metrics.md
- docs/dashboard.md
- docs/coach_logic.md
- GitHub repository public/ready
- Initial commits and branches

---

### 🚀 Phase 14: Future Enhancements
**Status**: Future
- Advanced ML models
- Sleep/HRV integration
- Garmin Connect support
- Local web app hardening
- Performance optimization
- Mobile app (if needed)
- Cloud deployment (if needed)

---

## Milestone Summary

| Milestone | Target | Dependencies |
|-----------|--------|--------------|
| MVP Local | Phase 6 | Phases 1-6 complete |
| Dashboard Working | Phase 9 | Phases 1-9 complete |
| Live Strava Sync | Phase 5 | Phases 1-5 complete |
| Coach Active | Phase 8 | Phases 1-8 complete |
| Production Ready | Phase 13 | All phases complete |

## Success Criteria

### Phase 1 Complete
- ✅ Project initialized with proper structure
- ✅ Git repository ready
- ✅ Development environment documented
- ✅ Can run `pip install -r requirements.txt`

### MVP Complete (End of Phase 6)
- ✅ Database schema created
- ✅ Mock data loaded
- ✅ Data pipeline working
- ✅ Normalization functions tested
- ✅ Dashboard displays mock data

### Integration Complete (End of Phase 9)
- ✅ Real Strava OAuth working
- ✅ Webhook receiving events
- ✅ Activities automatically extracted
- ✅ Dashboard updates in real-time

### Coach Active (End of Phase 8)
- ✅ Performance metrics calculated
- ✅ Coach generates recommendations
- ✅ Explanations clear and helpful
- ✅ Recommendations tested with scenarios

### Production Ready (End of Phase 13)
- ✅ All tests passing
- ✅ Code coverage >80%
- ✅ Documentation complete
- ✅ GitHub repository ready
- ✅ Local deployment working
- ✅ Ready for daily use

## Known Constraints

1. **Development Stage**: This is an MVP. Not all edge cases are handled.
2. **Privacy First**: Only personal use. Strava data not shared.
3. **Local Only**: All data stored locally. No cloud sync in MVP.
4. **Strava API**: Limited by Strava rate limits (600 req/15min).
5. **No Clinical Advice**: Coach recommendations are informational only.

## Dependencies & Blockers

- **Phase 2 blocker**: Need Strava Developer account
- **Phase 5 blocker**: Need way to expose localhost (ngrok, etc.)
- **Phase 9 blocker**: Requires Phases 3-8 complete

## Notes

- Each phase should be independently testable
- Commit after each phase with meaningful messages
- Use feature branches for each phase
- Update this roadmap as priorities change
- Keep documentation in sync with code
