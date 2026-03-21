import threading

from backend.extensions import prediction_refresh_queue
from backend.services import db_service

_state_lock = threading.Lock()
_states: dict[str, dict] = {}


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


def enqueue_prediction_refresh(
    prediction_id: str,
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    instagram_user: dict,
    refresh_requested: bool,
) -> dict:
    task = db_service.create_prediction_task(
        prediction_id=prediction_id,
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        task_type="prediction_refresh",
        refresh_requested=refresh_requested,
    )
    _set_state(task["task_id"], task)
    prediction_refresh_queue.put(
        {
            "task_id": task["task_id"],
            "prediction_id": prediction_id,
            "instagram_user": instagram_user,
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
    return _merge_state(db_service.get_prediction_task(task_id))


def get_latest_task_status(
    app_user_id: str, reference_profile_id: str, target_profile_id: str | None = None
) -> dict | None:
    return _merge_state(
        db_service.get_latest_prediction_task(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
        )
    )
