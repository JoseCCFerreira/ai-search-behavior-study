"""
Test configuration and settings module.
"""

import pytest

from config.settings import settings


def test_settings_loaded():
    """Test that settings are loaded correctly."""
    assert settings is not None
    assert settings.app_name == "Strava Performance Coach"
    assert settings.app_version == "0.1.0"


def test_directories_created():
    """Test that necessary directories are created."""
    assert settings.logs_dir.exists()
    assert settings.data_dir.exists()
    assert settings.raw_data_dir.exists()
    assert settings.processed_data_dir.exists()
    assert settings.mock_data_dir.exists()
    assert settings.database_dir.exists()


def test_strava_config_structure():
    """Test that Strava configuration is available."""
    assert hasattr(settings, "strava_client_id")
    assert hasattr(settings, "strava_client_secret")
    assert hasattr(settings, "strava_redirect_uri")
    assert hasattr(settings, "strava_verify_token")
    assert settings.strava_api_base_url == "https://www.strava.com"
    assert settings.strava_api_v3_url == "https://www.strava.com/api/v3"


def test_database_config():
    """Test that database configuration is available."""
    assert settings.duckdb_path == "database/strava_coach.duckdb"
    assert settings.database_dir.exists()


def test_environment_default_values():
    """Test environment defaults."""
    assert settings.app_env == "local"
    assert settings.debug is True
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
