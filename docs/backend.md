# Backend API

This page describes the current Flask backend architecture under the `meerkit` package.

## Runtime Overview

- App factory: `meerkit/app.py`
- Framework: Flask + Flask-CORS
- Storage: per-user SQLite files via `meerkit/services/db_service.py`
- Async workers:
  - `meerkit/workers/download_worker.py`
  - `meerkit/workers/prediction_worker.py`
  - `meerkit/workers/automation_worker.py`
- Scan execution entry: `meerkit/scan_worker.py` + `get_current_followers.py`
- Instagram access: curl-pattern API gateway (`meerkit/services/instagram_gateway.py`)

## Package Layout

```text
meerkit/
├── app.py
├── config.py
├── extensions.py
├── scan_worker.py
├── routes/
│   ├── auth.py
│   ├── scan.py
│   ├── history.py
│   ├── images.py
│   ├── predict.py
│   ├── tasks.py
│   ├── automation.py
│   └── curl_patterns.py
├── services/
│   ├── auth_service.py
│   ├── scan_runner.py
│   ├── prediction_runner.py
│   ├── automation_runner.py
│   ├── automation_service.py
│   ├── instagram_gateway.py
│   ├── curl_pattern_service.py
│   ├── script_generator.py
│   ├── instagram_response_cache.py
│   ├── instagram_api_usage.py
│   ├── relationship_cache.py
│   ├── user_details_cache.py
│   ├── persistence.py
│   └── db_service.py
├── db/
│   ├── db_handler.py
│   └── schemas.py
└── workers/
    ├── download_worker.py
    ├── prediction_worker.py
    └── automation_worker.py
```

## Route Groups

All routes are registered in `meerkit/app.py`.

### Auth (`/api/auth`)

- app user register/login/logout/me
- Instagram account CRUD/select
- Instagram API usage summary

### Curl Patterns (`/api/curl-patterns`)

- parse a pasted curl command into URL/method/cookie/header/data/variable suggestions
- list/get/store/update/delete per-operation patterns
- test a saved pattern against the live Instagram endpoint
- generate a standalone Python `requests` script from a saved pattern
- per-user field-selection preferences

### Scan + History (`/api`)

- trigger scan, poll status, cancel scan
- summary, history, analytics
- latest diff and diff by ID

### Predictions (`/api`)

- follow-back prediction create/refresh
- relationship cache status + refresh
- prediction history + session history
- prediction details + feedback
- prediction task status/latest/cancel

### Tasks (`/api`)

- unified active task feed for scan/prediction/automation

### Automation (`/api/automation`)

- cache efficiency + cache size
- following-user discovery
- batch follow/unfollow/left-right-compare prepare flows
- action confirm/cancel/status/list
- safelists (`do_not_follow`, `never_unfollow`)
- alternative-account link registry

### Images (`/api`)

- profile image serve/cache queue endpoint

## Instagram Gateway (Curl Patterns)

`meerkit/services/instagram_gateway.py` is the tracked wrapper around all Instagram calls. Instead of hardcoded request logic it executes stored **curl patterns**:

- Every operation maps to an `internal_name` (`fetch_user_profile_data`, `fetch_followers_list`, `fetch_following_list`, `follow_user`, `unfollow_user`).
- `meerkit/services/curl_pattern_service.py` stores patterns in the `api_curl_patterns` table, extracts session values from them (`extract_session_from_curl_pattern()`), and rebuilds live requests (`build_request()`) with `{{session.*}}` / `{{runtime.*}}` substitution and automatic `max_id` pagination.
- `meerkit/services/script_generator.py` renders a standalone Python `requests` script (Jinja2 template) from a saved pattern.
- `_pattern_call_paginated()` walks multi-page follower/following lists and `_parse_user_records()` handles both REST v1 and GraphQL response shapes.

See [Architecture](architecture.md) for a diagram and [API Reference](api-reference.md) for the curl-pattern endpoints.

## Worker Model

- Scan runs in a background thread via `scan_runner.start_scan()`.
- Prediction refresh tasks are queued and consumed by prediction workers.
- Automation actions are durable in DB and resumed/recovered by automation workers.
- Image downloads are queued and processed by download workers.

## Session + Scope Model

- Browser session stores `app_user_id` and `active_instagram_user_id`.
- Route helper `get_active_context()` resolves app-user + Instagram-user scope.
- Most scoped routes accept query override via `profile_id` or `instagram_user_id`.
- Instagram session credentials (`csrftoken`, `sessionid`, `ds_user_id`) are extracted from the stored curl patterns at call time — not stored in the app user's session.

## Caching + Metrics

!!! warning "⚠️ Instagram Rate Limits Apply"
    Keep follow/unfollow actions under **150–200/day** (new accounts: **under 100/day**). Spread actions gradually throughout the day. [Monitor your API usage →](showcase.md#5-api-monitoring-and-limits)

- Gateway response cache for Instagram read operations:
  - user lookup
  - user data fetch
  - followers/following discovery
- Cache hit/call metrics are stored as `instagram_api_usage_events`.
- Automation endpoints expose efficiency and size summaries.

## Error Handling Conventions

- Auth/context failures: `401` or `400`
- Missing resource: `404`
- In-progress conflict: `409`
- Validation errors: `400`
- Upstream/Instagram fetch failures in automation list fetch: `502`
- Missing curl patterns: `400` with a "set up at least one curl pattern" hint (scan), or `MissingCurlPatternError` surfaced from gateway calls

## Local Run

```bash
uv run flask --app meerkit.app run --debug --port 5000
```

Production-like run:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 "meerkit.app:create_app()"
```

## Tests

```bash
uv run pytest
```

See also: [API Reference](api-reference.md), [Architecture](architecture.md), [Database](database.md)
