"""
Pytest configuration and fixtures.
"""

import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Fixture providing the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def data_dir(project_root):
    """Fixture providing the data directory."""
    return project_root / "data"


@pytest.fixture
def database_dir(project_root):
    """Fixture providing the database directory."""
    return project_root / "database"


@pytest.fixture
def mock_data_dir(project_root):
    """Fixture providing the mock data directory."""
    return project_root / "data" / "mock"
