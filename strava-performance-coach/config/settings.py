"""
Application settings and configuration.

Loads environment variables from .env file using python-dotenv.
All sensitive data should be stored in .env, never hardcoded.
"""

import os
from pathlib import Path
from typing import Literal

try:
    from pydantic.v1 import BaseSettings, Field, validator
except ImportError:  # pragma: no cover - pydantic v1 fallback
    from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Application settings."""

    # Project
    app_name: str = "Strava Performance Coach"
    app_version: str = "0.1.0"
    app_env: Literal["local", "development", "production"] = Field(
        default="local", env="APP_ENV"
    )
    debug: bool = Field(default=True, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # API Server
    api_host: str = Field(default="127.0.0.1", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    api_reload: bool = Field(default=True, env="API_RELOAD")

    # Strava OAuth
    strava_client_id: str = Field(default="", env="STRAVA_CLIENT_ID")
    strava_client_secret: str = Field(default="", env="STRAVA_CLIENT_SECRET")
    strava_redirect_uri: str = Field(
        default="http://localhost:8000/auth/callback",
        env="STRAVA_REDIRECT_URI",
    )
    strava_verify_token: str = Field(default="change_me", env="STRAVA_VERIFY_TOKEN")
    strava_api_base_url: str = "https://www.strava.com"
    strava_api_v3_url: str = "https://www.strava.com/api/v3"

    # Database
    duckdb_path: str = Field(default="database/strava_coach.duckdb", env="DUCKDB_PATH")

    # Paths
    project_root: Path = Path(__file__).parent.parent
    data_dir: Path = Path(__file__).parent.parent / "data"
    raw_data_dir: Path = data_dir / "raw"
    processed_data_dir: Path = data_dir / "processed"
    mock_data_dir: Path = data_dir / "mock"
    database_dir: Path = Path(__file__).parent.parent / "database"
    docs_dir: Path = Path(__file__).parent.parent / "docs"
    logs_dir: Path = Path(__file__).parent.parent / "logs"

    @validator("debug", "api_reload", pre=True, allow_reuse=True)
    def parse_bool_env(cls, value):
        """Handle common local .env boolean spellings and empty values."""
        if value in (None, ""):
            return True
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
            return True
        return value

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **data):
        """Initialize settings and create required directories."""
        super().__init__(**data)
        # Create necessary directories
        self.logs_dir.mkdir(exist_ok=True, parents=True)
        self.raw_data_dir.mkdir(exist_ok=True, parents=True)
        self.processed_data_dir.mkdir(exist_ok=True, parents=True)
        self.mock_data_dir.mkdir(exist_ok=True, parents=True)
        self.database_dir.mkdir(exist_ok=True, parents=True)


# Create global settings instance
settings = Settings()
