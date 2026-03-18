from typing import cast

from flask import Blueprint, jsonify

from backend.routes import get_active_context
from backend.services import persistence
from backend.services.db_service import get_scan_history

bp = Blueprint("history", __name__, url_prefix="/api")


@bp.get("/history")
def history():
    app_user_id, context = get_active_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)

    return jsonify(get_scan_history(instagram_user["instagram_user_id"]))


@bp.get("/diff/latest")
def latest_diff():
    app_user_id, context = get_active_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)

    diff = persistence.get_latest_diff(
        reference_profile_id=instagram_user["instagram_user_id"]
    )

    return jsonify(diff)


@bp.get("/diff/<diff_id>")
def get_diff(diff_id: str):
    diff = persistence.get_diff(diff_id=diff_id)
    if not diff:
        return jsonify({"error": "Diff not found"}), 404
    return jsonify(diff)
