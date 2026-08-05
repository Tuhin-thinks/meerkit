# Changelog

All notable changes to meerkit are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-03-18

### Added

- **Initial Release**
- User authentication system (register, login, logout)
- Multi-user support with multiple Instagram accounts per user
- Instagram follower scanning via session credentials
- Automatic diff computation (new followers vs unfollowers)
- SQLite database with scan history and metadata storage
- Profile picture caching (local disk + optional in-memory)
- Responsive Vue 3 frontend with TailwindCSS
- Real-time scan status polling
- Scan history with timeline view
- RESTful API with comprehensive endpoints
- Flask backend with thread-safe background workers
- Image serving via `/api/image/<pk_id>` endpoint
- Admin interface for account management
- Comprehensive documentation with MkDocs + Material theme

### Backend Features

- `/api/auth/*` – User authentication and Instagram account management
- `/api/scan` – Scan triggering and status monitoring
- `/api/diff/*` – Diff retrieval and history
- `/api/image/*` – Cached image serving
- Thread-local database connections for concurrent scans
- Background workers for scanning and image downloading
- CORS support for dev server

### Frontend Features

- Dashboard with scan results (new followers, unfollowers)
- Real-time scan status indicator
- Scan history timeline
- Admin panel for account management
- Profile picture modal viewer
- Responsive design (mobile, tablet, desktop)
- TanStack Query for server state management
- Cookie string parser for easy credential entry
- Credential staleness checker (24-hour threshold)

### Database Schema

- `scan_history` – Scan metadata
- `scanned_data` – Individual follower records
- `diff_records` – Summary of changes
- `image_cache` – Cached image metadata
- `accounts`, `profile_audience_events` – Legacy tables

### Documentation

- `README.md` – Project overview and quick start
- `docs/index.md` – Documentation homepage
- `docs/setup.md` – Installation and configuration
- `docs/architecture.md` – System design and data flow
- `docs/backend.md` – Backend API documentation
- `docs/frontend.md` – Frontend architecture
- `docs/database.md` – Database schema and design
- `docs/development.md` – Development workflow
- `docs/api-reference.md` – Complete API endpoint reference
- `docs/contributing.md` – Contributing guidelines
- `mkdocs.yml` – MkDocs configuration with Material theme

### Known Limitations

- SQLite single-writer limitation (suitable for small-scale use)
- No built-in user-to-user rate limiting
- Image cache cleanup is manual
- Instagram session credentials expire periodically
- No support for private Instagram accounts (by design)

---

## Unreleased

### Added

- **Curl-pattern API gateway**: per-operation curl commands stored in the `api_curl_patterns` table drive all Instagram traffic (`fetch_user_profile_data`, `fetch_followers_list`, `fetch_following_list`, `follow_user`, `unfollow_user`).
- New API Scripts editor in the frontend (`ApiPatternsPanel.vue`, `CurlScriptEditor.vue`, `CurlFieldGroup.vue`) — paste a curl command, review parsed fields, save, generate a Python script, and test it live.
- Curl pattern endpoints under `/api/curl-patterns/*` (parse, CRUD, test, generate) plus per-user field-selection preferences.
- Pagination for followers/following scan endpoints (`next_max_id` cursor for followers; numeric `max_id` incrementing by 12 for following; dedupe by `pk`/`id`; configurable max pages and delay).
- Manual test scripts for the Instagram GraphQL API.

### Fixed

- Instagram API breaking changes: CSRF `fb_dtsg` enforcement and the `/graphql/query` → `/api/graphql` + REST v1 `/api/v1/friendships/...` migration are handled by the curl-pattern gateway.
- Gateway parses both REST v1 and GraphQL response formats for followers/following.
- Hardcoded user IDs in URL paths are replaced with `{{runtime.target_user_id}}` at parse time, and `/friendships/{id}/` path segments are auto-swapped at request build time.
- Follower/following counts are read from both `account_followers_count`/`follower_count` field-name variants.
- Fast-scan race in the dashboard: a scan that completes before the first status poll still refreshes diff/summary/history.
- Deduplication of users across paginated pages.

### Changed

- Session credentials (`csrf_token`, `session_id`, `user_id`) are extracted from stored curl patterns via `extract_session_from_curl_pattern()` instead of `instagram_users.json`.
- `_build_profile()` simplified to gateway-only fields; `doc_id`, `relay_variables`, `extra_cookies`, and `extra_headers` are dead code paths.
- Frontend **Credentials** tab removed; credential refresh now happens by re-saving curl commands in the **API Scripts** tab.
- `script_generator` expands the variables dict and quotes `json.dumps(variables)` in the generated `data_string`.
- Synced documentation with the current codebase across API, backend, frontend, architecture, and database guides.
- Updated API reference to include prediction, tasks, automation, scan cancellation, cache metrics, safelists, and alternative-account link endpoints.
- Corrected documentation examples to match sanitized auth/account payloads (no credential fields in API responses).
- Fixed developer docs to use the real Python package path (`meerkit/`) for linting/formatting/type-check commands.
- Added `LEGACY_USER_DETAILS_CACHE_WRITE_ENABLED` feature flag to support phased deprecation of legacy `user_details` cache writes.
- Standardized target user data cache source through the gateway cache envelope flow while keeping optional compatibility writes.
- Improved alternative-account followback assessment to prefer target graph follower evidence and robust key matching.

### Planned Features

- [ ] PostgreSQL support for scalability
- [ ] Redis caching layer
- [ ] Celery task queue for distributed scans
- [ ] Webhook notifications for follower changes
- [ ] Email digest reports
- [ ] CSV/Excel export of scan data
- [ ] Advanced filtering and search
- [ ] Analytics dashboard
- [ ] Dark mode
- [ ] Mobile app
- [ ] Two-factor authentication
- [ ] Automated scheduled scans
- [ ] Follower activity timeline
- [ ] Engagement metrics
- [ ] Community features (compare profiles, leaderboards)

### Performance Improvements

- [ ] Database query optimization
- [ ] Image caching improvements
- [ ] Frontend code splitting
- [ ] API response compression

### Developer Experience

- [ ] Docker containerization
- [ ] GitHub Actions CI/CD
- [ ] Better error messages
- [ ] Debugging tools
- [ ] API SDK/client library

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- `MAJOR` version when incompatible API changes
- `MINOR` version when adding functionality in backwards-compatible manner
- `PATCH` version for backwards-compatible bug fixes

## Release Process

1. Update `VERSION` in appropriate files
2. Update `CHANGELOG.md` with changes
3. Create git tag: `git tag v0.1.0`
4. Push: `git push origin main --tags`
5. Build release artifacts
6. Create GitHub Release

## Support

- **Latest Version:** 0.1.0
- **Python Support:** 3.12+
- **Node Support:** 20+

## Deprecated Features

None yet.

## Security

### Latest Security Fixes

None yet (v0.1.0 initial release).

---

## Previous Versions

No previous versions.

---

## Contributors

- [Your Name] – Initial development

---

## Timeline

- **2026-03-18** – v0.1.0 Initial Release

---

Copyright &copy; 2026 meerkit contributors
