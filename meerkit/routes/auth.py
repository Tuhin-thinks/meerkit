from flask import Blueprint, jsonify, request, session

from meerkit.routes.error_mapping import map_exception_to_response
from meerkit.services import auth_service, curl_pattern_service, db_service

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _error_response(exc: Exception):
    body, status = map_exception_to_response(exc)
    return jsonify(body), status


def _sanitize_instagram_user_payload(instagram_user: dict | None) -> dict | None:
    """Apply a route-level safety filter for instagram user response payloads."""
    return auth_service.sanitize_instagram_user(instagram_user)


def _sanitize_me_payload(payload: dict) -> dict:
    """Apply defense-in-depth filtering to /me-like response payloads."""
    sanitized = dict(payload)
    instagram_users = payload.get("instagram_users")
    if isinstance(instagram_users, list):
        sanitized["instagram_users"] = auth_service.sanitize_instagram_users(
            instagram_users
        )
    else:
        sanitized["instagram_users"] = []

    active_instagram_user = payload.get("active_instagram_user")
    if isinstance(active_instagram_user, dict):
        sanitized["active_instagram_user"] = _sanitize_instagram_user_payload(
            active_instagram_user
        )
    else:
        sanitized["active_instagram_user"] = None

    return sanitized


def _current_app_user() -> tuple[str, str] | None:
    """Return the logged-in app user id and name from session state."""
    app_user_id = session.get("app_user_id")
    app_user_name = session.get("app_user_name")
    if not app_user_id or not app_user_name:
        return None
    return app_user_id, app_user_name


def _sync_active_instagram_user_session(app_user_id: str) -> str | None:
    """Keep the browser session aligned with the persisted active instagram user."""
    active_instagram_user_id = auth_service.get_active_instagram_user_id(app_user_id)
    session["active_instagram_user_id"] = active_instagram_user_id
    return active_instagram_user_id


@bp.post("/register")
def register():
    """Create a new app user account using name/password."""
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    password = (payload.get("password") or "").strip()
    if not name or not password:
        return jsonify({"error": "name and password are required"}), 400

    try:
        user = auth_service.register_app_user(name, password)
    except Exception as exc:
        return _error_response(exc)

    return jsonify(user), 201


@bp.post("/login")
def login():
    """Log in an app user by name/password."""
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    password = (payload.get("password") or "").strip()

    user = auth_service.login_app_user(name, password)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    session["app_user_id"] = user["app_user_id"]
    session["app_user_name"] = user["name"]
    _sync_active_instagram_user_session(user["app_user_id"])
    return jsonify(
        _sanitize_me_payload(
            auth_service.build_me_payload(user["app_user_id"], user["name"])
        )
    )


@bp.post("/logout")
def logout():
    """Clear app session for current browser."""
    app_user_id = session.get("app_user_id")
    if app_user_id:
        auth_service.clear_user_session_payload(app_user_id)
    session.clear()
    return jsonify({"ok": True})


@bp.get("/me")
def me():
    """Return current app-user context and owned instagram users."""
    current = _current_app_user()
    if not current:
        return jsonify(None)

    app_user_id, app_user_name = current
    _sync_active_instagram_user_session(app_user_id)

    return jsonify(
        _sanitize_me_payload(auth_service.build_me_payload(app_user_id, app_user_name))
    )


@bp.get("/instagram-api-usage")
def instagram_api_usage_summary():
    """Return grouped Instagram API usage metrics for current app user."""
    current = _current_app_user()
    if not current:
        return jsonify({"error": "Not logged in"}), 401

    app_user_id, _app_user_name = current
    instagram_user_id = (request.args.get("instagram_user_id") or "").strip() or None

    summary = db_service.get_instagram_api_usage_summary(
        app_user_id=app_user_id,
        instagram_user_id=instagram_user_id,
    )
    users = auth_service.get_instagram_users(app_user_id)
    account_name_by_id = {
        str(user.get("instagram_user_id")): user.get("name")
        for user in users
        if user.get("instagram_user_id")
    }
    for account in summary.get("accounts", []):
        account["account_name"] = account_name_by_id.get(
            str(account.get("instagram_user_id"))
        )
    return jsonify(summary)


@bp.get("/instagram-users")
def list_instagram_users():
    """List instagram users for the current app user."""
    current = _current_app_user()
    if not current:
        return jsonify({"error": "Not logged in"}), 401
    app_user_id, _app_user_name = current
    return jsonify(auth_service.sanitize_instagram_users(auth_service.get_instagram_users(app_user_id)))


@bp.post("/instagram-users")
def create_instagram_user():
    """Create a new instagram user with mandatory session credentials."""
    current = _current_app_user()
    if not current:
        return jsonify({"error": "Not logged in"}), 401
    app_user_id, app_user_name = current

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    csrf_token = (payload.get("csrf_token") or "").strip()
    session_id = (payload.get("session_id") or "").strip()
    user_id = (payload.get("user_id") or "").strip()

    try:
        instagram_user = auth_service.add_instagram_user(
            app_user_id=app_user_id,
            name=name,
            csrf_token=csrf_token,
            session_id=session_id,
            user_id=user_id,
        )
    except Exception as exc:
        return _error_response(exc)

    _sync_active_instagram_user_session(app_user_id)

    return jsonify(
        {
            "instagram_user": _sanitize_instagram_user_payload(instagram_user),
            "me": _sanitize_me_payload(
                auth_service.build_me_payload(app_user_id, app_user_name)
            ),
        }
    ), 201


@bp.get("/instagram-users/<instagram_user_id>")
def get_instagram_user_detail(instagram_user_id: str):
    """Get one instagram user details for details page."""
    current = _current_app_user()
    if not current:
        return jsonify({"error": "Not logged in"}), 401
    app_user_id, _app_user_name = current

    instagram_user = auth_service.get_instagram_user(app_user_id, instagram_user_id)
    if not instagram_user:
        return jsonify({"error": "Instagram user not found"}), 404
    return jsonify(_sanitize_instagram_user_payload(instagram_user))


VALID_OPERATIONS = {
    "fetch_user_profile_data",
    "follow_user",
    "unfollow_user",
    "fetch_followers_list",
    "fetch_following_list",
    "search_user",
}

OPERATION_DISPLAY_NAMES = {
    "fetch_user_profile_data": "Fetch Profile Data",
    "follow_user": "Follow User",
    "unfollow_user": "Unfollow User",
    "fetch_followers_list": "Fetch Followers List",
    "fetch_following_list": "Fetch Following List",
    "search_user": "Search User",
}


@bp.patch("/instagram-users/<instagram_user_id>")
def patch_instagram_user(instagram_user_id: str):
    """Update instagram user display name and/or cookie-derived credentials."""
    current = _current_app_user()
    if not current:
        return jsonify({"error": "Not logged in"}), 401
    app_user_id, app_user_name = current

    payload = request.get_json(silent=True) or {}
    display_name = payload.get("display_name")
    cookie_string = payload.get("cookie_string")
    curl_command = payload.get("curl_command")
    operation = payload.get("operation")

    if display_name is not None and not isinstance(display_name, str):
        return jsonify({"error": "display_name must be a string"}), 400
    if cookie_string is not None and not isinstance(cookie_string, str):
        return jsonify({"error": "cookie_string must be a string"}), 400
    if curl_command is not None and not isinstance(curl_command, str):
        return jsonify({"error": "curl_command must be a string"}), 400
    if operation is not None and not isinstance(operation, str):
        return jsonify({"error": "operation must be a string"}), 400

    if operation and operation not in VALID_OPERATIONS:
        return jsonify({
            "error": f"Invalid operation. Must be one of: {', '.join(sorted(VALID_OPERATIONS))}"
        }), 400

    curl_pattern_stored = False

    if curl_command and operation:
        try:
            parsed = curl_pattern_service.parse_curl(curl_command)
            display_name_label = OPERATION_DISPLAY_NAMES.get(operation, operation)
            curl_pattern_service.store_pattern(
                app_user_id=app_user_id,
                internal_name=operation,
                display_name=display_name_label,
                curl_command=curl_command,
                url=parsed["url"],
                http_method=parsed["http_method"],
                selected_cookies=[
                    f["key"] for f in parsed["suggestions"]["cookies"] if f["selected"]
                ],
                selected_headers=[
                    f["key"] for f in parsed["suggestions"]["headers"] if f["selected"]
                ],
                selected_data=[
                    f["key"] for f in parsed["suggestions"]["data"] if f["selected"]
                ],
                selected_variables=[
                    f["key"] for f in parsed["suggestions"]["variables"] if f["selected"]
                ],
            )
            curl_pattern_stored = True
        except Exception as exc:
            return _error_response(exc)

    try:
        instagram_user = auth_service.update_instagram_user(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            display_name=display_name,
            cookie_string=cookie_string,
            curl_command=curl_command if not curl_pattern_stored else None,
        )
    except Exception as exc:
        return _error_response(exc)

    if not instagram_user:
        return jsonify({"error": "Instagram user not found"}), 404

    message = "Instagram account updated"
    if curl_pattern_stored:
        message = f"{OPERATION_DISPLAY_NAMES.get(operation, operation)} curl pattern stored"

    return jsonify(
        {
            "instagram_user": _sanitize_instagram_user_payload(instagram_user),
            "me": _sanitize_me_payload(
                auth_service.build_me_payload(app_user_id, app_user_name)
            ),
            "message": message,
        }
    )


@bp.post("/instagram-users/<instagram_user_id>/select")
def select_instagram_user(instagram_user_id: str):
    """Set active instagram user for scan/history/image scoped operations."""
    current = _current_app_user()
    if not current:
        return jsonify({"error": "Not logged in"}), 401
    app_user_id, app_user_name = current

    changed = auth_service.set_active_instagram_user(app_user_id, instagram_user_id)
    if not changed:
        return jsonify({"error": "Instagram user not found"}), 404

    _sync_active_instagram_user_session(app_user_id)

    instagram_user = auth_service.get_instagram_user(app_user_id, instagram_user_id)
    if not instagram_user:
        return jsonify({"error": "Instagram user not found"}), 404

    return jsonify(
        {
            "active_instagram_user": _sanitize_instagram_user_payload(instagram_user),
            "message": f"Active account set to {instagram_user['name']}",
            "me": _sanitize_me_payload(
                auth_service.build_me_payload(app_user_id, app_user_name)
            ),
        }
    )


@bp.delete("/instagram-users/<instagram_user_id>")
def delete_instagram_user(instagram_user_id: str):
    """Delete one instagram user and its associated persisted scan data."""
    current = _current_app_user()
    if not current:
        return jsonify({"error": "Not logged in"}), 401
    app_user_id, app_user_name = current

    deleted = auth_service.delete_instagram_user(app_user_id, instagram_user_id)
    if not deleted:
        return jsonify({"error": "Instagram user not found"}), 404

    _sync_active_instagram_user_session(app_user_id)

    return jsonify(
        {
            "ok": True,
            "me": _sanitize_me_payload(
                auth_service.build_me_payload(app_user_id, app_user_name)
            ),
        }
    )


@bp.delete("/instagram-users")
def delete_all_instagram_users():
    """Delete all instagram users for current app user (admin page action)."""
    current = _current_app_user()
    if not current:
        return jsonify({"error": "Not logged in"}), 401
    app_user_id, app_user_name = current

    auth_service.delete_all_instagram_users(app_user_id)
    _sync_active_instagram_user_session(app_user_id)
    return jsonify(
        {
            "ok": True,
            "me": _sanitize_me_payload(
                auth_service.build_me_payload(app_user_id, app_user_name)
            ),
        }
    )
