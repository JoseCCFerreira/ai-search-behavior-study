# Strava API Setup & OAuth 2.0

## Overview

This document walks you through setting up Strava Developer credentials and implementing OAuth 2.0 authentication for the Performance Coach application.

## Part 1: Create Strava Developer App

### Step 1: Go to Strava Settings

1. Open [https://www.strava.com/settings/api](https://www.strava.com/settings/api)
2. You must be logged into your Strava account
3. If you don't have a Strava account, create one at [strava.com](https://www.strava.com)

### Step 2: Register Application

Fill in the form with:

| Field | Value |
|-------|-------|
| **Application Name** | `Strava Performance Coach` |
| **Website** | `http://localhost:8000` (or your domain) |
| **Category** | `Training` |
| **Club** | Leave empty |
| **Description** | `Personal performance analysis and coaching system` |
| **Authorization Callback Domain** | `localhost` |

### Step 3: Accept Terms

- ✅ Check "I understand and agree to the Strava Platform License Agreement and Community Guidelines"
- ✅ Check "I have read and understand the Privacy Policy"
- Click "Create"

### Step 4: Get Credentials

After creation, you'll see:

- **Client ID**: A number (e.g., 12345)
- **Client Secret**: A long string (e.g., abc123def456...)
- **Authorization Callback Domain**: localhost

**⚠️ IMPORTANT**: 
- Never share your Client Secret
- Never commit it to Git
- Store it only in `.env` file (git-ignored)

### Step 5: Get Your Athlete ID

Your Athlete ID is needed for testing:

1. Go to your profile: [https://www.strava.com/athletes/me](https://www.strava.com/athletes/me)
2. Look at the URL: `https://www.strava.com/athletes/YOUR_ATHLETE_ID`
3. Note down the number

## Part 2: Configure Environment Variables

### Edit `.env` File

```bash
# Copy example if not already done
cp .env.example .env

# Edit .env with your values
nano .env  # or open in VS Code
```

### Set These Values

```env
# Strava OAuth Configuration
STRAVA_CLIENT_ID=your_client_id_here
STRAVA_CLIENT_SECRET=your_client_secret_here
STRAVA_REDIRECT_URI=http://localhost:8000/auth/callback

# Strava Webhook (for later phases)
STRAVA_VERIFY_TOKEN=your_random_verification_token_here

# Database
DUCKDB_PATH=database/strava_coach.duckdb

# Application
APP_ENV=local
DEBUG=True
LOG_LEVEL=DEBUG
```

Example (sanitized):
```env
STRAVA_CLIENT_ID=12345
STRAVA_CLIENT_SECRET=abc123def456ghi789jkl
STRAVA_REDIRECT_URI=http://localhost:8000/auth/callback
STRAVA_VERIFY_TOKEN=my_random_webhook_token_12345
DUCKDB_PATH=database/strava_coach.duckdb
APP_ENV=local
DEBUG=True
LOG_LEVEL=DEBUG
```

### Verify .env Loading

```bash
python -c "from config.settings import settings; print(f'Client ID: {settings.strava_client_id}')"
```

Should print your Client ID without the word "your".

## Part 3: Understand OAuth 2.0 Flow

### What is OAuth 2.0?

OAuth 2.0 allows you to authorize the app to access your Strava data **without** giving it your password.

### Flow Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    User (You)                             │
└──────────────────────────────────────────────────────────┘
                          │
                          │ 1. Login
                          ▼
┌──────────────────────────────────────────────────────────┐
│             Strava Authorization Server                   │
│   (https://www.strava.com/oauth/authorize)               │
└──────────────────────────────────────────────────────────┘
                          │
                          │ 2. Grant Permission
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│        Your App (Performance Coach)                       │
│   (receives authorization code)                           │
└──────────────────────────────────────────────────────────┘
                          │
                          │ 3. Exchange code for tokens
                          │    (using Client Secret)
                          ▼
┌──────────────────────────────────────────────────────────┐
│             Strava Token Server                           │
│   (https://www.strava.com/oauth/token)                   │
└──────────────────────────────────────────────────────────┘
                          │
                          │ 4. Receive tokens
                          │    - access_token (short-lived)
                          │    - refresh_token (long-lived)
                          ▼
┌──────────────────────────────────────────────────────────┐
│             Your App Storage                              │
│   (store tokens securely)                                │
└──────────────────────────────────────────────────────────┘
```

### Tokens Explained

**Access Token**:
- Short-lived (6 hours)
- Used to make API requests
- Example: `Bearer abc123...`

**Refresh Token**:
- Long-lived (never expires)
- Used to get a new access token when it expires
- Kept secure in storage

**Expires At**:
- Timestamp when access_token expires
- Checked before each API call

## Part 4: Scopes & Permissions

### What Scopes Do We Need?

| Scope | Permission | Why |
|-------|-----------|-----|
| `read` | Read public activities | Basic data access |
| `activity:read` | Read private activities | Your activities |
| `activity:read_all` | Read all activities | Historical data |
| `profile:read_all` | Read athlete info | User profile |
| `profile:write` | Write athlete info | Not needed for MVP |

For this project, we use: **`read,activity:read_all,profile:read_all`**

### Authorization URL

When you first authenticate, you'll be directed to:

```
https://www.strava.com/oauth/authorize?
    client_id=YOUR_CLIENT_ID&
    response_type=code&
    redirect_uri=http://localhost:8000/auth/callback&
    scope=read,activity:read_all,profile:read_all&
    state=random_string_for_security
```

User clicks "Authorize" → Strava redirects to your callback URL with `code` parameter

## Part 5: Token Refresh

### Why Refresh Tokens?

Access tokens expire (6 hours). Instead of asking user to re-authorize, we use refresh tokens to get new ones automatically.

### Refresh Process

```python
# Before making API call
if token_expired(access_token, expires_at):
    new_token = refresh_access_token(refresh_token)
    store_new_token(new_token)
    
# Make API call with valid token
response = api.get_activity(activity_id, access_token)
```

### Local Token Storage

⚠️ **Note**: In production, use secure storage (encrypted database, secrets manager). For local development, we use a JSON file with restricted permissions:

```json
{
  "access_token": "abc123...",
  "refresh_token": "def456...",
  "expires_at": 1234567890,
  "athlete_id": 12345,
  "scope": "read,activity:read_all"
}
```

File location: `.tokens/strava_tokens.json`
Permissions: `0600` (read/write for owner only)

## Part 6: Security Best Practices

### ✅ DO:
- Store Client Secret in `.env` (git-ignored)
- Use HTTPS for API calls
- Validate tokens before use
- Refresh tokens proactively
- Use state parameter in OAuth (prevents CSRF attacks)
- Log token operations (without logging the token value)

### ❌ DON'T:
- Commit `.env` to Git
- Log token values
- Store tokens in plain text
- Share Client Secret
- Use client credentials for user login
- Hardcode URLs or tokens

### Token Storage Hierarchy

```
Level 1 (Most Secure): Cloud Secrets Manager (HashiCorp Vault, AWS Secrets Manager)
Level 2: Encrypted Database with encryption keys in Environment
Level 3: .env file with file permissions (current MVP)
Level 4: Config file in repo (❌ NEVER DO THIS)
```

For MVP (local development): Level 3 is fine.

## Part 7: Implementation Details

See `src/auth/strava_oauth.py` for:

1. `generate_authorization_url()` - Creates login URL
2. `exchange_code_for_tokens()` - Trades code for tokens
3. `refresh_access_token_if_needed()` - Keeps tokens fresh
4. `save_tokens()` - Stores tokens locally
5. `load_tokens()` - Retrieves stored tokens

## Part 8: Testing OAuth Locally

### Manual Test

```bash
# Start FastAPI server
uvicorn src.connector.strava_webhook:app --reload --port 8000

# In browser, visit:
# http://localhost:8000/auth/login

# You'll be redirected to Strava
# Log in and authorize
# You'll be redirected back with a code
# Token stored in .tokens/strava_tokens.json
```

### Programmatic Test

```python
from src.auth.strava_oauth import StravaOAuth

oauth = StravaOAuth()

# Generate authorization URL
url = oauth.generate_authorization_url()
print(f"Visit this URL: {url}")

# Later, after user authorizes (manually or in test):
code = "YOUR_AUTH_CODE_FROM_REDIRECT"
tokens = oauth.exchange_code_for_tokens(code)
print(f"Access Token: {tokens['access_token'][:20]}...")
```

## Part 9: Rate Limiting

Strava API has rate limits:

- **Short term**: 600 requests per 15 minutes
- **Long term**: 30,000 requests per day

Our implementation:

1. Respects `Retry-After` header
2. Logs when approaching limits
3. Implements exponential backoff for retries
4. Queues requests if needed

Monitor in logs:
```
Rate limit: 599 requests remaining in 15 minutes
```

## Part 10: Webhook Verification

For webhooks (Phase 5), Strava sends a verification request:

```
GET /strava/webhook?hub.mode=subscribe&hub.challenge=abc123&hub.verify_token=YOUR_VERIFY_TOKEN
```

Response must be:
```json
{"hub.challenge":"abc123"}
```

See `src/connector/strava_webhook.py` for implementation.

## Troubleshooting

### Error: "Invalid Client ID"

```
Solution: Check .env has correct STRAVA_CLIENT_ID
```

### Error: "Redirect URI mismatch"

```
Solution: Ensure STRAVA_REDIRECT_URI in .env matches what's in Strava app settings
```

### Error: "Token expired"

```
Solution: Normal! Use refresh_token to get new access_token
```

### Error: "Scope not authorized"

```
Solution: User didn't authorize that scope. Re-authorize with correct scopes.
```

## Next Steps

- ✅ Phase 2: Developer App setup complete
- 📋 Phase 3: Implement OAuth in code (src/auth/strava_oauth.py)
- 📋 Phase 4: Create Strava API client
- 📋 Phase 5: Implement webhooks

## Additional Resources

- [Strava API Documentation](https://developers.strava.com/docs/)
- [OAuth 2.0 Specification](https://tools.ietf.org/html/rfc6749)
- [Strava Developer Community](https://groups.google.com/forum/#!forum/strava-api)

---

**Phase 2 complete! Ready for Phase 3 - OAuth Implementation.** 🚀
