from datetime import datetime
from typing import cast

from flask import Blueprint, jsonify, request

from meerkit.config import TASKS_CANCELLED_EXPIRY_SECONDS, TASKS_MAX_RECENT_COUNT
from meerkit.routes import get_active_context
from meerkit.services import automation_runner, prediction_runner, scan_runner

bp = Blueprint("tasks", __name__, url_prefix="/api")


def _keep_task(task: dict) -> bool:
    """Return False for cancelled tasks that have been cancelled for more than 5 minutes."""
    if task.get("status") != "cancelled":
        return True
    completed_at = task.get("completed_at")
    if not completed_at:
        return True
    try:
        age = (datetime.now() - datetime.fromisoformat(completed_at)).total_seconds()
        return age < TASKS_CANCELLED_EXPIRY_SECONDS
    except ValueError:
        return True


@bp.get("/tasks")
def list_tasks():
    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    app_user_id, context = get_active_context(instagram_user_id)
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id = instagram_user["instagram_user_id"]

    prediction_tasks = prediction_runner.list_active_tasks(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
    )
    scan_tasks = scan_runner.list_running_scans(app_user_id)
    active_scan_task = scan_runner.get_active_scan_task(
        app_user_id, reference_profile_id
    )
    if active_scan_task:
        scan_task_ids = {task.get("task_id") for task in scan_tasks}
        if active_scan_task.get("task_id") not in scan_task_ids:
            scan_tasks.append(active_scan_task)

    automation_actions = automation_runner.list_active_actions(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
    )

    normalized_prediction_tasks = [
        {
            "task_id": task["task_id"],
            "task_type": task.get("task_type") or "prediction_refresh",
            "source": "prediction",
            "status": task.get("status"),
            "progress": task.get("progress"),
            "error": task.get("error"),
            "queued_at": task.get("queued_at"),
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at"),
            "target_profile_id": task.get("target_profile_id"),
            "target_username": None,
            "can_cancel": task.get("status") in {"queued", "running"},
            "metric_label": "progress",
            "metric_value": int(round((task.get("progress") or 0) * 100)),
        }
        for task in prediction_tasks
    ]

    normalized_automation_tasks = [
        {
            "task_id": action["action_id"],
            "task_type": action.get("action_type") or "automation",
            "source": "automation",
            "status": action.get("status"),
            "progress": None,
            "error": action.get("error"),
            "queued_at": action.get("queued_at"),
            "started_at": action.get("started_at"),
            "completed_at": action.get("completed_at"),
            "target_profile_id": None,
            "target_username": None,
            "can_cancel": action.get("status") in {"queued", "running", "staged"},
            "metric_label": "items_completed",
            "metric_value": (action.get("completed_items") or 0),
            "total_items": action.get("total_items") or 0,
            "completed_items": action.get("completed_items") or 0,
            "failed_items": action.get("failed_items") or 0,
            "skipped_items": action.get("skipped_items") or 0,
        }
        for action in automation_actions
    ]

    tasks = sorted(
        [*normalized_prediction_tasks, *scan_tasks, *normalized_automation_tasks],
        key=lambda item: item.get("started_at") or item.get("queued_at") or "",
        reverse=True,
    )
    tasks = [t for t in tasks if _keep_task(t)]

    running_tasks = [
        item for item in tasks if item.get("status") in {"queued", "running"}
    ]
    non_running_tasks = [
        item for item in tasks if item.get("status") not in {"queued", "running"}
    ]

    # Always include all active tasks, then fill with recent non-running tasks.
    if running_tasks:
        max_non_running = max(TASKS_MAX_RECENT_COUNT - len(running_tasks), 0)
        tasks = [*running_tasks, *non_running_tasks[:max_non_running]]
    else:
        tasks = non_running_tasks[:TASKS_MAX_RECENT_COUNT]

    running_count = sum(
        1 for item in tasks if item.get("status") in {"queued", "running"}
    )

    return jsonify(
        {
            "running_count": running_count,
            "total": len(tasks),
            "tasks": tasks,
        }
    )
