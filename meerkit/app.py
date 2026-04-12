import logging
import os
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

# Ensure workspace root is on sys.path so get_current_followers and insta_interface
# are importable regardless of the working directory Flask is launched from.
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from flask_cors import CORS

from meerkit.config import (
    LOG_FILE_PATH,
    LOG_LEVEL,
    LOG_REDACT_SENSITIVE_FIELDS,
    LOG_ROTATION_BACKUP_COUNT,
    LOG_ROTATION_MAX_BYTES,
    LOG_SUPPRESSED_LOGGERS,
    LOGGING_ENABLED,
)
from meerkit.exceptions import ConfigurationError
from meerkit.logging_config import setup_logging
from meerkit.logging_context import bind_context, clear_context

logger = logging.getLogger(__name__)


def _is_dev_or_test_environment() -> bool:
    return (
        os.environ.get("FLASK_ENV") in {"development", "testing"}
        or os.environ.get("FLASK_DEBUG") == "1"
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )


def _resolve_secret_key() -> str:
    secret_key = os.environ.get("APP_SECRET_KEY")
    if secret_key:
        return secret_key
    if os.environ.get("FLASK_ENV") == "production":
        raise ConfigurationError(
            "APP_SECRET_KEY environment variable is required",
            error_code="missing_app_secret_key",
            env_var="APP_SECRET_KEY",
        )
    if _is_dev_or_test_environment():
        return "dev-secret-change-me"
    return "dev-secret-change-me"


def _resolve_cors_origins() -> list[str]:
    raw_origins = os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:4173"
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:5173", "http://localhost:4173"]


def create_app() -> Flask:
    setup_logging(
        enabled=LOGGING_ENABLED,
        log_level=LOG_LEVEL,
        log_file_path=LOG_FILE_PATH,
        max_bytes=LOG_ROTATION_MAX_BYTES,
        backup_count=LOG_ROTATION_BACKUP_COUNT,
        redact_sensitive_fields=LOG_REDACT_SENSITIVE_FIELDS,
        suppressed_loggers=LOG_SUPPRESSED_LOGGERS,
    )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = _resolve_secret_key()

    @app.before_request
    def _bind_request_context() -> None:
        from flask import g, request, session

        g.request_started_at = perf_counter()
        bind_context(
            request_id=str(uuid4()),
            app_user_id=session.get("app_user_id"),
            request_path=request.path,
            request_method=request.method,
        )

    @app.after_request
    def _log_request(response):
        from flask import g, request

        started_at = float(getattr(g, "request_started_at", perf_counter()))
        logger.info(
            "http_request_completed",
            extra={
                "event": "http_request_completed",
                "metrics": {
                    "status_code": int(response.status_code),
                    "duration_ms": int((perf_counter() - started_at) * 1000),
                },
                "request_path": request.path,
                "request_method": request.method,
            },
        )
        return response

    @app.teardown_request
    def _clear_request_context(_exc) -> None:
        clear_context()

    # Allow Vite dev server (5173) and preview server (4173) in development
    CORS(
        app,
        resources={r"/api/*": {"origins": _resolve_cors_origins()}},
    )

    from meerkit.routes.auth import bp as auth_bp
    from meerkit.routes.automation import bp as automation_bp
    from meerkit.routes.history import bp as history_bp
    from meerkit.routes.images import bp as images_bp
    from meerkit.routes.predict import bp as predict_bp
    from meerkit.routes.scan import bp as scan_bp
    from meerkit.routes.tasks import bp as tasks_bp
    from meerkit.workers import automation_worker, download_worker, prediction_worker

    is_debug = (
        os.environ.get("FLASK_DEBUG") == "1"
        or os.environ.get("FLASK_ENV") == "development"
    )
    # In debug/reload mode, Werkzeug starts a parent + child process.
    # Start the worker only in the reloader child process.
    if (is_debug and os.environ.get("WERKZEUG_RUN_MAIN") == "true") or (not is_debug):
        download_worker.start_download_worker()
        prediction_worker.start_prediction_worker()
        automation_worker.start_automation_worker()

    app.register_blueprint(auth_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(predict_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(automation_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        port=int(os.environ.get("PORT", "5000")),
    )
