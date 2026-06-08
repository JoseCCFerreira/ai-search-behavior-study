# Strava Performance Coach

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A personal performance coaching application that integrates with Strava to provide data-driven insights, training analysis, and personalized recommendations.

## 🎯 Objective

Analyze your Strava activities automatically, calculate performance metrics, track training load, identify fatigue patterns, and receive personalized coaching recommendations - all locally on your machine with complete privacy.

**Key Features**:
- 🔐 **Privacy First**: All data stored locally (DuckDB)
- 📊 **Real-time Sync**: Automatic activity extraction via Strava webhooks
- 📈 **Performance Metrics**: Track pace, efficiency, training load, fatigue
- 🧠 **Coach Recommendations**: Rule-based coaching with explanations
- 📱 **Interactive Dashboard**: Streamlit-based analytics interface
- 🤖 **Optional ML**: Activity clustering and performance prediction
- 🔄 **Scalable Architecture**: Modular design ready for expansion

## 📋 System Architecture

```
Strava API & Webhooks
         ↓
    FastAPI Server (Webhook Receiver)
         ↓
    DuckDB (Local Database)
         ↓
    Processing Pipeline (Normalization, Validation, Calculations)
         ↓
    Analytics Layer (Metrics, Scores, Summaries)
         ↓
    Coach Engine (Rule-based Recommendations)
         ↓
    Streamlit Dashboard (Interactive UI)
```

See [Architecture Documentation](docs/architecture.md) for detailed system design.

## 🛠️ Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Framework** | FastAPI | 0.109+ |
| **Dashboard** | Streamlit | 1.28+ |
| **Database** | DuckDB | 0.9+ |
| **Data Processing** | Pandas | 2.1+ |
| **Visualization** | Plotly | 5.18+ |
| **Machine Learning** | Scikit-learn | 1.3+ |
| **Testing** | Pytest | 7.4+ |
| **Python** | 3.9+ | |

## 📁 Project Structure

```
strava-performance-coach/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── pyproject.toml              # Project metadata
├── .gitignore                  # Git ignore rules
├── .env.example                # Environment variables template
│
├── config/
│   ├── __init__.py
│   └── settings.py             # Configuration management
│
├── data/                        # Data storage
│   ├── raw/                    # Raw data from Strava
│   ├── processed/              # Processed data
│   └── mock/                   # Mock data for testing
│
├── database/
│   ├── schema.sql              # DuckDB schema
│   └── strava_coach.duckdb     # Database file (gitignored)
│
├── docs/                        # Documentation
│   ├── architecture.md         # System design
│   ├── roadmap.md              # Development roadmap
│   ├── strava_api.md           # Strava OAuth setup
│   ├── data_model.md           # Data schema details
│   └── ...
│
├── src/                         # Source code
│   ├── auth/                   # Strava OAuth
│   ├── connector/              # Strava API + Webhooks
│   ├── database/               # Database operations
│   ├── processing/             # Data normalization & cleaning
│   ├── metrics/                # Performance metrics
│   ├── coach/                  # Recommendation engine
│   ├── ml/                     # Machine learning (optional)
│   └── utils/                  # Utilities
│
├── app/                         # Streamlit dashboard
│   ├── streamlit_app.py        # Main app
│   ├── pages/                  # Dashboard pages
│   │   ├── 01_Overview.py
│   │   ├── 02_Activities.py
│   │   ├── 03_Performance.py
│   │   ├── 04_Training_Load.py
│   │   ├── 05_Fatigue_Recovery.py
│   │   ├── 06_Coach.py
│   │   └── 07_Machine_Learning.py
│   └── components/             # Reusable components
│
├── notebooks/                   # Jupyter notebooks
│   ├── 01_explore_strava_data.ipynb
│   ├── 02_metrics_exploration.ipynb
│   └── 03_coach_logic_exploration.ipynb
│
└── tests/                       # Unit tests
    ├── test_database.py
    ├── test_strava_client.py
    ├── test_metrics.py
    └── ...
```

## 🚀 Quick Start

### Prerequisites
- Python 3.9 or higher
- Strava account (free tier OK)
- Git
- ~500MB disk space

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/strava-performance-coach.git
cd strava-performance-coach
```

### 2. Create Virtual Environment

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your settings
# For now, you can leave defaults for testing
```

### 5. Run Tests

```bash
pytest -v
```

### 6. Initialize Database

```bash
python src/database/create_database.py
```

## 📖 Usage

### Run Streamlit Dashboard

```bash
streamlit run app/streamlit_app.py
```

Dashboard opens at `http://localhost:8501`

### Run FastAPI Server (Webhooks)

In a separate terminal:

```bash
uvicorn src.connector.strava_webhook:app --reload --port 8000
```

API server at `http://localhost:8000`

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_database.py -v

# Run specific test
pytest tests/test_database.py::test_connection -v
```

## 📊 Project Roadmap

The project is divided into 14 phases:

| Phase | Name | Status |
|-------|------|--------|
| 1 | Project Setup | ✅ Completed |
| 2 | Strava Developer Config | ✅ Completed |
| 3 | Database Setup (Medallion) | ✅ Completed |
| 3 | Database Setup | 📋 To Do |
| 4 | Strava API Client | 📋 To Do |
| 4 | Strava API Client | ✅ Completed |
| 5 | Webhook Integration | 📋 To Do |
| 6 | Data Normalization | 📋 To Do |
| 7 | Performance Metrics | 📋 To Do |
| 8 | Coach Engine | 📋 To Do |
| 9 | Streamlit Dashboard | 📋 To Do |
| 10 | Machine Learning | 📋 To Do |
| 11 | Testing & Quality | 📋 To Do |
| 12 | Mock Data Pipeline | 📋 To Do |
| 13 | GitHub & Workflow | 📋 To Do |
| 14 | Future Enhancements | 🔮 Future |

See [Roadmap](docs/roadmap.md) for detailed phase breakdown.

## 🔐 Security & Privacy

### Local Data
- All data stored in `database/strava_coach.duckdb`
- Database file is **git-ignored** (never committed)
- Local access only

### Credentials
- Strava tokens stored in `.env` (git-ignored)
- Never hardcoded in source
- Use `config/settings.py` for all config access
- Token refresh automated

### Data Usage
- Only your own activities analyzed
- No data uploaded to external services
- No sharing with third parties
- Machine learning is local-only
- Recommendations are informational only

### Best Practices
```bash
# Always keep .env out of git
git check-ignore .env  # Should be true

# Keep database file out of git
git check-ignore database/strava_coach.duckdb  # Should be true

# Never commit sensitive data
grep -r "STRAVA_CLIENT_SECRET" src/  # Should be empty
```

## 📚 Documentation

- **[Architecture](docs/architecture.md)**: System design and components
- **[Roadmap](docs/roadmap.md)**: Development phases and timeline
- **[Setup Guide](docs/setup.md)**: Detailed setup instructions *(Phase 2)*
- **[Strava API](docs/strava_api.md)**: OAuth and webhook setup *(Phase 2)*
- **[Data Model](docs/data_model.md)**: Database schema *(Phase 3)*
- **[Metrics](docs/metrics.md)**: Performance metrics explained *(Phase 7)*
- **[Dashboard](docs/dashboard.md)**: Dashboard features *(Phase 9)*
- **[Coach Logic](docs/coach_logic.md)**: Recommendation logic *(Phase 8)*

## 🔄 Development Workflow

### Working on a New Phase

1. **Create a feature branch**
   ```bash
   git checkout -b feature/phase-X-description
   ```

2. **Make changes**
   ```bash
   # Edit files, write code, run tests
   pytest -v
   ```

3. **Commit with clear message**
   ```bash
   git add .
   git commit -m "Phase X: Feature description"
   ```

4. **Push to GitHub**
   ```bash
   git push origin feature/phase-X-description
   ```

5. **Create Pull Request**
   - Review changes
   - Ensure tests pass
   - Merge to main

### Recommended Branches

```
main                          # Production ready
├── dev                       # Development branch
└── feature/phase-X-...       # Feature branches
    ├── feature/strava-oauth
    ├── feature/strava-webhook
    ├── feature/streamlit-dashboard
    └── feature/performance-coach
```

## 📝 Commit Messages

Follow these patterns:

```bash
# Phase completion
git commit -m "Phase X: Feature description"

# Feature within phase
git commit -m "Phase X: Add specific feature"

# Bug fix
git commit -m "Fix: Brief description"

# Documentation
git commit -m "Docs: Update section"

# Refactor
git commit -m "Refactor: Improve code organization"
```

## 🐛 Common Issues

### ImportError: No module named 'src'

**Solution**: Ensure you're in the project root directory:
```bash
cd strava-performance-coach
python -c "import src.config.settings"  # Should work
```

### DuckDB file locked

**Solution**: Close all connections:
```bash
# Kill any running Python processes
pkill -f python

# Delete and recreate database
rm database/strava_coach.duckdb
python src/database/create_database.py
```

### Streamlit not found

**Solution**: Install all dependencies:
```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

### .env file not loading

**Solution**: Check file location and format:
```bash
# File must be in project root
ls -la | grep .env  # Should show .env

# Check format (no quotes needed)
cat .env | grep STRAVA_CLIENT_ID
```

## 🤝 Contributing

This is a personal project, but suggestions welcome!

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This project is for personal analysis only. Recommendations are based on your data and are **informational**, not medical advice. Always consult healthcare professionals for health-related decisions.

## 🙏 Acknowledgments

- [Strava](https://www.strava.com) for the API and platform
- [Streamlit](https://streamlit.io) for the dashboard framework
- [DuckDB](https://duckdb.org) for the local database
- [FastAPI](https://fastapi.tiangolo.com) for the web framework

## 📞 Support

For issues or questions:
1. Check existing [issues](https://github.com/yourusername/strava-performance-coach/issues)
2. Review [documentation](docs/)
3. Create new issue with detailed description

## 🗺️ Next Steps

**Getting Started:**
1. ✅ You're reading this! (Phase 1 underway)
2. 📋 Next: Follow Phase 2 instructions for Strava Developer setup
3. 🗄️ Then: Create DuckDB schema (Phase 3)
4. 🔌 Then: Implement Strava API client (Phase 4)

Each phase has detailed instructions. Follow them in order!

---

**Happy training! 🏃‍♂️🚴‍♀️**
