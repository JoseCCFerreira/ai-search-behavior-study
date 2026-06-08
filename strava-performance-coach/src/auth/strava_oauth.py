"""
Strava OAuth 2.0 Authentication Module

Handles the OAuth 2.0 flow for Strava authentication.
Manages token acquisition, storage, and refresh.

Security Note:
- Tokens are stored in .tokens/strava_tokens.json with 0600 permissions
- In production, use encrypted storage or secrets manager
- Never log token values
- Keep Client Secret in .env only
"""

import json
import logging
import secrets
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import requests
from pydantic import BaseModel, Field

from config.settings import settings

logger = logging.getLogger(__name__)


class TokenData(BaseModel):
    """Token storage model."""

    access_token: Optional[str]
    refresh_token: str
    expires_at: float  # Unix timestamp
    athlete_id: int
    athlete_name: Optional[str] = None
    athlete_profile_picture: Optional[str] = None
    scope: str = "read,activity:read_all,profile:read_all"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class StravaOAuth:
    """
    Strava OAuth 2.0 handler.

    Manages authentication flow and token lifecycle.
    """

    # Strava OAuth endpoints
    AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
    TOKEN_URL = "https://www.strava.com/oauth/token"

    # Scopes for API access
    SCOPES = "read,activity:read_all,profile:read_all"
    tokens_dir = Path(".tokens")
    tokens_file = tokens_dir / "strava_tokens.json"

    def __init__(self):
        """Initialize OAuth handler."""
        self.client_id = settings.strava_client_id
        self.client_secret = settings.strava_client_secret
        self.redirect_uri = settings.strava_redirect_uri
        self.tokens_dir = Path(self.__class__.tokens_dir)
        self.tokens_file = Path(self.__class__.tokens_file)

        # Create tokens directory if it doesn't exist
        self.tokens_dir.mkdir(exist_ok=True, mode=0o700)

        logger.info("StravaOAuth initialized")

    def generate_authorization_url(self) -> str:
        """
        Generate the authorization URL for user to visit.

        Returns:
            str: Full authorization URL
        """
        # Generate random state for CSRF protection
        state = secrets.token_urlsafe(32)

        # Save state temporarily (in production, store in session/cache)
        self._save_state(state)

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.SCOPES,
            "state": state,
        }

        url = f"{self.AUTHORIZE_URL}?{urlencode(params)}"
        logger.debug(f"Generated authorization URL (state: {state[:10]}...)")

        return url

    def exchange_code_for_tokens(self, code: str, state: Optional[str] = None) -> TokenData:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from Strava redirect
            state: State parameter for CSRF validation

        Returns:
            TokenData: Token information

        Raises:
            ValueError: If code exchange fails or state is invalid
        """
        # Validate state if provided
        if state:
            if not self._validate_state(state):
                raise ValueError("Invalid state parameter - possible CSRF attack")

        logger.info(f"Exchanging code for tokens (code: {code[:10]}...)")

        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            # Extract token data
            token_data = TokenData(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=data["expires_at"],
                athlete_id=data["athlete"]["id"],
                athlete_name=data["athlete"].get("firstname", ""),
                athlete_profile_picture=data["athlete"].get("profile_medium", ""),
                scope=self.SCOPES,
            )

            # Save tokens
            self.save_tokens(token_data)

            logger.info(
                f"Successfully exchanged code for tokens (athlete_id: {token_data.athlete_id})"
            )

            return token_data

        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            raise ValueError(f"Token exchange failed: {e}")

    def refresh_access_token_if_needed(self) -> Optional[TokenData]:
        """
        Refresh access token if it's expired or about to expire.

        Returns:
            TokenData: Updated token data, or None if token still valid

        Raises:
            ValueError: If refresh fails
        """
        token_data = self.load_tokens()
        if not token_data:
            logger.warning("No tokens available to refresh")
            return None

        # Check if token expires in next 5 minutes (300 seconds)
        now = datetime.utcnow().timestamp()
        time_to_expiry = token_data.expires_at - now

        if time_to_expiry > 300:
            logger.debug(f"Token still valid for {time_to_expiry/60:.1f} minutes")
            return None

        logger.info("Token expired or expiring soon, refreshing...")

        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": token_data.refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            # Update token data
            token_data.access_token = data["access_token"]
            token_data.refresh_token = data["refresh_token"]
            token_data.expires_at = data["expires_at"]
            token_data.updated_at = datetime.utcnow()

            # Save updated tokens
            self.save_tokens(token_data)

            logger.info("Successfully refreshed access token")

            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh token: {e}")
            raise ValueError(f"Token refresh failed: {e}")

    def refresh_tokens(self, refresh_token: str) -> TokenData:
        """
        Refresh tokens using an explicit refresh token.

        This is the API used by StravaClient when it already has a TokenData
        object in memory and needs the refreshed object returned immediately.
        """
        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()
            current_token = self.load_tokens()
            athlete = data.get("athlete") or {}

            token_data = TokenData(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=data["expires_at"],
                athlete_id=athlete.get("id")
                or (current_token.athlete_id if current_token else 0),
                athlete_name=current_token.athlete_name if current_token else None,
                athlete_profile_picture=(
                    current_token.athlete_profile_picture if current_token else None
                ),
                scope=current_token.scope if current_token else self.SCOPES,
            )

            self.save_tokens(token_data)
            logger.info("Successfully refreshed tokens")
            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh tokens: {e}")
            raise ValueError(f"Token refresh failed: {e}")

    def get_valid_token(self) -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            str: Valid access token, or None if not available

        Raises:
            ValueError: If refresh fails
        """
        # Refresh if needed
        self.refresh_access_token_if_needed()

        # Load token
        token_data = self.load_tokens()
        if not token_data:
            return None

        return token_data.access_token

    def save_tokens(self, token_data: TokenData) -> None:
        """
        Save tokens to file with restricted permissions.

        Args:
            token_data: Token information to save
        """
        try:
            if hasattr(token_data, "model_dump"):
                data = token_data.model_dump(mode="json")
            else:
                data = token_data.dict()
            json_str = json.dumps(data, indent=2, default=str)

            # Write file with restricted permissions (0600 = rw-------)
            self.tokens_file.write_text(json_str)
            self.tokens_file.chmod(0o600)

            logger.info(f"Tokens saved to {self.tokens_file}")

        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")
            raise

    def load_tokens(self) -> Optional[TokenData]:
        """
        Load tokens from file.

        Returns:
            TokenData: Token information, or None if file doesn't exist
        """
        if not self.tokens_file.exists():
            logger.debug("No tokens file found")
            return None

        try:
            json_str = self.tokens_file.read_text()
            data = json.loads(json_str)

            # Parse datetime strings
            if "created_at" in data and isinstance(data["created_at"], str):
                data["created_at"] = datetime.fromisoformat(data["created_at"])
            if "updated_at" in data and isinstance(data["updated_at"], str):
                data["updated_at"] = datetime.fromisoformat(data["updated_at"])

            token_data = TokenData(**data)
            logger.debug(f"Loaded tokens (athlete_id: {token_data.athlete_id})")

            return token_data

        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
            return None

    def clear_tokens(self) -> None:
        """Clear stored tokens."""
        if self.tokens_file.exists():
            self.tokens_file.unlink()
            logger.info("Tokens cleared")

    def is_authenticated(self) -> bool:
        """
        Check if user is authenticated (tokens available).

        Returns:
            bool: True if valid tokens exist
        """
        token_data = self.load_tokens()
        if not token_data:
            return False

        # Check if token hasn't expired
        now = datetime.utcnow().timestamp()
        return token_data.expires_at > now

    def _save_state(self, state: str) -> None:
        """Save state for CSRF validation (simple implementation)."""
        # In production, use session or cache with expiration
        state_file = self.tokens_dir / ".oauth_state"
        state_file.write_text(state)
        logger.debug("OAuth state saved")

    def _validate_state(self, state: str) -> bool:
        """Validate state parameter."""
        state_file = self.tokens_dir / ".oauth_state"
        if not state_file.exists():
            logger.warning("No saved state found")
            return False

        saved_state = state_file.read_text()
        is_valid = saved_state == state

        if is_valid:
            state_file.unlink()  # Remove used state
            logger.debug("State validated and cleared")
        else:
            logger.warning("State validation failed - possible CSRF attack")

        return is_valid


def get_oauth_handler() -> StravaOAuth:
    """Get or create OAuth handler instance."""
    return StravaOAuth()
