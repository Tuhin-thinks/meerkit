# API Reference

This document lists the currently implemented HTTP API in the Flask backend.

!!! warning "⚠️ Instagram Rate Limits Apply"
    Keep follow/unfollow actions under **150–200/day** (new accounts: **under 100/day**). Spread actions gradually throughout the day. [Monitor your API usage →](showcase.md#5-api-monitoring-and-limits)

## Base URL

- Development: `http://localhost:5000/api`
- Production: `https://<your-domain>/api`

## Auth Model

- Cookie-based Flask session auth is used.
- Public endpoints: `POST /auth/register`, `POST /auth/login`
- All other endpoints require a logged-in app user.
- Most data endpoints are scoped by active Instagram account and accept either:
  - `profile_id=<instagram_user_id>`
  - `instagram_user_id=<instagram_user_id>`

## Error Format

All API errors return JSON:

```json
{
  "error": "Description"
}
```

Common status codes: `200`, `201`, `202`, `400`, `401`, `404`, `409`, `502`.

## Auth Endpoints (`/api/auth`)

### POST `/auth/register`
Create app user.

Request:

```json
{
  "name": "alice",
  "password": "secret"
}
```

Response `201`:

```json
{
  "app_user_id": "app_...",
  "name": "alice"
}
```

### POST `/auth/login`
Log in app user and return profile context.

Response `200`:

```json
{
  "app_user_id": "app_...",
  "name": "alice",
  "instagram_users": [
    {
      "instagram_user_id": "123456",
      "name": "Primary IG",
      "username": "alice_ig",
      "created_at": "2026-03-20T10:30:00",
      "credentials_old": false,
      "credentials_age_hours": 4
    }
  ],
  "active_instagram_user": {
    "instagram_user_id": "123456",
    "name": "Primary IG",
    "username": "alice_ig",
    "created_at": "2026-03-20T10:30:00",
    "credentials_old": false,
    "credentials_age_hours": 4
  }
}
```

Note: credential fields (`session_id`, `csrf_token`, `password_hash`) are never returned.

### POST `/auth/logout`
Clear session.

Response `200`:

```json
{
  "ok": true
}
```

### GET `/auth/me`
Get current app-user context.

Response `200` (not logged in):

```json
null
```

### GET `/auth/instagram-api-usage`
Get grouped API/caching usage summary.

Optional query:

- `instagram_user_id`

### GET `/auth/instagram-users`
List Instagram accounts for current app user (sanitized payload).

### POST `/auth/instagram-users`
Create Instagram account for current app user.

Request:

```json
{
  "name": "Primary IG",
  "csrf_token": "...",
  "session_id": "...",
  "user_id": "123456"
}
```

Response `201`:

```json
{
  "instagram_user": {
    "instagram_user_id": "123456",
    "name": "Primary IG",
    "username": "alice_ig",
    "created_at": "2026-03-20T10:30:00",
    "credentials_old": false,
    "credentials_age_hours": 0
  },
  "me": {
    "app_user_id": "app_...",
    "name": "alice",
    "instagram_users": [],
    "active_instagram_user": null
  }
}
```

### GET `/auth/instagram-users/<instagram_user_id>`
Get one Instagram account (sanitized payload).

### PATCH `/auth/instagram-users/<instagram_user_id>`
Update account display name and/or credentials via cookie string.

Request:

```json
{
  "display_name": "Updated Name",
  "cookie_string": "sessionid=...; ds_user_id=...; csrftoken=..."
}
```

> **Note:** The frontend "Credentials" tab was removed. Session credential refresh is now done by re-capturing and re-saving curl commands in the **API Scripts** tab; this PATCH endpoint remains for display-name updates and cookie-string refreshes.

### POST `/auth/instagram-users/<instagram_user_id>/select`
Set active Instagram account.

### DELETE `/auth/instagram-users/<instagram_user_id>`
Delete one Instagram account and associated data scope.

### DELETE `/auth/instagram-users`
Delete all Instagram accounts for current app user.

## Curl Pattern Endpoints (`/api/curl-patterns`)

These endpoints manage the per-operation curl commands that drive the Instagram API gateway. Patterns are stored in the `api_curl_patterns` table, keyed by `(app_user_id, internal_name)`.

Supported `internal_name` values: `fetch_user_profile_data`, `fetch_followers_list`, `fetch_following_list`, `follow_user`, `unfollow_user`, `search_user`.

### POST `/curl-patterns/parse`
Parse a pasted curl command into URL, HTTP method, and field suggestions.

Request:

```json
{
  "curl_text": "curl 'https://www.instagram.com/...' -H '...' --data-raw '...'"
}
```

Response `200`:

```json
{
  "url": "https://www.instagram.com/api/graphql",
  "http_method": "POST",
  "cookies": {},
  "headers": {},
  "data": {},
  "variables": {},
  "suggestions": {
    "cookies": [],
    "headers": [],
    "data": [],
    "variables": []
  }
}
```

Response `400` with `code: "parse_error"` when the command cannot be parsed.

### GET `/curl-patterns`
List all stored patterns for the current scope.

### GET `/curl-patterns/<internal_name>`
Get one pattern, or `null` when not configured.

### POST `/curl-patterns/<internal_name>`
Store (create or replace) a pattern.

Request fields:

- `display_name` (required)
- `curl_command` (required)
- `url` (required)
- `http_method` (required, default `POST`)
- `selected_cookies`, `selected_headers`, `selected_data`, `selected_variables` (JSON arrays)
- `generated_script` (optional)

Returns the stored pattern row.

### PATCH `/curl-patterns/<internal_name>`
Update a subset of pattern fields (`display_name`, `curl_command`, `url`, `http_method`, `selected_*`, `generated_script`, `is_active`).

### DELETE `/curl-patterns/<internal_name>`
Delete a pattern.

Response `200`:

```json
{
  "ok": true
}
```

### POST `/curl-patterns/<internal_name>/test`
Execute the saved pattern against the live Instagram endpoint (session values extracted from the stored curl command). Useful for checking that a session is still valid.

Response `200`:

```json
{
  "status_code": 200,
  "elapsed_ms": 120,
  "response_text": "{...}",
  "success": true
}
```

### POST `/curl-patterns/<internal_name>/generate`
Generate a standalone Python `requests` script from the saved pattern.

Response `200`:

```json
{
  "script": "import pprint\n..."
}
```

### GET `/curl-patterns/preferences/<key>`
Get stored field-selection preferences for a key (or `null`).

### PUT `/curl-patterns/preferences/<key>`
Store field-selection preferences (`selected_cookies`, `selected_headers`, `selected_data`, `selected_variables`).

## Scan & History Endpoints (`/api`)

### POST `/scan`
Start async follower scan.

Requires at least one configured curl pattern (session values are extracted from the stored patterns). Without one, returns `400` with `"No API patterns configured. Please set up at least one curl pattern first."`

### GET `/scan/status`
Get scan status (`idle | running | cancelled | error`) and last scan metadata.

### POST `/scan/cancel`
Mark running scan as cancelled.

### GET `/summary`
Get latest scan summary (or `null` if no scan yet).

### GET `/history`
Get scan history.

Query options:

- `range=recent|all_time`
- `days`
- `limit`
- `offset`

### GET `/scan-analytics`
Get day-bucketed analytics for recent scan deltas.

Query options:

- `days` (default `30`)

### GET `/diff/latest`
Get latest computed diff.

### GET `/diff/<diff_id>`
Get a specific diff by ID.

## Image Endpoint (`/api`)

### GET `/image/<pk_id>`
Serve cached profile image or queue download and return placeholder.

- `pk_id` must be numeric.
- Returns image bytes (`image/jpeg`) when successful.

## Prediction Endpoints (`/api`)

### POST `/predictions/follow-back`
Create or refresh a follow-back prediction.

Request fields:

- `username` or `user_id`
- `refresh` (optional)
- `force_background` (optional)
- `relationship_type` (`followers|following`, optional)
- `prediction_session_id` (optional)

Returns `200` for immediate result or `202` when background task is queued.

### GET `/targets/<target_profile_id>/relationship-cache`
Get relationship cache status for a target.

Optional query:

- `sync_counts=true|false`

### POST `/targets/<target_profile_id>/relationship-cache/refresh`
Refresh one relationship cache (`followers` or `following`) in background.

### GET `/predictions/history`
List prediction sessions/history.

Query options:

- `target_profile_id`
- `limit` (max `200`)
- `offset`

### GET `/predictions/history/sessions/<prediction_session_id>`
List predictions in one session.

### GET `/predictions/<prediction_id>`
Get prediction record, linked task status, and assessments.

### PATCH `/predictions/<prediction_id>/feedback`
Store feedback/assessment.

Request fields include:

- `assessment_status`: `correct|wrong|pending_review|ignored`
- `notes`
- `observed_at`
- `expected_direction`: `higher|lower`
- `expected_value`: `0.0..1.0`

### GET `/prediction-tasks/<task_id>/status`
Get one prediction task status.

### GET `/prediction-tasks/latest`
Get latest prediction task for current scope.

Optional query:

- `target_profile_id`

### POST `/prediction-tasks/<task_id>/cancel`
Cancel queued/running prediction task.

## Tasks Endpoint (`/api`)

### GET `/tasks`
Unified live task list combining:

- prediction tasks
- scan tasks
- automation actions

Cancelled tasks are retained briefly for UI visibility.

## Automation Endpoints (`/api/automation`)

!!! warning "⚠️ Instagram Rate Limit Warning"
    **Do not bulk follow or unfollow users on Instagram.** Doing so can trigger Instagram's spam detection and may lead to account restrictions.

    | Scenario | Safe daily limit |
    |---|---|
    | General / established accounts | 150 – 200 follow/unfollow actions |
    | New accounts (first few weeks) | Stay under 100 actions |

    - Spread your actions **gradually throughout the day** to avoid detection.
    - If you exceed the limit, Instagram may:
        - Temporarily block your actions (for hours or days)
        - Limit your reach (**shadowban**)
        - **Permanently disable** your account if abuse continues

    > **Note:** These limits are not officially confirmed by Instagram — they are based on extensive community testing and experience with Instagram automation tools.

    Use [`GET /auth/instagram-api-usage`](#get-authinstagram-api-usage) to monitor your live API call counts, or check the **Admin → Account Details → API Usage** tab in the UI. See also: [API Monitoring and Limits](showcase.md#5-api-monitoring-and-limits).

### GET `/automation/cache-efficiency`
Get read-cache hit/call efficiency summary per category.

### GET `/automation/cache-size`
Get cache scope disk stats.

### GET `/automation/following-users`
Get current following list enriched with follows-you and count metadata.

### POST `/automation/batch-follow/prepare`
Stage intelligent batch-follow action.

### POST `/automation/batch-unfollow/prepare`
Stage batch-unfollow action.

### POST `/automation/left-right-compare/prepare`
Stage left-right comparison action.

### POST `/automation/actions/<action_id>/confirm`
Queue staged automation action for execution.

### POST `/automation/actions/<action_id>/cancel`
Cancel automation action.

### GET `/automation/actions/<action_id>`
Get action details with `items_by_status`.

### GET `/automation/actions`
List actions for current scope.

Query options:

- `action_type`
- `limit` (max `500`)

### GET `/automation/safelists/<list_type>`
Get safelist entries.

`list_type` values:

- `do_not_follow`
- `never_unfollow`

### POST `/automation/safelists/<list_type>`
Add entries to safelist.

Request:

```json
{
  "entries": ["@user1", "https://instagram.com/user2"]
}
```

### DELETE `/automation/safelists/<list_type>/<identity_key>`
Delete one safelist entry.

### GET `/automation/alternative-account-links`
List alternative-account links.

Optional query:

- `primary_identity_key`

### POST `/automation/alternative-account-links`
Add primary-to-alternative account links.

Request:

```json
{
  "primary_account": "@primary",
  "alternative_accounts": ["@alt1", "@alt2"],
  "linkedin_accounts": ["https://linkedin.com/in/..."],
  "trigger_discovery": true
}
```

### DELETE `/automation/alternative-account-links/<primary_identity_key>/<alt_identity_key>`
Delete one alternative-account link.

## Minimal Example Flow

```bash
# 1) login
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"name":"alice","password":"secret"}'

# 2) select active IG account
curl -X POST http://localhost:5000/api/auth/instagram-users/123456/select

# 3) store a curl pattern (captured from browser DevTools)
curl -X POST "http://localhost:5000/api/curl-patterns/fetch_followers_list" \
  -H "Content-Type: application/json" \
  -d '{"display_name":"Fetch Followers","curl_command":"curl ...","url":"...","http_method":"POST"}'

# 4) start scan (requires at least one stored pattern)
curl -X POST "http://localhost:5000/api/scan?profile_id=123456"

# 5) poll status
curl "http://localhost:5000/api/scan/status?profile_id=123456"

# 6) read latest diff
curl "http://localhost:5000/api/diff/latest?profile_id=123456"
```

Next: [Backend API](backend.md), [Architecture](architecture.md)
