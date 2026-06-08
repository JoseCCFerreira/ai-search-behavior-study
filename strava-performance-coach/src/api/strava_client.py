"""
Strava API Client with rate limiting, error handling, and token refresh.

This module provides a client for interacting with the Strava API v3,
including automatic rate limiting (600 requests/15 minutes),
exponential backoff retry logic, and token refresh handling.

Author: Strava Performance Coach
Date: 2026
"""

import json
import logging
import time
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import settings
from src.auth.strava_oauth import StravaOAuth, TokenData

# Configure logging
logger = logging.getLogger(__name__)


class StravaAPIError(Exception):
    """Base exception for Strava API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)

    def __str__(self):
        if self.status_code:
            return f"{self.status_code}: {self.message}"
        return self.message


class RateLimitError(StravaAPIError):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, retry_after: int = 900):
        self.retry_after = retry_after
        message = f"Rate limit exceeded. Retry after {retry_after} seconds"
        super().__init__(message, 429)


class AuthenticationError(StravaAPIError):
    """Exception raised when authentication fails."""

    pass


class ResourceNotFoundError(StravaAPIError):
    """Exception raised when a resource is not found."""

    pass


class StravaClient:
    """
    Strava API v3 client with rate limiting and error handling.

    Features:
    - Automatic rate limiting (600 requests per 15 minutes)
    - Exponential backoff retry logic
    - Token refresh handling
    - Connection pooling
    - Comprehensive logging
    - Mock responses for testing

    Rate Limit Details:
    - Limit: 600 requests per 15 minutes (40 req/min average)
    - Short term: 100 requests per minute (bursts)
    - The client tracks and respects both limits

    Example:
        >>> from src.api.strava_client import StravaClient
        >>> from src.auth.strava_oauth import TokenData
        >>>
        >>> token = TokenData(
        ...     access_token="token_here",
        ...     refresh_token="refresh_here",
        ...     expires_at=1234567890
        ... )
        >>> client = StravaClient(token)
        >>> activity = client.get_activity(12345)
        >>> print(activity.get("name"))
    """

    # Rate limiting constants (as per Strava documentation)
    RATE_LIMIT_LONG_TERM = 200  # requests per 15 minutes
    RATE_LIMIT_SHORT_TERM = 200  # requests per 15 minutes
    RATE_LIMIT_WINDOW_LONG = 900  # 15 minutes in seconds
    RATE_LIMIT_WINDOW_SHORT = 60  # 1 minute in seconds

    # Retry configuration
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 2  # exponential backoff: 1s, 2s, 4s, 8s, etc

    def __init__(
        self,
        token: TokenData,
        base_url: str = settings.strava_api_v3_url,
        mock_mode: bool = False,
        mock_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Strava API client.

        Args:
            token: TokenData object with access_token, refresh_token, expires_at
            base_url: Base URL for Strava API (default from settings)
            mock_mode: If True, use mock data instead of making real requests
            mock_data: Dictionary with mock responses (key=endpoint, value=response)

        Raises:
            ValueError: If token is None or missing required fields
        """
        if not token or not token.access_token:
            raise ValueError("Token and access_token are required")

        self.token = token
        self.base_url = base_url.rstrip("/")
        self.mock_mode = mock_mode
        self.mock_data = mock_data or {}
        self.oauth = StravaOAuth()

        # Rate limiting tracking
        self.request_times_long_term: List[float] = []  # tracking for 15-min window
        self.request_times_short_term: List[float] = []  # tracking for 1-min window
        self.last_request_time = 0.0
        self.rate_limit_remaining = self.RATE_LIMIT_LONG_TERM
        self.rate_limit_reset = None

        # Session with connection pooling
        self.session = self._create_session()

        logger.info(f"StravaClient initialized. Mock mode: {mock_mode}")

    def _create_session(self) -> requests.Session:
        """Create a requests session with connection pooling and retry strategy."""
        session = requests.Session()

        # Configure retry strategy for common transient errors
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT"],
            backoff_factor=self.BACKOFF_FACTOR,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _check_token_refresh(self) -> None:
        """
        Check if token needs refresh and refresh if necessary.

        The token is refreshed if it expires within 5 minutes.
        """
        if not self.token:
            raise AuthenticationError("No token available")

        # Check if token expires within 5 minutes
        expires_in = self.token.expires_at - time.time()
        if expires_in < 300:  # 5 minutes
            logger.info("Token expiring soon, refreshing...")
            try:
                self.token = self.oauth.refresh_tokens(self.token.refresh_token)
                logger.info("Token refreshed successfully")
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                raise AuthenticationError(f"Failed to refresh token: {e}")

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests."""
        self._check_token_refresh()
        return {
            "Authorization": f"Bearer {self.token.access_token}",
            "Accept": "application/json",
            "User-Agent": f"StravaPerformanceCoach/{settings.app_version}",
        }

    def _check_rate_limit(self) -> None:
        """
        Check and enforce rate limiting.

        Implements both short-term (100 req/min) and long-term (600 req/15min) limits.
        Waits if necessary to avoid exceeding limits.

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        current_time = time.time()

        # Clean up old request times outside the windows
        self.request_times_long_term = [t for t in self.request_times_long_term if current_time - t < self.RATE_LIMIT_WINDOW_LONG]
        self.request_times_short_term = [t for t in self.request_times_short_term if current_time - t < self.RATE_LIMIT_WINDOW_SHORT]

        # Check long-term limit
        if len(self.request_times_long_term) >= self.RATE_LIMIT_LONG_TERM:
            sleep_time = self.request_times_long_term[0] + self.RATE_LIMIT_WINDOW_LONG - current_time
            logger.warning(f"Long-term rate limit reached. Sleeping for {sleep_time:.1f}s")
            time.sleep(sleep_time + 0.1)
            self.request_times_long_term = []

        # Check short-term limit
        if len(self.request_times_short_term) >= self.RATE_LIMIT_SHORT_TERM:
            sleep_time = self.request_times_short_term[0] + self.RATE_LIMIT_WINDOW_SHORT - current_time
            logger.warning(f"Short-term rate limit reached. Sleeping for {sleep_time:.1f}s")
            time.sleep(sleep_time + 0.1)
            self.request_times_short_term = []

        # Add current request time
        self.request_times_long_term.append(current_time)
        self.request_times_short_term.append(current_time)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the Strava API with error handling.

        Args:
            method: HTTP method (GET, POST, PUT, etc)
            endpoint: API endpoint (e.g., "/athlete/activities")
            params: Query parameters
            json_data: JSON body data
            retry_count: Internal counter for retries

        Returns:
            Response JSON as dictionary

        Raises:
            StravaAPIError: For API errors
            RateLimitError: If rate limit is exceeded
            AuthenticationError: If authentication fails
            ResourceNotFoundError: If resource not found
        """
        # Check rate limit before making request
        self._check_rate_limit()

        # Build full URL
        url = urljoin(self.base_url, endpoint.lstrip("/"))

        # Mock mode
        if self.mock_mode:
            logger.info(f"[MOCK] {method} {endpoint}")
            mock_key = f"{method}:{endpoint}"
            if mock_key in self.mock_data:
                return self.mock_data[mock_key]
            return {}

        # Real request
        headers = self._get_headers()

        try:
            logger.debug(f"Making request: {method} {url}")
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=30,
            )

            # Update rate limit info from response headers
            response_headers = (
                response.headers if isinstance(response.headers, Mapping) else {}
            )
            if "X-RateLimit-Limit" in response_headers:
                limits = response_headers.get("X-RateLimit-Limit", "0,0").split(",")
                usage = response_headers.get("X-RateLimit-Usage", "0,0").split(",")
                try:
                    short_limit = int(limits[0])
                    short_usage = int(usage[0])
                    self.rate_limit_remaining = max(short_limit - short_usage, 0)
                except (TypeError, ValueError, IndexError):
                    logger.debug("Could not parse Strava rate limit headers")

            # Handle different status codes
            if response.status_code == 200 or response.status_code == 201:
                logger.debug(f"Request successful: {response.status_code}")
                return response.json()

            elif response.status_code == 204:
                # No content
                logger.debug("Request successful (no content)")
                return {}

            elif response.status_code == 400:
                data = response.json() if response.text else {}
                raise StravaAPIError("Bad request", 400, data)

            elif response.status_code == 401:
                raise AuthenticationError("Unauthorized - token may be invalid or expired", 401)

            elif response.status_code == 403:
                raise AuthenticationError("Forbidden - insufficient permissions", 403)

            elif response.status_code == 404:
                raise ResourceNotFoundError("Resource not found", 404)

            elif response.status_code == 429:
                # Rate limit exceeded - wait and retry
                retry_after = int(response_headers.get("Retry-After", 60))
                if retry_after > 60:
                    raise RateLimitError(retry_after)
                if retry_count < self.MAX_RETRIES:
                    logger.warning(f"Rate limited. Retrying after {retry_after}s (attempt {retry_count + 1}/{self.MAX_RETRIES})")
                    time.sleep(retry_after)
                    return self._make_request(method, endpoint, params, json_data, retry_count + 1)
                else:
                    raise RateLimitError(retry_after)

            elif response.status_code >= 500:
                # Server error - retry with backoff
                if retry_count < self.MAX_RETRIES:
                    wait_time = self.BACKOFF_FACTOR ** retry_count
                    logger.warning(f"Server error ({response.status_code}). Retrying after {wait_time}s (attempt {retry_count + 1}/{self.MAX_RETRIES})")
                    time.sleep(wait_time)
                    return self._make_request(method, endpoint, params, json_data, retry_count + 1)
                else:
                    raise StravaAPIError(f"Server error after {self.MAX_RETRIES} retries", response.status_code)

            else:
                raise StravaAPIError(f"Unexpected status code", response.status_code)

        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout: {e}")
            raise StravaAPIError("Request timeout", 504)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            raise StravaAPIError("Connection error", 500)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            raise StravaAPIError(f"Request error: {e}", 500)

    def get_athlete(self) -> Dict[str, Any]:
        """
        Get authenticated athlete's profile.

        Returns:
            Athlete object with fields: id, firstname, lastname, city, state, country,
            sex, summit, created_at, updated_at, profile_medium, profile, friend, follower

        Example:
            >>> athlete = client.get_athlete()
            >>> print(f"Athlete: {athlete['firstname']} {athlete['lastname']}")
        """
        logger.info("Fetching authenticated athlete profile")
        return self._make_request("GET", "/athlete")

    def get_activity(self, activity_id: int, include_all_efforts: bool = True) -> Dict[str, Any]:
        """
        Get a specific activity by ID.

        Args:
            activity_id: ID of the activity
            include_all_efforts: Whether to include all segment efforts

        Returns:
            Activity object with fields: id, name, distance, moving_time, elapsed_time,
            start_date, type, location_city, location_state, latlng, elevation_gain,
            average_speed, max_speed, average_heartrate, max_heartrate, and more

        Raises:
            ResourceNotFoundError: If activity not found
            StravaAPIError: For other API errors

        Example:
            >>> activity = client.get_activity(12345)
            >>> print(f"Activity: {activity['name']} ({activity['distance']}m)")
        """
        logger.info(f"Fetching activity {activity_id}")
        params = {"include_all_efforts": include_all_efforts}
        return self._make_request("GET", f"/activities/{activity_id}", params=params)

    def get_athlete_activities(
        self,
        before: Optional[int] = None,
        after: Optional[int] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get authenticated athlete's activities.

        Args:
            before: Unix timestamp to get activities before (exclusive)
            after: Unix timestamp to get activities after (exclusive)
            page: Page number (1-indexed)
            per_page: Activities per page (1-200, default 30)

        Returns:
            List of activity objects (summary format)

        Note:
            Results are ordered by start_date descending (most recent first).
            For efficiency, use 'after' timestamp rather than paginating through old data.

        Example:
            >>> # Get activities from last 30 days
            >>> timestamp_30_days_ago = int(time.time()) - (30 * 24 * 3600)
            >>> activities = client.get_athlete_activities(after=timestamp_30_days_ago)
            >>> print(f"Found {len(activities)} activities")
            >>>
            >>> # Paginate through all activities
            >>> all_activities = []
            >>> page = 1
            >>> while True:
            >>>     activities = client.get_athlete_activities(page=page)
            >>>     if not activities:
            >>>         break
            >>>     all_activities.extend(activities)
            >>>     page += 1
        """
        logger.info(f"Fetching athlete activities (page={page}, per_page={per_page})")

        # Validate per_page
        if per_page < 1 or per_page > 200:
            raise ValueError("per_page must be between 1 and 200")

        params = {
            "page": page,
            "per_page": per_page,
        }

        if before:
            params["before"] = before
        if after:
            params["after"] = after

        return self._make_request("GET", "/athlete/activities", params=params)

    def iter_athlete_activities(
        self,
        before: Optional[int] = None,
        after: Optional[int] = None,
        per_page: int = 200,
        max_pages: Optional[int] = None,
    ):
        """Yield authenticated athlete activities across paginated responses."""
        page = 1
        while True:
            activities = self.get_athlete_activities(
                before=before,
                after=after,
                page=page,
                per_page=per_page,
            )
            if not activities:
                break

            for activity in activities:
                yield activity

            if len(activities) < per_page:
                break
            if max_pages is not None and page >= max_pages:
                break
            page += 1

    def get_all_athlete_activities(
        self,
        before: Optional[int] = None,
        after: Optional[int] = None,
        per_page: int = 200,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return all paginated authenticated athlete activities."""
        return list(
            self.iter_athlete_activities(
                before=before,
                after=after,
                per_page=per_page,
                max_pages=max_pages,
            )
        )

    def get_athlete_stats(self) -> Dict[str, Any]:
        """
        Get authenticated athlete's stats (requires athlete:read_all scope).

        Returns:
            Stats object with fields: biggest_ride_distance, biggest_climb_elevation_gain,
            recent_ride_totals, recent_run_totals, all_ride_totals, all_run_totals

        Raises:
            AuthenticationError: If insufficient permissions

        Example:
            >>> stats = client.get_athlete_stats()
            >>> print(f"All time distance: {stats['all_ride_totals']['distance']}m")
        """
        logger.info("Fetching athlete stats")
        athlete_id = self.get_athlete()["id"]
        return self._make_request("GET", f"/athletes/{athlete_id}/stats")

    def get_activity_comments(self, activity_id: int, page: int = 1, per_page: int = 30) -> List[Dict[str, Any]]:
        """
        Get comments on a specific activity.

        Args:
            activity_id: ID of the activity
            page: Page number
            per_page: Comments per page (1-200)

        Returns:
            List of comment objects

        Example:
            >>> comments = client.get_activity_comments(12345)
            >>> for comment in comments:
            >>>     print(f"{comment['athlete']['firstname']}: {comment['text']}")
        """
        logger.info(f"Fetching comments for activity {activity_id}")
        params = {"page": page, "per_page": per_page}
        return self._make_request("GET", f"/activities/{activity_id}/comments", params=params)

    def get_activity_kudos(self, activity_id: int, page: int = 1, per_page: int = 30) -> List[Dict[str, Any]]:
        """
        Get athletes who kudoed a specific activity.

        Args:
            activity_id: ID of the activity
            page: Page number
            per_page: Athletes per page (1-200)

        Returns:
            List of athlete objects who gave kudos

        Example:
            >>> kudos = client.get_activity_kudos(12345)
            >>> print(f"Activity got {len(kudos)} kudos")
        """
        logger.info(f"Fetching kudos for activity {activity_id}")
        params = {"page": page, "per_page": per_page}
        return self._make_request("GET", f"/activities/{activity_id}/kudos", params=params)

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status.

        Returns:
            Dictionary with rate_limit_remaining, rate_limit_reset, rate_limit_short_term_remaining

        Example:
            >>> status = client.get_rate_limit_status()
            >>> print(f"Requests remaining: {status['rate_limit_remaining']}/600")
        """
        return {
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_reset": self.rate_limit_reset.isoformat() if self.rate_limit_reset else None,
            "requests_in_queue": len(self.request_times_long_term),
        }

    def close(self) -> None:
        """Close the session and clean up resources."""
        if self.session:
            self.session.close()
            logger.info("StravaClient session closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
