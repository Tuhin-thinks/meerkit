import logging
from typing import cast

from flask import Blueprint, jsonify, request

from meerkit.routes import get_active_context
from meerkit.services.curl_pattern_service import (
    delete_pattern,
    get_pattern,
    get_preference,
    list_patterns,
    parse_curl,
    set_preference,
    store_pattern,
    test_pattern,
    update_pattern,
)
from meerkit.services.script_generator import (
    collect_runtime_keys,
    generate_script,
)
from curl_to_python import parse_curl_command as _curl_parse, parse_data as _curl_parse_data, build_request_components as _curl_build_components

logger = logging.getLogger(__name__)

bp = Blueprint("curl_patterns", __name__, url_prefix="/api/curl-patterns")

_INTERNAL_NAMES = frozenset({
    "fetch_user_profile_data",
    "fetch_followers_list",
    "fetch_following_list",
    "follow_user",
    "unfollow_user",
    "search_user",
})


def _get_app_and_ig_user() -> tuple[str, dict]:
    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    app_user_id, context = get_active_context(instagram_user_id)
    if not app_user_id:
        body, status = context
        raise _api_error(body["error"], status, body["code"])
    return app_user_id, cast(dict, context)


class _ApiError(Exception):
    def __init__(self, message: str, status_code: int, code: str) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code


def _api_error(message: str, status_code: int, code: str) -> _ApiError:
    return _ApiError(message, status_code, code)


@bp.errorhandler(_ApiError)
def _handle_api_error(error: _ApiError):
    return jsonify({"error": error.message, "code": error.code}), error.status_code


@bp.post("/parse")
def handle_parse():
    body = request.get_json(silent=True) or {}
    curl_text = body.get("curl_text", "")
    if not curl_text.strip():
        return jsonify({"error": "curl_text is required", "code": "validation_error"}), 400
    try:
        result = parse_curl(curl_text)
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": f"Failed to parse curl: {exc}", "code": "parse_error"}), 400


@bp.post("/<internal_name>")
def handle_store(internal_name: str):
    if internal_name not in _INTERNAL_NAMES:
        return jsonify({"error": f"Unknown internal name: {internal_name}", "code": "validation_error"}), 400
    app_user_id, _ = _get_app_and_ig_user()
    body = request.get_json(silent=True) or {}
    required = ("display_name", "curl_command", "url", "http_method")
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}", "code": "validation_error"}), 400

    pattern = store_pattern(
        app_user_id=app_user_id,
        internal_name=internal_name,
        display_name=body["display_name"],
        curl_command=body["curl_command"],
        url=body["url"],
        http_method=body.get("http_method", "POST"),
        selected_cookies=body.get("selected_cookies", []),
        selected_headers=body.get("selected_headers", []),
        selected_data=body.get("selected_data", []),
        selected_variables=body.get("selected_variables", []),
        generated_script=body.get("generated_script"),
    )
    return jsonify(pattern), 200


@bp.get("/<internal_name>")
def handle_get(internal_name: str):
    app_user_id, _ = _get_app_and_ig_user()
    pattern = get_pattern(app_user_id, internal_name)
    if not pattern:
        return jsonify(None), 200
    return jsonify(pattern), 200


@bp.get("")
def handle_list():
    app_user_id, _ = _get_app_and_ig_user()
    patterns = list_patterns(app_user_id)
    return jsonify(patterns), 200


@bp.patch("/<internal_name>")
def handle_update(internal_name: str):
    app_user_id, _ = _get_app_and_ig_user()
    body = request.get_json(silent=True) or {}
    allowed = {
        "display_name", "curl_command", "url", "http_method",
        "selected_cookies", "selected_headers", "selected_data",
        "selected_variables", "generated_script", "is_active",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return jsonify({"error": "No valid fields to update", "code": "validation_error"}), 400
    result = update_pattern(app_user_id, internal_name, **updates)
    if not result:
        return jsonify({"error": "Pattern not found", "code": "not_found"}), 404
    return jsonify(result), 200


@bp.delete("/<internal_name>")
def handle_delete(internal_name: str):
    app_user_id, _ = _get_app_and_ig_user()
    deleted = delete_pattern(app_user_id, internal_name)
    return jsonify({"ok": deleted}), 200


@bp.post("/<internal_name>/test")
def handle_test(internal_name: str):
    app_user_id, instagram_user = _get_app_and_ig_user()
    runtime_values = request.get_json(silent=True) or {}
    session_values = {
        "csrftoken": instagram_user.get("csrf_token", ""),
        "sessionid": instagram_user.get("session_id", ""),
        "ds_user_id": instagram_user.get("user_id", ""),
    }

    result = test_pattern(
        app_user_id=app_user_id,
        internal_name=internal_name,
        session_values=session_values,
        runtime_values=runtime_values,
    )
    return jsonify(result), 200


@bp.post("/<internal_name>/generate")
def handle_generate(internal_name: str):
    app_user_id, instagram_user = _get_app_and_ig_user()
    pattern = get_pattern(app_user_id, internal_name)
    if not pattern:
        return jsonify({"error": "Pattern not found", "code": "not_found"}), 404

    session_values: dict[str, str] = {
        "csrftoken": instagram_user.get("csrf_token", ""),
        "sessionid": instagram_user.get("session_id", ""),
        "ds_user_id": instagram_user.get("user_id", ""),
    }

    raw_url, raw_headers, raw_cookies, raw_data_str = _curl_parse(
        str(pattern["curl_command"])
    )
    raw_data = _curl_parse_data(raw_data_str) if raw_data_str else {}
    _, _, raw_variables = _curl_build_components(raw_data)

    runtime_keys = collect_runtime_keys(raw_cookies) | collect_runtime_keys(raw_headers) | collect_runtime_keys(raw_data) | collect_runtime_keys(raw_url) | collect_runtime_keys(raw_variables or {})

    user_id = instagram_user.get("user_id", "")
    runtime_values: dict[str, object] = {}
    for rk in runtime_keys:
        if rk in ("id", "target_user_id", "ds_user_id"):
            runtime_values[rk] = user_id
        elif rk == "username":
            runtime_values[rk] = instagram_user.get("username", user_id)
        elif rk == "enable_integrity_filters":
            runtime_values[rk] = True
        elif rk == "first":
            runtime_values[rk] = 50
        else:
            runtime_values[rk] = ""

    script = generate_script(
        internal_name=str(pattern["internal_name"]),
        display_name=str(pattern["display_name"]),
        url=str(pattern["url"]),
        http_method=str(pattern["http_method"]),
        selected_cookies=pattern.get("selected_cookies") or [],
        selected_headers=pattern.get("selected_headers") or [],
        selected_data=pattern.get("selected_data") or [],
        selected_variables=pattern.get("selected_variables") or [],
        all_cookies=raw_cookies,
        all_headers=raw_headers,
        all_data=raw_data,
        all_variables=raw_variables,
        session_values=session_values,
        runtime_values=runtime_values,
    )
    return jsonify({"script": script}), 200


@bp.get("/preferences/<key>")
def handle_get_preference(key: str):
    app_user_id, _ = _get_app_and_ig_user()
    logger.info("GET preference key=%s app_user_id=%s", key, app_user_id)
    value = get_preference(app_user_id, key)
    logger.info("GET preference result=%s", value)
    if value is None:
        return jsonify(None), 200
    return jsonify(value), 200


@bp.put("/preferences/<key>")
def handle_set_preference(key: str):
    app_user_id, _ = _get_app_and_ig_user()
    body = request.get_json(silent=True) or {}
    logger.info("SET preference key=%s app_user_id=%s body=%s", key, app_user_id, body)
    set_preference(app_user_id, key, body)
    return jsonify(body), 200
