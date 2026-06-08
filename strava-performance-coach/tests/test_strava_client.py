"""
Comprehensive tests for Strava API Client.

Test Coverage:
- Client initialization and configuration
- Mock mode functionality
- API endpoints (athlete, activities, stats, comments, kudos)
- Rate limiting (short-term and long-term)
- Error handling (401, 403, 404, 429, 500, etc)
- Token refresh
- Retry logic
- Connection pooling
- Context manager pattern

Author: Strava Performance Coach
Date: 2026
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from src.api.strava_client import (
    StravaClient,
    StravaAPIError,
    RateLimitError,
    AuthenticationError,
    ResourceNotFoundError,
)
from src.auth.strava_oauth import TokenData


@pytest.fixture
def valid_token() -> TokenData:
    """Create a valid token for testing."""
    return TokenData(
        access_token="test_access_token_123456789",
        refresh_token="test_refresh_token_987654321",
        expires_at=time.time() + 3600,  # 1 hour from now
        athlete_id=12345,
        scope="read,activity:read_all,profile:read_all",
    )


@pytest.fixture
def expired_token() -> TokenData:
    """Create an expired token for testing."""
    return TokenData(
        access_token="expired_token",
        refresh_token="refresh_token",
        expires_at=time.time() - 3600,  # 1 hour in the past
        athlete_id=12345,
        scope="read",
    )


@pytest.fixture
def mock_athlete_response() -> Dict[str, Any]:
    """Mock Strava athlete response."""
    return {
        "id": 12345,
        "firstname": "Test",
        "lastname": "Athlete",
        "profile_medium": "https://example.com/profile.jpg",
        "profile": "https://example.com/profile.jpg",
        "city": "Lisbon",
        "state": "Lisbon",
        "country": "Portugal",
        "sex": "M",
        "summit": True,
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2025-12-31T23:59:59Z",
    }


@pytest.fixture
def mock_activity_response() -> Dict[str, Any]:
    """Mock Strava activity response."""
    return {
        "id": 987654,
        "name": "Morning Run",
        "distance": 10000.5,
        "moving_time": 3600,
        "elapsed_time": 3700,
        "start_date": "2026-06-02T08:00:00Z",
        "type": "Run",
        "location_city": "Lisbon",
        "location_state": "Lisbon",
        "latlng": [[38.7223, -9.1393]],
        "elevation_gain": 125.5,
        "average_speed": 2.78,
        "max_speed": 5.2,
        "average_heartrate": 155.2,
        "max_heartrate": 182,
        "total_elevation_gain": 125.5,
        "kudos_count": 5,
        "comment_count": 2,
    }


@pytest.fixture
def mock_activities_list(mock_activity_response) -> list:
    """Mock list of activities response."""
    activity1 = mock_activity_response.copy()
    activity1["id"] = 1
    activity1["name"] = "Run 1"

    activity2 = mock_activity_response.copy()
    activity2["id"] = 2
    activity2["name"] = "Run 2"

    return [activity1, activity2]


@pytest.fixture
def strava_client(valid_token) -> StravaClient:
    """Create a StravaClient instance with valid token."""
    return StravaClient(token=valid_token)


@pytest.fixture
def mock_strava_client(valid_token, mock_athlete_response, mock_activity_response) -> StravaClient:
    """Create a StravaClient in mock mode with predefined responses."""
    mock_data = {
        "GET:/athlete": mock_athlete_response,
        "GET:/activities/987654": mock_activity_response,
        "GET:/athlete/activities": [mock_activity_response],
    }
    return StravaClient(token=valid_token, mock_mode=True, mock_data=mock_data)


class TestStravaClientInitialization:
    """Test client initialization and configuration."""

    def test_initialize_with_valid_token(self, valid_token):
        """Test successful client initialization."""
        client = StravaClient(token=valid_token)
        assert client.token == valid_token
        assert client.base_url is not None
        assert client.mock_mode is False
        assert client.session is not None

    def test_initialize_with_none_token(self):
        """Test initialization fails with None token."""
        with pytest.raises(ValueError, match="Token and access_token are required"):
            StravaClient(token=None)

    def test_initialize_with_token_missing_access_token(self):
        """Test initialization fails when token lacks access_token."""
        token = TokenData(
            access_token=None,
            refresh_token="test",
            expires_at=time.time() + 3600,
            athlete_id=12345,
        )
        with pytest.raises(ValueError):
            StravaClient(token=token)

    def test_initialize_with_mock_mode(self, valid_token, mock_athlete_response):
        """Test client initialization with mock mode."""
        mock_data = {"GET:/athlete": mock_athlete_response}
        client = StravaClient(token=valid_token, mock_mode=True, mock_data=mock_data)
        assert client.mock_mode is True
        assert client.mock_data == mock_data

    def test_initialize_creates_session(self, valid_token):
        """Test that session is created with proper configuration."""
        client = StravaClient(token=valid_token)
        assert isinstance(client.session, requests.Session)
        assert client.session.adapters is not None


class TestMockMode:
    """Test mock mode functionality."""

    def test_mock_get_athlete(self, mock_strava_client, mock_athlete_response):
        """Test getting athlete in mock mode."""
        athlete = mock_strava_client.get_athlete()
        assert athlete == mock_athlete_response
        assert athlete["id"] == 12345

    def test_mock_get_activity(self, mock_strava_client, mock_activity_response):
        """Test getting activity in mock mode."""
        activity = mock_strava_client.get_activity(987654)
        assert activity == mock_activity_response
        assert activity["name"] == "Morning Run"

    def test_mock_get_athlete_activities(self, mock_strava_client):
        """Test getting athlete activities in mock mode."""
        activities = mock_strava_client.get_athlete_activities()
        assert isinstance(activities, list)
        assert len(activities) > 0

    def test_mock_nonexistent_endpoint(self, mock_strava_client):
        """Test accessing nonexistent endpoint in mock mode returns empty dict."""
        result = mock_strava_client._make_request("GET", "/nonexistent")
        assert result == {}


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limit_tracking_long_term(self, strava_client):
        """Test that rate limiting tracks requests in 15-min window."""
        assert len(strava_client.request_times_long_term) == 0
        strava_client._check_rate_limit()
        assert len(strava_client.request_times_long_term) == 1

    def test_rate_limit_tracking_short_term(self, strava_client):
        """Test that rate limiting tracks requests in 1-min window."""
        assert len(strava_client.request_times_short_term) == 0
        strava_client._check_rate_limit()
        assert len(strava_client.request_times_short_term) == 1

    def test_rate_limit_cleanup_old_entries(self, strava_client):
        """Test that old entries are cleaned up."""
        # Add old entry manually
        old_time = time.time() - 1000  # 1000 seconds ago (outside 15-min window)
        strava_client.request_times_long_term = [old_time]

        strava_client._check_rate_limit()
        # Old entry should be removed
        assert all(t > old_time for t in strava_client.request_times_long_term)

    def test_rate_limit_waits_when_exceeded_long_term(self, strava_client):
        """Test that client waits when long-term rate limit would be exceeded."""
        # Simulate having made many requests
        current_time = time.time()
        strava_client.request_times_long_term = [current_time - 5 + i * 0.1 for i in range(600)]

        # Mock time.sleep to avoid actually sleeping
        with patch("time.sleep") as mock_sleep:
            strava_client._check_rate_limit()
            # Should have called sleep
            mock_sleep.assert_called()

    def test_get_rate_limit_status(self, strava_client):
        """Test rate limit status retrieval."""
        status = strava_client.get_rate_limit_status()
        assert "rate_limit_remaining" in status
        assert "rate_limit_reset" in status
        assert "requests_in_queue" in status
        assert status["requests_in_queue"] == 0


class TestTokenManagement:
    """Test token refresh and management."""

    def test_token_not_refreshed_when_valid(self, strava_client):
        """Test that valid token is not refreshed."""
        with patch.object(strava_client.oauth, "refresh_tokens") as mock_refresh:
            strava_client._check_token_refresh()
            # Should not be called for valid token
            mock_refresh.assert_not_called()

    def test_token_refreshed_when_expiring_soon(self, valid_token):
        """Test that token is refreshed when expiring soon."""
        # Set token to expire in 2 minutes (less than 5 min threshold)
        valid_token.expires_at = time.time() + 120

        client = StravaClient(token=valid_token)

        new_token = TokenData(
            access_token="new_token",
            refresh_token="new_refresh",
            expires_at=time.time() + 3600,
            athlete_id=12345,
        )

        with patch.object(client.oauth, "refresh_tokens", return_value=new_token) as mock_refresh:
            client._check_token_refresh()
            mock_refresh.assert_called_once()
            assert client.token == new_token

    def test_token_refresh_failure(self, valid_token):
        """Test handling of token refresh failure."""
        valid_token.expires_at = time.time() + 120  # Expiring soon

        client = StravaClient(token=valid_token)

        with patch.object(client.oauth, "refresh_tokens", side_effect=Exception("Refresh failed")):
            with pytest.raises(AuthenticationError):
                client._check_token_refresh()


class TestAPIEndpoints:
    """Test API endpoint methods."""

    def test_get_athlete(self, mock_strava_client, mock_athlete_response):
        """Test get_athlete endpoint."""
        athlete = mock_strava_client.get_athlete()
        assert athlete["id"] == 12345
        assert athlete["firstname"] == "Test"
        assert athlete["lastname"] == "Athlete"

    def test_get_activity(self, mock_strava_client, mock_activity_response):
        """Test get_activity endpoint."""
        activity = mock_strava_client.get_activity(987654)
        assert activity["id"] == 987654
        assert activity["name"] == "Morning Run"
        assert activity["distance"] == 10000.5

    def test_get_activity_with_options(self, mock_strava_client):
        """Test get_activity with options."""
        with patch.object(mock_strava_client, "_make_request") as mock_request:
            mock_request.return_value = {}
            mock_strava_client.get_activity(987654, include_all_efforts=False)
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[1]["params"]["include_all_efforts"] is False

    def test_get_athlete_activities(self, mock_strava_client):
        """Test get_athlete_activities endpoint."""
        activities = mock_strava_client.get_athlete_activities()
        assert isinstance(activities, list)

    def test_get_athlete_activities_with_pagination(self, mock_strava_client):
        """Test get_athlete_activities with pagination."""
        with patch.object(mock_strava_client, "_make_request") as mock_request:
            mock_request.return_value = []
            mock_strava_client.get_athlete_activities(page=2, per_page=50)
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[1]["params"]["page"] == 2
            assert call_args[1]["params"]["per_page"] == 50

    def test_get_athlete_activities_with_before_after(self, mock_strava_client):
        """Test get_athlete_activities with time filters."""
        before_timestamp = int(time.time())
        after_timestamp = int(time.time()) - 86400

        with patch.object(mock_strava_client, "_make_request") as mock_request:
            mock_request.return_value = []
            mock_strava_client.get_athlete_activities(before=before_timestamp, after=after_timestamp)
            call_args = mock_request.call_args
            assert call_args[1]["params"]["before"] == before_timestamp
            assert call_args[1]["params"]["after"] == after_timestamp

    def test_get_athlete_activities_invalid_per_page(self, mock_strava_client):
        """Test get_athlete_activities fails with invalid per_page."""
        with pytest.raises(ValueError):
            mock_strava_client.get_athlete_activities(per_page=201)

        with pytest.raises(ValueError):
            mock_strava_client.get_athlete_activities(per_page=0)

    def test_get_activity_comments(self, mock_strava_client):
        """Test get_activity_comments endpoint."""
        with patch.object(mock_strava_client, "_make_request") as mock_request:
            mock_request.return_value = []
            mock_strava_client.get_activity_comments(987654)
            mock_request.assert_called_once()

    def test_get_activity_kudos(self, mock_strava_client):
        """Test get_activity_kudos endpoint."""
        with patch.object(mock_strava_client, "_make_request") as mock_request:
            mock_request.return_value = []
            mock_strava_client.get_activity_kudos(987654)
            mock_request.assert_called_once()


class TestErrorHandling:
    """Test error handling and status codes."""

    def test_authentication_error_401(self, strava_client):
        """Test handling of 401 Unauthorized response."""
        with patch.object(strava_client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_request.return_value = mock_response

            with pytest.raises(AuthenticationError):
                strava_client._make_request("GET", "/athlete")

    def test_authentication_error_403(self, strava_client):
        """Test handling of 403 Forbidden response."""
        with patch.object(strava_client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_request.return_value = mock_response

            with pytest.raises(AuthenticationError):
                strava_client._make_request("GET", "/athlete")

    def test_resource_not_found_error_404(self, strava_client):
        """Test handling of 404 Not Found response."""
        with patch.object(strava_client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_request.return_value = mock_response

            with pytest.raises(ResourceNotFoundError):
                strava_client._make_request("GET", "/activities/999999")

    def test_rate_limit_error_429_with_retry(self, strava_client):
        """Test handling of 429 Rate Limit with retry."""
        response_count = 0

        def mock_request_side_effect(*args, **kwargs):
            nonlocal response_count
            response_count += 1

            if response_count == 1:
                # First call: rate limited
                mock_response = Mock()
                mock_response.status_code = 429
                mock_response.headers = {"Retry-After": "1"}
                return mock_response
            else:
                # Second call: success
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"id": 123}
                mock_response.headers = {}
                return mock_response

        with patch.object(strava_client.session, "request", side_effect=mock_request_side_effect):
            with patch("time.sleep"):  # Don't actually sleep
                result = strava_client._make_request("GET", "/athlete")
                assert result == {"id": 123}
                assert response_count == 2

    def test_rate_limit_error_429_exhausted_retries(self, strava_client):
        """Test RateLimitError when retries exhausted."""
        with patch.object(strava_client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "900"}
            mock_request.return_value = mock_response

            with pytest.raises(RateLimitError):
                strava_client._make_request("GET", "/athlete")

    def test_server_error_500_with_retry(self, strava_client):
        """Test handling of 500 Server Error with retry."""
        response_count = 0

        def mock_request_side_effect(*args, **kwargs):
            nonlocal response_count
            response_count += 1

            if response_count == 1:
                mock_response = Mock()
                mock_response.status_code = 500
                return mock_response
            else:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"id": 123}
                mock_response.headers = {}
                return mock_response

        with patch.object(strava_client.session, "request", side_effect=mock_request_side_effect):
            with patch("time.sleep"):
                result = strava_client._make_request("GET", "/athlete")
                assert response_count == 2

    def test_timeout_error(self, strava_client):
        """Test handling of timeout error."""
        with patch.object(strava_client.session, "request", side_effect=requests.exceptions.Timeout("Timeout")):
            with pytest.raises(StravaAPIError, match="timeout"):
                strava_client._make_request("GET", "/athlete")

    def test_connection_error(self, strava_client):
        """Test handling of connection error."""
        with patch.object(strava_client.session, "request", side_effect=requests.exceptions.ConnectionError("Connection failed")):
            with pytest.raises(StravaAPIError, match="Connection"):
                strava_client._make_request("GET", "/athlete")

    def test_bad_request_error_400(self, strava_client):
        """Test handling of 400 Bad Request."""
        with patch.object(strava_client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"message": "Invalid parameter"}
            mock_request.return_value = mock_response

            with pytest.raises(StravaAPIError):
                strava_client._make_request("GET", "/athlete")

    def test_no_content_response_204(self, strava_client):
        """Test handling of 204 No Content response."""
        with patch.object(strava_client.session, "request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 204
            mock_response.headers = {}
            mock_request.return_value = mock_response

            result = strava_client._make_request("DELETE", "/activities/123")
            assert result == {}


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager_enter_exit(self, valid_token):
        """Test context manager pattern."""
        with StravaClient(token=valid_token) as client:
            assert client is not None
            assert isinstance(client, StravaClient)

    def test_context_manager_closes_session(self, valid_token):
        """Test that context manager closes session."""
        client = StravaClient(token=valid_token)
        session = client.session

        with patch.object(session, "close") as mock_close:
            with client:
                pass
            mock_close.assert_called_once()

    def test_close_method(self, valid_token):
        """Test explicit close method."""
        client = StravaClient(token=valid_token)
        session = client.session

        with patch.object(session, "close") as mock_close:
            client.close()
            mock_close.assert_called_once()


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_full_workflow_mock_mode(self, mock_strava_client):
        """Test complete workflow in mock mode."""
        # Get athlete
        athlete = mock_strava_client.get_athlete()
        assert athlete["id"] == 12345

        # Get activity
        activity = mock_strava_client.get_activity(987654)
        assert activity["id"] == 987654

        # Get activities list
        activities = mock_strava_client.get_athlete_activities()
        assert len(activities) > 0

    def test_rate_limit_status_after_requests(self, mock_strava_client):
        """Test rate limit status tracking."""
        initial_status = mock_strava_client.get_rate_limit_status()
        assert initial_status["requests_in_queue"] == 0

        # Make a request
        mock_strava_client.get_athlete()

        updated_status = mock_strava_client.get_rate_limit_status()
        assert updated_status["requests_in_queue"] >= 0

    def test_multiple_endpoints_in_mock_mode(self, valid_token):
        """Test accessing multiple endpoints in mock mode."""
        mock_data = {
            "GET:/athlete": {"id": 1, "firstname": "Test"},
            "GET:/athlete/activities": [{"id": 100, "name": "Activity 1"}],
            "GET:/activities/100": {"id": 100, "name": "Activity 1", "distance": 5000},
        }

        client = StravaClient(token=valid_token, mock_mode=True, mock_data=mock_data)

        athlete = client.get_athlete()
        assert athlete["id"] == 1

        activities = client.get_athlete_activities()
        assert len(activities) == 1

        activity = client.get_activity(100)
        assert activity["distance"] == 5000
