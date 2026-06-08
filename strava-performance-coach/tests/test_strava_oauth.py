"""
Tests for Strava OAuth authentication module.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

import pytest
from unittest.mock import patch, MagicMock

from src.auth.strava_oauth import StravaOAuth, TokenData, get_oauth_handler


@pytest.fixture
def oauth_handler(tmp_path, monkeypatch):
    """Create OAuth handler with temporary tokens directory."""
    # Mock tokens directory
    monkeypatch.setattr("src.auth.strava_oauth.StravaOAuth.tokens_dir", tmp_path / ".tokens")
    monkeypatch.setattr(
        "src.auth.strava_oauth.StravaOAuth.tokens_file",
        tmp_path / ".tokens" / "strava_tokens.json",
    )

    # Create instance
    handler = StravaOAuth()
    handler.tokens_dir = tmp_path / ".tokens"
    handler.tokens_file = handler.tokens_dir / "strava_tokens.json"
    handler.tokens_dir.mkdir(exist_ok=True, mode=0o700)

    return handler


@pytest.fixture
def sample_token_data():
    """Create sample token data."""
    expires_at = (datetime.utcnow() + timedelta(hours=5)).timestamp()

    return TokenData(
        access_token="sample_access_token_123",
        refresh_token="sample_refresh_token_456",
        expires_at=expires_at,
        athlete_id=12345,
        athlete_name="John Doe",
        athlete_profile_picture="https://example.com/profile.jpg",
        scope="read,activity:read_all,profile:read_all",
    )


@pytest.fixture
def strava_oauth_response():
    """Create sample Strava OAuth response."""
    return {
        "access_token": "new_access_token_789",
        "refresh_token": "new_refresh_token_000",
        "expires_at": (datetime.utcnow() + timedelta(hours=6)).timestamp(),
        "athlete": {
            "id": 12345,
            "firstname": "John",
            "lastname": "Doe",
            "profile_medium": "https://example.com/profile_medium.jpg",
            "profile": "https://example.com/profile.jpg",
        },
    }


def test_oauth_initialization(oauth_handler):
    """Test OAuth handler initialization."""
    assert oauth_handler.client_id == oauth_handler.client_id
    assert oauth_handler.client_secret == oauth_handler.client_secret
    assert oauth_handler.redirect_uri == oauth_handler.redirect_uri
    assert oauth_handler.tokens_dir.exists()


def test_generate_authorization_url(oauth_handler):
    """Test authorization URL generation."""
    url = oauth_handler.generate_authorization_url()

    assert "https://www.strava.com/oauth/authorize" in url
    assert "client_id=" in url
    assert "response_type=code" in url
    assert "redirect_uri=" in url
    assert "scope=" in url
    assert "state=" in url

    # State should be saved
    state_file = oauth_handler.tokens_dir / ".oauth_state"
    assert state_file.exists()


def test_save_and_load_tokens(oauth_handler, sample_token_data):
    """Test saving and loading tokens."""
    # Save tokens
    oauth_handler.save_tokens(sample_token_data)
    assert oauth_handler.tokens_file.exists()

    # Load tokens
    loaded = oauth_handler.load_tokens()

    assert loaded is not None
    assert loaded.access_token == sample_token_data.access_token
    assert loaded.refresh_token == sample_token_data.refresh_token
    assert loaded.athlete_id == sample_token_data.athlete_id


def test_clear_tokens(oauth_handler, sample_token_data):
    """Test clearing tokens."""
    # Save tokens
    oauth_handler.save_tokens(sample_token_data)
    assert oauth_handler.tokens_file.exists()

    # Clear tokens
    oauth_handler.clear_tokens()
    assert not oauth_handler.tokens_file.exists()


def test_is_authenticated_with_valid_tokens(oauth_handler, sample_token_data):
    """Test authentication check with valid tokens."""
    oauth_handler.save_tokens(sample_token_data)

    assert oauth_handler.is_authenticated() is True


def test_is_authenticated_with_expired_tokens(oauth_handler):
    """Test authentication check with expired tokens."""
    # Create expired token
    expired_token = TokenData(
        access_token="expired_token",
        refresh_token="expired_refresh",
        expires_at=(datetime.utcnow() - timedelta(hours=1)).timestamp(),
        athlete_id=12345,
    )

    oauth_handler.save_tokens(expired_token)

    assert oauth_handler.is_authenticated() is False


def test_is_authenticated_without_tokens(oauth_handler):
    """Test authentication check without tokens."""
    assert oauth_handler.is_authenticated() is False


def test_load_tokens_file_not_found(oauth_handler):
    """Test loading tokens when file doesn't exist."""
    result = oauth_handler.load_tokens()
    assert result is None


@patch("src.auth.strava_oauth.requests.post")
def test_exchange_code_for_tokens(mock_post, oauth_handler, strava_oauth_response):
    """Test exchanging authorization code for tokens."""
    mock_post.return_value.json.return_value = strava_oauth_response
    mock_post.return_value.raise_for_status = MagicMock()

    code = "test_auth_code"
    result = oauth_handler.exchange_code_for_tokens(code)

    assert result.access_token == strava_oauth_response["access_token"]
    assert result.refresh_token == strava_oauth_response["refresh_token"]
    assert result.athlete_id == strava_oauth_response["athlete"]["id"]

    # Verify tokens were saved
    assert oauth_handler.load_tokens() is not None


@patch("src.auth.strava_oauth.requests.post")
def test_exchange_code_for_tokens_failure(mock_post, oauth_handler):
    """Test token exchange failure."""
    mock_post.side_effect = Exception("Network error")

    with pytest.raises(ValueError):
        oauth_handler.exchange_code_for_tokens("invalid_code")


def test_validate_state_success(oauth_handler):
    """Test successful state validation."""
    state = "test_state_123"
    oauth_handler._save_state(state)

    is_valid = oauth_handler._validate_state(state)
    assert is_valid is True

    # State file should be deleted after validation
    state_file = oauth_handler.tokens_dir / ".oauth_state"
    assert not state_file.exists()


def test_validate_state_failure(oauth_handler):
    """Test failed state validation."""
    state = "test_state_123"
    oauth_handler._save_state(state)

    is_valid = oauth_handler._validate_state("wrong_state")
    assert is_valid is False


def test_get_valid_token(oauth_handler, sample_token_data):
    """Test getting valid token."""
    oauth_handler.save_tokens(sample_token_data)

    token = oauth_handler.get_valid_token()
    assert token == sample_token_data.access_token


@patch("src.auth.strava_oauth.requests.post")
def test_refresh_access_token_if_needed_expired(mock_post, oauth_handler, strava_oauth_response):
    """Test refreshing expired token."""
    # Create expired token
    expired_token = TokenData(
        access_token="old_token",
        refresh_token="old_refresh",
        expires_at=(datetime.utcnow() - timedelta(hours=1)).timestamp(),
        athlete_id=12345,
    )

    oauth_handler.save_tokens(expired_token)
    mock_post.return_value.json.return_value = strava_oauth_response
    mock_post.return_value.raise_for_status = MagicMock()

    result = oauth_handler.refresh_access_token_if_needed()

    assert result is not None
    assert result.access_token == strava_oauth_response["access_token"]
    assert result.refresh_token == strava_oauth_response["refresh_token"]


def test_refresh_access_token_if_needed_still_valid(oauth_handler, sample_token_data):
    """Test that refresh is skipped for valid tokens."""
    oauth_handler.save_tokens(sample_token_data)

    # Should return None (no refresh needed)
    result = oauth_handler.refresh_access_token_if_needed()
    assert result is None


def test_get_oauth_handler():
    """Test getting OAuth handler instance."""
    handler = get_oauth_handler()
    assert isinstance(handler, StravaOAuth)


def test_token_data_model():
    """Test TokenData pydantic model."""
    expires_at = (datetime.utcnow() + timedelta(hours=1)).timestamp()

    token = TokenData(
        access_token="test_token",
        refresh_token="test_refresh",
        expires_at=expires_at,
        athlete_id=123,
    )

    assert token.access_token == "test_token"
    assert token.athlete_id == 123
    assert token.scope == "read,activity:read_all,profile:read_all"

    # Test JSON serialization
    json_str = token.json()
    assert "test_token" in json_str
    assert "123" in json_str


def test_tokens_file_permissions(oauth_handler, sample_token_data):
    """Test that tokens file has restricted permissions."""
    oauth_handler.save_tokens(sample_token_data)

    # Check file permissions (0o600 = rw-------)
    perms = oauth_handler.tokens_file.stat().st_mode & 0o777
    assert perms == 0o600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
