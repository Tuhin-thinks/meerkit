# Database

The backend uses SQLite with schemas defined in `meerkit/db/schemas.py` and runtime initialization in `meerkit/db/db_handler.py`.

## Storage Model

- SQLite DB is opened through `meerkit/services/db_service.py`.
- DB path is resolved by `meerkit.config.app_user_db()`.
- Data and caches are stored under `data/`.

## Core Tables

### Scan + Diff

- `scan_history`
- `scanned_data`
- `diff_records`
- `image_cache`

Used for scan snapshots, per-scan follower rows, diff metadata, and profile-image cache references.

### Account + Legacy

- `accounts`
- `profile_audience_events`

### Target Profile + Relationship Cache

- `target_profiles`
- `target_profile_relationships`
- `target_profile_list_cache_entries`

Used by prediction and automation features to track fetched metadata and relationship lists.

### Prediction Domain

- `predictions`
- `prediction_tasks`
- `prediction_assessments`

Supports prediction sessions, background refresh tasks, and user feedback/assessment.

### API Usage Metrics

- `instagram_api_usage_events`

Tracks API calls and cache-hit events by category/service/method.

!!! warning "⚠️ Instagram Rate Limits Apply"
    Keep follow/unfollow actions under **150–200/day** (new accounts: **under 100/day**). Spread actions gradually throughout the day. [Monitor your API usage →](showcase.md#5-api-monitoring-and-limits)

### Curl Pattern Gateway

- `api_curl_patterns`
- `user_preferences`

`api_curl_patterns` stores the per-operation curl commands that drive the Instagram API gateway, keyed uniquely by `(app_user_id, internal_name)`:

| Column | Type | Purpose |
|---|---|---|
| `id` | INTEGER PK | Auto-increment row id |
| `app_user_id` | TEXT | Owning app user |
| `internal_name` | TEXT | Gateway operation (`fetch_user_profile_data`, `fetch_followers_list`, `fetch_following_list`, `follow_user`, `unfollow_user`, ...) |
| `display_name` | TEXT | Human-readable label |
| `curl_command` | TEXT | The original pasted curl command |
| `url` | TEXT | Parsed request URL (with `{{runtime.*}}` placeholders) |
| `http_method` | TEXT | `GET` or `POST` (default `POST`) |
| `selected_cookies` / `selected_headers` / `selected_data` / `selected_variables` | TEXT (JSON arrays) | Which parsed fields the rebuilt request should send |
| `generated_script` | TEXT | Optional generated Python `requests` script |
| `is_active` | INTEGER | Soft enable/disable flag |
| `created_at` / `updated_at` | TEXT | Timestamps |

`user_preferences` stores per-user, per-pattern field-selection preferences (key/value JSON) so the API Scripts editor remembers the user's selections.

### Automation Domain

- `automation_actions`
- `automation_action_items`
- `automation_safelists`
- `automation_alt_account_links`
- `automation_primary_accounts`

Supports staged/queued/running automation workflows, exclusion lists, and linked-account registry.

## Indexes

The schema includes indexes for high-use access patterns, including:

- prediction scope/session queries
- automation scope queries
- relationship cache scope queries
- API usage aggregation queries
- curl pattern lookup by `(app_user_id, internal_name)`

See index definitions in `meerkit/db/schemas.py`.

## Schema Evolution

`SqliteDBHandler` performs startup-safe schema updates:

- ensures required tables exist
- backfills newer columns where needed (for example `last_heartbeat_at`, `prediction_session_id`)
- creates missing indexes

## Common Query Patterns

- latest scan metadata for active profile
- latest diff and diff lookup by ID
- active prediction tasks by scope
- active/recoverable automation actions
- grouped API usage summary per account/category
- curl pattern lookup for the API gateway (`get_pattern`, `list_patterns`)

## Operational Notes

- SQLite is suitable for local/single-node operation.
- Thread-local DB handlers are used for concurrent worker threads.
- Background workers initialize and close DB handlers per thread lifecycle.

For endpoint-level behavior, see [API Reference](api-reference.md).
