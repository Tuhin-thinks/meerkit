import threading
from datetime import datetime, timedelta
from typing import cast

from backend.extensions import prediction_refresh_queue
from backend.services import db_service

_state_lock = threading.Lock()
_states: dict[str, dict] = {}
_STALE_RUNNING_TIMEOUT = timedelta(minutes=5)


def _set_state(task_id: str, payload: dict) -> None:
    with _state_lock:
        _states[task_id] = payload


def _merge_state(task: dict | None) -> dict | None:
    if not task:
        return None
    overlay = _states.get(task["task_id"])
    if not overlay:
        return task
    return {**task, **overlay}


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_stale_running_task(task: dict | None) -> bool:
    if not task:
        return False

    status = task.get("status")
    if status == "running":
        started_at = _parse_timestamp(task.get("started_at"))
        if started_at is None:
            return True
        return datetime.now() - started_at > _STALE_RUNNING_TIMEOUT

    if status == "queued":
        queued_at = _parse_timestamp(task.get("queued_at"))
        if queued_at is None:
            return True
        return datetime.now() - queued_at > _STALE_RUNNING_TIMEOUT

    return False


def fail_stale_task(task: dict | None) -> dict | None:
    if not is_stale_running_task(task):
        return task
    if task is None:
        return None

    stale_error = (
        "Prediction task stayed queued for more than 5 minutes."
        if task.get("status") == "queued"
        else "Prediction task became inactive after running for more than 5 minutes."
    )
    stale_task = mark_task_error(task["task_id"], stale_error)
    db_service.update_prediction(task["prediction_id"], status="error")
    return stale_task


def normalize_task(task: dict | None) -> dict | None:
    merged_task = _merge_state(task)
    if not merged_task:
        return None
    if is_stale_running_task(merged_task):
        return fail_stale_task(merged_task)
    return merged_task


def get_active_task_bundle(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
) -> dict | None:
    task = normalize_task(
        db_service.get_latest_active_prediction_task(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
        )
    )
    if not task or task.get("status") not in {"queued", "running"}:
        return None

    prediction = db_service.get_prediction(task["prediction_id"])
    if not prediction:
        return None

    return {"task": task, "prediction": prediction}


def enqueue_prediction_refresh(
    prediction_id: str,
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    instagram_user: dict,
    refresh_requested: bool,
    relationship_type: str | None = None,
    fetch_relationships: bool = True,
) -> dict:
    task_type = (
        f"prediction_refresh_{relationship_type}"
        if relationship_type in {"followers", "following"}
        else "prediction_refresh"
    )
    task = db_service.create_prediction_task(
        prediction_id=prediction_id,
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        task_type=task_type,
        refresh_requested=refresh_requested,
    )
    _set_state(task["task_id"], task)
    prediction_refresh_queue.put(
        {
            "task_id": task["task_id"],
            "prediction_id": prediction_id,
            "instagram_user": instagram_user,
            "relationship_type": relationship_type,
            "fetch_relationships": fetch_relationships,
        }
    )
    return task


def mark_task_running(task_id: str) -> dict | None:
    task = db_service.update_prediction_task(
        task_id,
        status="running",
        progress=0.1,
        started_at=db_service._now_iso(),
        error=None,
    )
    if task:
        _set_state(task_id, task)
    return task


def mark_task_progress(task_id: str, progress: float) -> dict | None:
    task = db_service.update_prediction_task(task_id, progress=progress)
    if task:
        _set_state(task_id, task)
    return task


def mark_task_completed(task_id: str) -> dict | None:
    current = get_task_status(task_id)
    if current and current.get("status") == "cancelled":
        return current
    task = db_service.update_prediction_task(
        task_id,
        status="completed",
        progress=1.0,
        completed_at=db_service._now_iso(),
        error=None,
    )
    if task:
        _set_state(task_id, task)
    return task


def mark_task_error(task_id: str, error: str) -> dict | None:
    # Use raw task state here to avoid recursive stale normalization loops:
    # fail_stale_task -> mark_task_error -> get_task_status -> normalize_task -> fail_stale_task
    current = _merge_state(db_service.get_prediction_task(task_id))
    if current and current.get("status") == "cancelled":
        return current
    task = db_service.update_prediction_task(
        task_id,
        status="error",
        error=error,
        completed_at=db_service._now_iso(),
    )
    if task:
        _set_state(task_id, task)
    return task


def get_task_status(task_id: str) -> dict | None:
    return normalize_task(db_service.get_prediction_task(task_id))


def get_latest_task_status(
    app_user_id: str, reference_profile_id: str, target_profile_id: str | None = None
) -> dict | None:
    return normalize_task(
        db_service.get_latest_prediction_task(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
        )
    )


def mark_task_cancelled(task_id: str) -> dict | None:
    task = db_service.update_prediction_task(
        task_id,
        status="cancelled",
        completed_at=db_service._now_iso(),
        error="Cancelled by user.",
    )
    if task:
        _set_state(task_id, task)
    return task


def cancel_task(task_id: str) -> dict | None:
    task = get_task_status(task_id)
    if not task:
        return None

    if task.get("status") in {"completed", "error", "cancelled"}:
        return task

    return mark_task_cancelled(task_id)


def list_active_tasks(app_user_id: str, reference_profile_id: str) -> list[dict]:
    list_tasks_fn = getattr(db_service, "list_active_prediction_tasks", None)
    tasks: list[dict]
    if callable(list_tasks_fn):
        tasks = cast(
            list[dict],
            list_tasks_fn(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
            ),
        )
    else:
        tasks = []

    normalized: list[dict] = []
    for task in tasks:
        item = normalize_task(task)
        if not item:
            continue
        if item.get("status") not in {"queued", "running", "cancelled"}:
            continue
        normalized.append(item)
    return normalized
