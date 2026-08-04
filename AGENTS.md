# Meerkit – AGENTS.md

## Quick start (dev)

```bash
uv sync --dev                                    # install Python deps
cd frontend && npm install && cd ..              # install frontend deps

# Run both frontend and backend together:
./scripts/launch.sh

# Or run them separately:
# terminal 1:
uv run flask --app meerkit.app run --debug --port 5000
# terminal 2:
cd frontend && npm run dev                       # Vite on :5173, proxies /api -> :5000
```

Open http://localhost:5173

## Commands

| What | How |
|---|---|
| Run all Python tests | `uv run pytest` (or `python -m pytest` inside venv) |
| Run single test file | `uv run pytest tests/test_auth_response_sanitization.py -v` |
| Run docs server | `uv run mkdocs serve` |
| Lint / format Python | `uv run ruff check . && uv run black --check .` |
| Type-check Python | `uv run mypy meerkit/` |
| Build frontend | `cd frontend && npm run build` (runs `vue-tsc && vite build`) |
| Frontend lint | `cd frontend && npm run lint` (ESLint) |

## Architecture

- **Backend**: Flask app factory in `meerkit/app.py:create_app()`. Routes under `meerkit/routes/`, business logic in `meerkit/services/`, background workers in `meerkit/workers/` (in-process threading, not Celery).
- **Frontend**: Vue 3 + TypeScript + Vite + Pinia + TanStack Query + TailwindCSS. Entry: `frontend/src/main.ts`, router: `frontend/src/router/index.ts`, API client: `frontend/src/services/api.ts`. API scope managed via `setActiveInstagramUserForApi()`.
- **Database**: Per-user SQLite files at `data/app_user_db.sqlite` via `meerkit/db/`. Schema in `meerkit/db/schemas.py`. No migration framework — columns added via `_ensure_*` PRAGMA checks in `SqliteDBHandler`.
- **Instagram scraping**: Top-level modules `insta_interface.py` and `get_current_followers.py` (imported directly, not under `meerkit/`). `sys.path` is patched in `app.py` to make them importable.
- **Data dirs**: `data/users/<app_user_id>/profiles/<profile_id>/data/` for scans/diffs/cache. Config in `meerkit/config.py` — all env-configurable.

## Code quality

- Python: `ruff` for lint, `black` for format, `mypy` for type-check.
- Frontend: ESLint + vue-tsc (`npm run build` type-checks before bundling).
- `.github/instructions/python.instructions.md` enforces typing style (Python 3.12 `X | None`, no `Optional`), error handling, and naming conventions. Follow it.

## Testing quirks

- Test credentials go in `tests/.test.env` (not committed to prod env). VSCode launch config loads it for debug runs.
- Integration tests hit real Instagram — they need a valid `.test.env` with `IG_CSRF_TOKEN`, `IG_SESSION_ID`, `IG_USER_ID`, `IG_TARGET_USERNAME`.
- Some tests may create files in `tests/outputs/` (gitignored).

## Key env vars

| Variable | Default | Notes |
|---|---|---|
| `APP_SECRET_KEY` | `dev-secret-change-me` | Required in production |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:4173` | Comma-separated |
| `LEGACY_USER_DETAILS_CACHE_WRITE_ENABLED` | `1` | Set to `0` to disable legacy cache writes |
| `LOGGING_ENABLED` | `true` | Set to `false` to disable structured JSON logging |
| `LOG_LEVEL` | `DEBUG` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Important gotchas

- **Workers + Flask reload**: In debug mode, workers (`download_worker`, `prediction_worker`, `automation_worker`) start *only* in the reloader child process (guarded by `WERKZEUG_RUN_MAIN`). Do not move worker startup outside that guard.
- **Top-level imports**: `meerkit/app.py` inserts workspace root on `sys.path` so `insta_interface` and `get_current_followers` are importable. If importing those modules elsewhere, the path must be set first.
- **Thread-local DB**: `SqliteDBHandler` connections are managed per-thread in `db_service.py` via `threading.local()`.
- **Scans are single-flight**: `scan_runner.start_scan()` acquires a per-scope `threading.Lock` — returns `False` if already running.
- **Follow/unfollow rate limits**: Hard limit of ~150-200 actions/day. Automation has built-in delays (`AUTOMATION_INTER_ACTION_DELAY_SECONDS`, `AUTOMATION_INTER_ACTION_JITTER_SECONDS`).

## Commit style

Conventional commits per `.github/.copilot-commit-message-instructions.md`: `<type>(<scope>): <subject>` with types `feat|fix|docs|refactor|perf|test|chore|ci`.

## Dependencies

- Python: `uv` (uv.lock committed), Python 3.12+.
- Frontend: npm (package-lock.json committed).
