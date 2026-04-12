import logging
from collections.abc import Callable
from datetime import datetime
from time import perf_counter
from typing import TypeVar

from meerkit.services import db_service

T = TypeVar("T")
logger = logging.getLogger(__name__)


class InstagramApiUsageTracker:
    """Best-effort tracker for Instagram API usage events."""

    def track_cache_hit(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        category: str,
        caller_service: str,
        caller_method: str,
    ) -> None:
        try:
            db_service.create_instagram_api_usage_event(
                app_user_id=app_user_id,
                instagram_user_id=instagram_user_id,
                category=f"{category}_cache_hit",
                caller_service=caller_service,
                caller_method=caller_method,
                success=True,
                duration_ms=0,
                called_at=datetime.now().isoformat(),
            )
        except Exception as exc:
            # Metrics collection should never break primary workflows.
            logger.warning(
                "instagram_api_usage_cache_hit_record_failed",
                extra={
                    "event": "instagram_api_usage_cache_hit_record_failed",
                    "error": str(exc),
                    "app_user_id": app_user_id,
                    "instagram_user_id": instagram_user_id,
                    "category": category,
                },
            )

    def track_call(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        category: str,
        caller_service: str,
        caller_method: str,
        execute: Callable[[], T],
    ) -> T:
        started = perf_counter()
        called_at = datetime.now().isoformat()
        success = True
        try:
            return execute()
        except Exception:
            success = False
            raise
        finally:
            duration_ms = int((perf_counter() - started) * 1000)
            try:
                db_service.create_instagram_api_usage_event(
                    app_user_id=app_user_id,
                    instagram_user_id=instagram_user_id,
                    category=category,
                    caller_service=caller_service,
                    caller_method=caller_method,
                    success=success,
                    duration_ms=duration_ms,
                    called_at=called_at,
                )
            except Exception as exc:
                # Metrics collection should never break primary workflows.
                logger.warning(
                    "instagram_api_usage_event_record_failed",
                    extra={
                        "event": "instagram_api_usage_event_record_failed",
                        "error": str(exc),
                        "app_user_id": app_user_id,
                        "instagram_user_id": instagram_user_id,
                        "category": category,
                        "metrics": {"duration_ms": duration_ms, "success": success},
                    },
                )


instagram_api_usage_tracker = InstagramApiUsageTracker()
