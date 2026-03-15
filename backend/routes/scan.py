from flask import Blueprint, jsonify, request, session

from backend.config import profile_data_dir
from backend.services import auth, persistence, scan_runner

bp = Blueprint("scan", __name__, url_prefix="/api")


def _current_context() -> tuple[str, dict] | tuple[None, tuple[dict, int]]:
    """Return logged-in app user + active instagram user, or an API error tuple."""
    app_user_id = session.get("app_user_id")
    if not app_user_id:
        return None, ({"error": "Not logged in"}, 401)

    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    if not instagram_user_id:
        instagram_user_id = auth.get_active_instagram_user_id(app_user_id)
    if not instagram_user_id:
        return None, ({"error": "No active instagram user selected"}, 400)

    instagram_user = auth.get_instagram_user(app_user_id, instagram_user_id)
    if not instagram_user:
        return None, ({"error": "Instagram user not found"}, 404)

    return app_user_id, instagram_user


@bp.post("/scan")
def trigger_scan():
    app_user_id, context = _current_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = context

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
    app_user_id, context = _current_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status
    instagram_user = context
    data_dir = profile_data_dir(app_user_id, instagram_user["instagram_user_id"])
    return jsonify(
        scan_runner.get_status(
            app_user_id, instagram_user["instagram_user_id"], data_dir
        )
    )


@bp.get("/summary")
def summary():
    app_user_id, context = _current_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status
    instagram_user = context
    data_dir = profile_data_dir(app_user_id, instagram_user["instagram_user_id"])
    meta = persistence.get_latest_scan_meta(data_dir)
    if not meta:
        return jsonify(None)
    # Enrich with diff counts so the UI has a single call for header stats
    if meta.get("diff_id"):
        diff = persistence.get_diff(data_dir, meta["diff_id"])
        if diff:
            meta = {
                **meta,
                "new_count": diff["new_count"],
                "unfollow_count": diff["unfollow_count"],
            }
    return jsonify(meta)
