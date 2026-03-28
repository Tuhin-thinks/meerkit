"""
Automation runner — action state machine.

Wraps automation_actions DB updates across the worker lifecycle,
analogous to prediction_runner for prediction_tasks.
"""

import threading
from datetime import datetime, timedelta

from meerkit.config import AUTOMATION_STALE_TIMEOUT_MINUTES
from meerkit.services import db_service

_state_lock = threading.Lock()
# In-memory overlay for actions currently in-flight — key: action_id
_states: dict[str, dict] = {}
_STALE_RUNNING_TIMEOUT = timedelta(minutes=AUTOMATION_STALE_TIMEOUT_MINUTES)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _set_state(action_id: str, payload: dict) -> None:
    with _state_lock:
        _states[action_id] = payload


def _merge_state(action: dict | None) -> dict | None:
    if not action:
        return None
    overlay = _states.get(action["action_id"])
    if not overlay:
        return action
    return {**action, **overlay}


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_stale_running_action(action: dict | None) -> bool:
    if not action:
        return False
    status = action.get("status")
    if status == "running":
        last_activity_at = _parse_timestamp(action.get("last_heartbeat_at"))
        if last_activity_at is None:
            last_activity_at = _parse_timestamp(action.get("started_at"))
        if last_activity_at is None:
            return True
        return datetime.now() - last_activity_at > _STALE_RUNNING_TIMEOUT
    if status == "queued":
        queued_at = _parse_timestamp(action.get("queued_at"))
        if queued_at is None:
            return True
        return datetime.now() - queued_at > _STALE_RUNNING_TIMEOUT
    return False


def normalize_action(action: dict | None) -> dict | None:
    merged = _merge_state(action)
    if not merged:
        return None
    if is_stale_running_action(merged):
        return _fail_stale_action(merged)
    return merged


def _fail_stale_action(action: dict) -> dict | None:
    timeout_minutes = int(_STALE_RUNNING_TIMEOUT.total_seconds() // 60)
    msg = (
        f"Automation action stayed queued for more than {timeout_minutes} minutes."
        if action.get("status") == "queued"
        else f"Automation action became inactive after running for more than {timeout_minutes} minutes."
    )
    return mark_action_error(action["action_id"], msg)


def get_action_status(action_id: str) -> dict | None:
    return normalize_action(db_service.get_automation_action(action_id))


def mark_action_running(action_id: str) -> dict | None:
    now = _now_iso()
    db_service.update_automation_action(
        action_id,
        status="running",
        started_at=now,
        last_heartbeat_at=now,
        completed_at=None,
        error=None,
    )
    action = db_service.get_automation_action(action_id)
    if action:
        _set_state(action_id, action)
    return action


def mark_action_heartbeat(action_id: str) -> dict | None:
    db_service.update_automation_action(action_id, last_heartbeat_at=_now_iso())
    action = db_service.get_automation_action(action_id)
    if action:
        _set_state(action_id, action)
    return action


def mark_action_completed(action_id: str) -> dict | None:
    current = get_action_status(action_id)
    if current and current.get("status") == "cancelled":
        return current
    now = _now_iso()
    db_service.update_automation_action(
        action_id,
        status="completed",
        last_heartbeat_at=now,
        completed_at=now,
        error=None,
    )
    action = db_service.get_automation_action(action_id)
    if action:
        _set_state(action_id, action)
    return action


def mark_action_partial(action_id: str) -> dict | None:
    """Mark the action as partial when some items completed and some failed."""
    now = _now_iso()
    db_service.update_automation_action(
        action_id,
        status="partial",
        last_heartbeat_at=now,
        completed_at=now,
    )
    action = db_service.get_automation_action(action_id)
    if action:
        _set_state(action_id, action)
    return action


def mark_action_error(action_id: str, error: str) -> dict | None:
    current = _merge_state(db_service.get_automation_action(action_id))
    if current and current.get("status") == "cancelled":
        return current
    now = _now_iso()
    db_service.update_automation_action(
        action_id,
        status="error",
        error=error,
        last_heartbeat_at=now,
        completed_at=now,
    )
    action = db_service.get_automation_action(action_id)
    if action:
        _set_state(action_id, action)
    return action


def mark_action_cancelled(action_id: str) -> dict | None:
    now = _now_iso()
    db_service.update_automation_action(
        action_id,
        status="cancelled",
        last_heartbeat_at=now,
        completed_at=now,
        error="Cancelled by user.",
    )
    action = db_service.get_automation_action(action_id)
    if action:
        _set_state(action_id, action)
    return action


def cancel_action(action_id: str) -> dict | None:
    action = get_action_status(action_id)
    if not action:
        return None
    if action.get("status") in {"completed", "partial", "error", "cancelled"}:
        return action
    return mark_action_cancelled(action_id)


def record_item_completed(action_id: str) -> None:
    action = db_service.get_automation_action(action_id)
    if not action:
        return
    db_service.update_automation_action(
        action_id,
        completed_items=(action.get("completed_items") or 0) + 1,
        last_heartbeat_at=_now_iso(),
    )
    if action:
        _set_state(action_id, db_service.get_automation_action(action_id) or action)


def record_item_failed(action_id: str) -> None:
    action = db_service.get_automation_action(action_id)
    if not action:
        return
    db_service.update_automation_action(
        action_id,
        failed_items=(action.get("failed_items") or 0) + 1,
        last_heartbeat_at=_now_iso(),
    )
    if action:
        _set_state(action_id, db_service.get_automation_action(action_id) or action)


def list_active_actions(
    app_user_id: str,
    reference_profile_id: str,
    *,
    action_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    rows = db_service.list_automation_actions(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        statuses=[
            "queued",
            "running",
            "staged",
            "completed",
            "partial",
            "error",
            "cancelled",
        ],
        limit=limit,
    )
    normalized = [a for a in (normalize_action(r) for r in rows) if a is not None]
    if action_type:
        normalized = [a for a in normalized if a.get("action_type") == action_type]
    return normalized
