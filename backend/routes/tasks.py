from typing import cast

from flask import Blueprint, jsonify, request

from backend.routes import get_active_context
from backend.services import prediction_runner, scan_runner

bp = Blueprint("tasks", __name__, url_prefix="/api")


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
    active_scan_task = scan_runner.get_active_scan_task(app_user_id, reference_profile_id)
    if active_scan_task:
        scan_task_ids = {task.get("task_id") for task in scan_tasks}
        if active_scan_task.get("task_id") not in scan_task_ids:
            scan_tasks.append(active_scan_task)

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

    tasks = sorted(
        [*normalized_prediction_tasks, *scan_tasks],
        key=lambda item: item.get("started_at") or item.get("queued_at") or "",
        reverse=True,
    )

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
