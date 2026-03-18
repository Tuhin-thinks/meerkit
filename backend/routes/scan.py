from typing import cast

from flask import Blueprint, jsonify, request

from backend.config import profile_data_dir
from backend.routes import get_active_context
from backend.services import persistence, scan_runner

bp = Blueprint("scan", __name__, url_prefix="/api")


@bp.post("/scan")
def trigger_scan():
    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    app_user_id, context = get_active_context(instagram_user_id)
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)

    data_dir = profile_data_dir(app_user_id, instagram_user["instagram_user_id"])
    started = scan_runner.start_scan(
        app_user_id=app_user_id,
        profile_id=instagram_user["instagram_user_id"],
        data_dir=data_dir,
        credentials=instagram_user,
        target_user_id=instagram_user["user_id"],
    )
    if not started:
        return jsonify({"error": "Scan already in progress"}), 409
    return jsonify({"message": "scan started"}), 202


@bp.get("/scan/status")
def scan_status():
    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    app_user_id, context = get_active_context(instagram_user_id)
    if not app_user_id:
        body, status = context
        return jsonify(body), status
    instagram_user = cast(dict, context)
    return jsonify(
        scan_runner.get_status(app_user_id, instagram_user["instagram_user_id"])
    )


@bp.get("/summary")
def summary():
    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    app_user_id, context = get_active_context(instagram_user_id)
    if not app_user_id:
        body, status = context
        return jsonify(body), status
    instagram_user = cast(dict, context)
    meta = persistence.get_latest_scan_meta(instagram_user["instagram_user_id"])
    if not meta:
        return jsonify(None)
    # Enrich with diff counts so the UI has a single call for header stats
    if meta.get("diff_id"):
        diff = persistence.get_diff(meta["diff_id"])
        if diff:
            meta = {
                **meta,
                "new_count": diff["new_count"],
                "unfollow_count": diff["unfollow_count"],
            }
    return jsonify(meta)
