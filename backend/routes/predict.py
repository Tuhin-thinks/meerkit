from typing import cast

from flask import Blueprint, jsonify, request

from backend.routes import get_active_context
from backend.services import account_handler, db_service, prediction_runner

bp = Blueprint("predict", __name__, url_prefix="/api")


def _active_scope() -> tuple[str | None, dict | tuple[dict, int]]:
    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    return get_active_context(instagram_user_id)


@bp.post("/predictions/follow-back")
def create_followback_prediction():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip() or None
    user_id = (payload.get("user_id") or "").strip() or None
    refresh = bool(payload.get("refresh", False))
    force_background = bool(payload.get("force_background", False))
    relationship_type = (payload.get("relationship_type") or "").strip() or None

    try:
        result = account_handler.request_followback_prediction(
            app_user_id=app_user_id,
            instagram_user=instagram_user,
            username=username,
            user_id=user_id,
            refresh=refresh,
            force_background=force_background,
            relationship_type=relationship_type,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    status_code = 202 if result.get("task") else 200
    return jsonify(result), status_code


@bp.get("/targets/<target_profile_id>/relationship-cache")
def get_relationship_cache_status(target_profile_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    sync_counts = request.args.get("sync_counts", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    try:
        payload = account_handler.get_target_relationship_cache_status(
            app_user_id=app_user_id,
            instagram_user=instagram_user,
            target_profile_id=target_profile_id,
            sync_counts=sync_counts,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


@bp.post("/targets/<target_profile_id>/relationship-cache/refresh")
def refresh_relationship_cache(target_profile_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    payload = request.get_json(silent=True) or {}
    relationship_type = (payload.get("relationship_type") or "").strip().lower()
    if relationship_type not in {"followers", "following"}:
        return jsonify(
            {"error": "relationship_type must be followers or following"}
        ), 400

    try:
        result = account_handler.request_followback_prediction(
            app_user_id=app_user_id,
            instagram_user=instagram_user,
            user_id=target_profile_id,
            refresh=True,
            force_background=True,
            relationship_type=relationship_type,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result), 202 if result.get("task") else 200


@bp.get("/predictions/history")
def prediction_history():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    target_profile_id = request.args.get("target_profile_id")
    limit = int(request.args.get("limit", 50))
    predictions = db_service.list_predictions(
        app_user_id=app_user_id,
        reference_profile_id=instagram_user["instagram_user_id"],
        target_profile_id=target_profile_id,
        limit=limit,
    )
    return jsonify(predictions)


@bp.get("/predictions/<prediction_id>")
def get_prediction(prediction_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    prediction = db_service.get_prediction(prediction_id)
    if not prediction:
        return jsonify({"error": "Prediction not found"}), 404
    task = None
    if prediction.get("task_id"):
        task = prediction_runner.get_task_status(prediction["task_id"])
    return jsonify(
        {
            "prediction": prediction,
            "task": task,
            "assessments": db_service.list_prediction_assessments(prediction_id),
        }
    )


@bp.patch("/predictions/<prediction_id>/feedback")
def patch_prediction_feedback(prediction_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    payload = request.get_json(silent=True) or {}
    assessment_status = (payload.get("assessment_status") or "").strip()
    notes = payload.get("notes")
    observed_at = payload.get("observed_at")
    if assessment_status not in {"correct", "wrong", "pending_review", "ignored"}:
        return jsonify({"error": "Invalid assessment_status"}), 400

    try:
        assessment = account_handler.record_prediction_feedback(
            prediction_id=prediction_id,
            assessment_status=assessment_status,
            notes=notes,
            observed_at=observed_at,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(assessment)


@bp.get("/prediction-tasks/<task_id>/status")
def prediction_task_status(task_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    task = prediction_runner.get_task_status(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)


@bp.get("/prediction-tasks/latest")
def latest_prediction_task_status():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    target_profile_id = request.args.get("target_profile_id")
    task = prediction_runner.get_latest_task_status(
        app_user_id=app_user_id,
        reference_profile_id=instagram_user["instagram_user_id"],
        target_profile_id=target_profile_id,
    )
    return jsonify(task)


@bp.post("/prediction-tasks/<task_id>/cancel")
def cancel_prediction_task(task_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    task = prediction_runner.get_task_status(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if task.get("app_user_id") != app_user_id:
        return jsonify({"error": "Task not found"}), 404

    cancelled = prediction_runner.cancel_task(task_id)
    if not cancelled:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"task": cancelled})
