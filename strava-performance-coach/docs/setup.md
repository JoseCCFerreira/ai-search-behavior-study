# Setup Guide

Complete setup instructions for Strava Performance Coach.

## System Requirements

- **Python**: 3.9 or higher
- **OS**: macOS, Linux, or Windows
- **Disk Space**: ~500MB
- **RAM**: 2GB minimum (4GB recommended)
- **Git**: Version control

## Step-by-Step Setup

### 1. Clone the Repository

```bash
# Clone
git clone https://github.com/yourusername/strava-performance-coach.git

# Navigate to project
cd strava-performance-coach

# Check structure
ls -la
```

### 2. Create Virtual Environment

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (Command Prompt):**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Windows (PowerShell):**
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Upgrade pip

```bash
pip install --upgrade pip
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

To verify installation:
```bash
pip list | grep -E "streamlit|fastapi|duckdb|pandas"
```

### 5. Environment Configuration

```bash
# Create .env file from template
cp .env.example .env

# Edit .env with your settings (or leave defaults for testing)
```

For now, you can leave the defaults. They're suitable for local development.

### 6. Initialize Database

```bash
python src/database/create_database.py
```

Check that database was created:
```bash
ls -lh database/strava_coach.duckdb
```

### 7. Run Tests

```bash
pytest tests/test_settings.py -v
```

Expected output:
```
tests/test_settings.py::test_settings_loaded PASSED
tests/test_settings.py::test_directories_created PASSED
tests/test_settings.py::test_strava_config_structure PASSED
tests/test_settings.py::test_database_config PASSED
tests/test_settings.py::test_environment_default_values PASSED
```

## Verify Installation

### Check Python Version
```bash
python --version
```

Should show 3.9 or higher.

### Check Virtual Environment
```bash
which python  # macOS/Linux
# or
where python  # Windows
```

Should point to `.venv/bin/python`.

### Check Imports
```bash
python -c "import streamlit; import fastapi; import duckdb; print('✓ All imports OK')"
```

### Check Project Structure
```bash
# Verify key directories exist
test -d data && echo "✓ data/"
test -d database && echo "✓ database/"
test -d src && echo "✓ src/"
test -d app && echo "✓ app/"
test -d tests && echo "✓ tests/"
```

## Running the Application

### Streamlit Dashboard
```bash
streamlit run app/streamlit_app.py
```

Then open `http://localhost:8501` in your browser.

### FastAPI Server (Future use)
```bash
uvicorn src.connector.strava_webhook:app --reload --port 8000
```

Then visit `http://localhost:8000/docs` for API documentation.

### Run All Tests
```bash
pytest -v

# With coverage
pytest --cov=src --cov-report=html
```

## Troubleshooting

### Issue: "command not found: python3"

**Solution**:
```bash
# Check if Python is installed
which python
python --version

# If not installed, install from python.org
```

### Issue: "No such file or directory: '.venv'"

**Solution**:
```bash
# Create virtual environment
python -m venv .venv

# Activate it
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows
```

### Issue: "ModuleNotFoundError: No module named 'streamlit'"

**Solution**:
```bash
# Ensure venv is activated
source .venv/bin/activate

# Reinstall requirements
pip install -r requirements.txt
```

### Issue: "DuckDB database is locked"

**Solution**:
```bash
# Kill any running Python processes
pkill -f python

# Delete database
rm database/strava_coach.duckdb

# Recreate
python src/database/create_database.py
```

### Issue: "Permission denied" when running scripts

**Solution**:
```bash
# Make script executable
chmod +x src/database/create_database.py

# Or run with Python
python src/database/create_database.py
```

## Next Steps

1. ✅ **Phase 1 Complete**: Setup done!
2. 📋 **Phase 2**: Follow Strava Developer configuration
3. 🗄️ **Phase 3**: Initialize database schema
4. Continue with phases 4-14

See [Roadmap](roadmap.md) for detailed phase breakdown.

## Getting Help

- Check [README.md](../README.md) for overview
- Check [Architecture](architecture.md) for system design
- Run `pytest -v` to verify everything works
- Check [Roadmap](roadmap.md) for next steps

---

**Setup complete! Ready to move to Phase 2.** 🚀
