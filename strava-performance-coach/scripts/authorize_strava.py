"""Authorize Strava and store local OAuth tokens."""

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import StravaOAuth


def extract_query_value(value: str, key: str) -> str:
    """Extract a query parameter from a full callback URL or raw value."""
    value = value.strip()
    if key not in value and "://" not in value:
        return value

    parsed = urlparse(value)
    params = parse_qs(parsed.query)
    values = params.get(key)
    return values[0] if values else ""


def main() -> None:
    oauth = StravaOAuth()
    url = oauth.generate_authorization_url()

    print("\nOpen this URL in your browser and authorize the app:\n")
    print(url)
    print(
        "\nAfter Strava redirects to localhost, copy the full browser URL "
        "or just the 'code' value."
    )

    callback_or_code = input("\nCallback URL or code: ").strip()
    code = extract_query_value(callback_or_code, "code")
    state = extract_query_value(callback_or_code, "state")

    if not code:
        raise SystemExit("No authorization code found.")

    token_data = oauth.exchange_code_for_tokens(code=code, state=state or None)
    print("\nAuthorized successfully.")
    print(f"Athlete ID: {token_data.athlete_id}")
    print(f"Tokens saved to: {oauth.tokens_file}")


if __name__ == "__main__":
    main()
