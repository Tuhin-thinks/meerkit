import json
import logging
import re
from datetime import datetime
from urllib.parse import quote

import curl_to_python
import requests
from meerkit.services.db_service import get_worker_db
from meerkit.services.exceptions import MissingCurlPatternError
from meerkit.services.script_generator import RUNTIME_VARIABLE_KEYS, resolve_value

logger = logging.getLogger(__name__)

SESSION_FIELDS = {"fb_dtsg", "lsd", "jazoest", "csrftoken", "sessionid", "x-csrftoken"}
CONSTANT_FIELDS = {
    "x-ig-app-id", "content-type", "doc_id", "fb_api_req_friendly_name",
    "server_timestamps", "fb_api_caller_class", "x-fb-friendly-name",
}
JUNK_FIELDS = curl_to_python.JUNK_FIELDS


def _now_iso() -> str:
    return datetime.now().isoformat()


def parse_curl(curl_text: str) -> dict:
    url, headers, cookies, data_str = curl_to_python.parse_curl_command(curl_text)
    data = curl_to_python.parse_data(data_str) if data_str else {}
    kept, junk, variables = curl_to_python.build_request_components(data)

    if variables and "id" in variables:
        user_id = str(variables["id"])
        if user_id.isdigit():
            url = re.sub(
                rf'(?<=/){re.escape(user_id)}(?=[/?])',
                '{{runtime.target_user_id}}',
                url,
            )

    http_method = "GET" if not data_str else "POST"

    def _reason(key: str, group: str) -> str:
        if key in SESSION_FIELDS:
            return "session"
        if key in CONSTANT_FIELDS:
            return "constant"
        if key in JUNK_FIELDS:
            return "junk"
        if group == "variables" and key in RUNTIME_VARIABLE_KEYS:
            return "runtime"
        if group == "data" and key in RUNTIME_VARIABLE_KEYS:
            return "runtime"
        return "optional"

    def _selected(key: str, group: str) -> bool:
        reason = _reason(key, group)
        return reason in ("session", "constant", "runtime")

    cookie_fields = [
        {"key": k, "value": v, "selected": _selected(k, "cookies"), "reason": _reason(k, "cookies")}
        for k, v in sorted(cookies.items())
    ]
    header_fields = [
        {"key": k, "value": v, "selected": _selected(k, "headers"), "reason": _reason(k, "headers")}
        for k, v in sorted(headers.items())
    ]

    all_data = {}
    all_data.update(kept)
    all_data.update(junk)
    data_fields = [
        {
            "key": k,
            "value": v,
            "selected": k in kept and _selected(k, "data"),
            "reason": "junk" if k in junk else _reason(k, "data"),
        }
        for k, v in sorted(all_data.items())
    ]

    variable_fields = []
    if variables:
        def _walk(obj, path: str):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _walk(v, f"{path}.{k}" if path else k)
            else:
                var_key = path.split(".")[-1] if "." in path else path
                variable_fields.append({
                    "key": path,
                    "value": json.dumps(obj) if not isinstance(obj, str) else obj,
                    "selected": var_key in RUNTIME_VARIABLE_KEYS,
                    "reason": "runtime" if var_key in RUNTIME_VARIABLE_KEYS else "optional",
                })

        _walk(variables, "")

    suggestions = {
        "cookies": cookie_fields,
        "headers": header_fields,
        "data": data_fields,
        "variables": variable_fields,
    }

    return {
        "url": url,
        "http_method": http_method,
        "cookies": cookies,
        "headers": headers,
        "data": data,
        "variables": variables,
        "suggestions": suggestions,
    }





def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for json_field in ("selected_cookies", "selected_headers", "selected_data", "selected_variables"):
        if isinstance(d.get(json_field), str):
            try:
                d[json_field] = json.loads(d[json_field])
            except (json.JSONDecodeError, TypeError):
                d[json_field] = []
    return d


def store_pattern(
    app_user_id: str,
    internal_name: str,
    display_name: str,
    curl_command: str,
    url: str,
    http_method: str,
    selected_cookies: list[str],
    selected_headers: list[str],
    selected_data: list[str],
    selected_variables: list[str],
    generated_script: str | None = None,
) -> dict:
    db_handler = get_worker_db()
    now = _now_iso()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO api_curl_patterns
               (app_user_id, internal_name, display_name, curl_command, url, http_method,
                selected_cookies, selected_headers, selected_data, selected_variables,
                generated_script, updated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                   (SELECT created_at FROM api_curl_patterns
                    WHERE app_user_id = ? AND internal_name = ?), ?
               ))""",
            (
                app_user_id, internal_name, display_name, curl_command, url, http_method,
                json.dumps(selected_cookies), json.dumps(selected_headers),
                json.dumps(selected_data), json.dumps(selected_variables),
                generated_script, now,
                app_user_id, internal_name, now,
            ),
        )
        conn.commit()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? AND internal_name = ?",
            (app_user_id, internal_name),
        )
        row = _row_to_dict(cursor.fetchone())
        assert row is not None
        return row


def get_pattern(app_user_id: str, internal_name: str) -> dict | None:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? AND internal_name = ?",
            (app_user_id, internal_name),
        )
        return _row_to_dict(cursor.fetchone())


_SESSION_COOKIE_MAP = {
    "csrftoken": "csrftoken",
    "sessionid": "sessionid",
    "ds_user_id": "ds_user_id",
}


def extract_session_from_curl_pattern(app_user_id: str, internal_name: str = "fetch_user_profile_data") -> dict:
    """Extract session values (csrftoken, sessionid, ds_user_id) from a stored curl pattern.

    Parses the stored curl command and extracts cookies/headers that map to session fields.
    Falls back to other patterns if the requested one doesn't exist.
    """
    pattern = get_pattern(app_user_id, internal_name)
    if not pattern:
        alternatives = ["follow_user", "unfollow_user", "fetch_followers_list", "fetch_following_list"]
        for alt in alternatives:
            if alt != internal_name:
                pattern = get_pattern(app_user_id, alt)
                if pattern:
                    break
    if not pattern:
        raise MissingCurlPatternError(
            internal_name=internal_name,
            display_name=internal_name,
        )

    curl_command = str(pattern["curl_command"])
    _, raw_headers, raw_cookies, _ = curl_to_python.parse_curl_command(curl_command)

    session_values: dict[str, str] = {}
    for cookie_key, session_key in _SESSION_COOKIE_MAP.items():
        if cookie_key in raw_cookies:
            session_values[session_key] = raw_cookies[cookie_key]

    if "x-csrftoken" in raw_headers and "csrftoken" not in session_values:
        session_values["csrftoken"] = raw_headers["x-csrftoken"]

    return session_values


def list_patterns(app_user_id: str) -> list[dict]:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? ORDER BY internal_name",
            (app_user_id,),
        )
        return [r for r in (_row_to_dict(r) for r in cursor.fetchall()) if r is not None]


def update_pattern(app_user_id: str, internal_name: str, **updates) -> dict | None:
    existing = get_pattern(app_user_id, internal_name)
    if not existing:
        return None

    allowed = {
        "display_name", "curl_command", "url", "http_method",
        "selected_cookies", "selected_headers", "selected_data",
        "selected_variables", "generated_script", "is_active",
    }
    to_set = {k: v for k, v in updates.items() if k in allowed}
    if not to_set:
        return existing

    to_set["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in to_set)
    values = list(to_set.values())

    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE api_curl_patterns SET {set_clause} WHERE app_user_id = ? AND internal_name = ?",
            (*values, app_user_id, internal_name),
        )
        conn.commit()

    return get_pattern(app_user_id, internal_name)


def delete_pattern(app_user_id: str, internal_name: str) -> bool:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM api_curl_patterns WHERE app_user_id = ? AND internal_name = ?",
            (app_user_id, internal_name),
        )
        conn.commit()
        return cursor.rowcount > 0


def build_request(
    app_user_id: str,
    internal_name: str,
    session_values: dict,
    runtime_values: dict | None = None,
) -> tuple[str, dict, dict, str | None]:
    runtime_values = runtime_values or {}
    pattern = get_pattern(app_user_id, internal_name)
    if not pattern:
        raise MissingCurlPatternError(
            internal_name=internal_name,
            display_name=internal_name,
        )

    selected_cookies: list[str] = pattern.get("selected_cookies", [])
    selected_headers: list[str] = pattern.get("selected_headers", [])
    selected_data: list[str] = pattern.get("selected_data", [])
    selected_variables: list[str] = pattern.get("selected_variables", [])

    url = resolve_value(str(pattern["url"]), session_values, runtime_values)

    headers = {}
    raw_curl_url, raw_headers, raw_cookies, raw_data_str = curl_to_python.parse_curl_command(
        pattern["curl_command"]
    )
    for k in selected_headers:
        if k in raw_headers:
            headers[k] = resolve_value(raw_headers[k], session_values, runtime_values)

    cookies = {}
    for k in selected_cookies:
        if k in raw_cookies:
            cookies[k] = resolve_value(raw_cookies[k], session_values, runtime_values)

    data_string = None
    if selected_data and raw_data_str:
        raw_data = curl_to_python.parse_data(raw_data_str)
        kept, _, variables = curl_to_python.build_request_components(raw_data)

        data_dict = {}
        for dk in selected_data:
            if dk == "variables" and selected_variables and variables:
                mapped_vars = {}
                for vk in selected_variables:
                    if vk in variables:
                        if vk in RUNTIME_VARIABLE_KEYS and vk in runtime_values:
                            mapped_vars[vk] = str(runtime_values[vk])
                        elif vk == "id" and "target_user_id" in runtime_values:
                            mapped_vars[vk] = str(runtime_values["target_user_id"])
                        else:
                            mapped_vars[vk] = resolve_value(
                                json.dumps(variables[vk]) if not isinstance(variables[vk], str) else str(variables[vk]),
                                session_values, runtime_values,
                            )
                data_dict["variables"] = quote(json.dumps(mapped_vars))
            elif dk in raw_data:
                data_dict[dk] = resolve_value(raw_data[dk], session_values, runtime_values)

        if data_dict:
            data_string = "&".join(f"{k}={v}" for k, v in data_dict.items())

    return url, headers, cookies, data_string


def test_pattern(
    app_user_id: str,
    internal_name: str,
    session_values: dict,
    runtime_values: dict | None = None,
) -> dict:
    url, headers, cookies, data_string = build_request(
        app_user_id, internal_name, session_values, runtime_values,
    )
    pattern = get_pattern(app_user_id, internal_name)
    http_method = (pattern or {}).get("http_method", "POST")

    start = datetime.now()
    try:
        if http_method.upper() == "GET":
            resp = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        else:
            resp = requests.post(url, headers=headers, cookies=cookies, data=data_string, timeout=30)
        elapsed_ms = int((datetime.now() - start).total_seconds() * 1000)
        return {
            "status_code": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "response_text": resp.text[:10000],
            "success": resp.status_code < 500,
        }
    except requests.RequestException as e:
        elapsed_ms = int((datetime.now() - start).total_seconds() * 1000)
        return {
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "response_text": str(e),
            "success": False,
        }


def get_preference(app_user_id: str, key: str) -> dict | None:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT preference_value FROM user_preferences WHERE app_user_id = ? AND preference_key = ?",
            (app_user_id, key),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None


def set_preference(app_user_id: str, key: str, value: dict) -> dict:
    db_handler = get_worker_db()
    now = _now_iso()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO user_preferences
               (app_user_id, preference_key, preference_value, updated_at)
               VALUES (?, ?, ?, ?)""",
            (app_user_id, key, json.dumps(value), now),
        )
        conn.commit()
    return value
