"""
Strava API client and utilities package.

This package provides interfaces for interacting with the Strava API,
including rate limiting, token refresh, and error handling.
"""

from .strava_client import StravaClient, StravaAPIError, RateLimitError

__all__ = [
    "StravaClient",
    "StravaAPIError",
    "RateLimitError",
]
