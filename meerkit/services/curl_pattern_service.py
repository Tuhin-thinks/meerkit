import json
import logging
import re
from datetime import datetime
from urllib.parse import quote

import curl_to_python
import requests
from meerkit.services.db_service import get_worker_db
from meerkit.services.exceptions import MissingCurlPatternError
from meerkit.services.script_generator import (
    RUNTIME_VARIABLE_KEYS,
    collect_runtime_keys,
    resolve_value,
)

logger = logging.getLogger(__name__)

SESSION_FIELDS = {"fb_dtsg", "lsd", "jazoest", "csrftoken", "sessionid", "x-csrftoken"}
CONSTANT_FIELDS = {
    "x-ig-app-id", "content-type", "doc_id", "fb_api_req_friendly_name",
    "server_timestamps", "fb_api_caller_class", "x-fb-friendly-name",
}
JUNK_FIELDS = curl_to_python.JUNK_FIELDS


def _now_iso() -> str:
    return datetime.now().isoformat()


def _classify_field(name: str, value: str) -> str:
    """Classify a URL query param or body field.

    Returns "runtime" for keys that vary per call (max_id, first, after, ...),
    "session" for fields whose value carries a session placeholder, and
    "constant" for everything else.
    """
    if name in RUNTIME_VARIABLE_KEYS or "{{runtime." in value:
        return "runtime"
    if "{{session." in value:
        return "session"
    return "constant"


def _templateize_url(url: str) -> str:
    """Replace runtime query params and friendships path ids with placeholders.

    This turns a pasted curl URL into a template the engine can vary per call,
    without the user hand-writing {{runtime.*}} placeholders.
    """
    if "/friendships/" in url:
        url = re.sub(
            r"(/friendships/)(\d+)(/)",
            r"\g<1>{{runtime.target_user_id}}\3",
            url,
        )
    base, sep, query = url.partition("?")
    if not sep:
        return url
    parts: list[str] = []
    for chunk in query.split("&"):
        if not chunk:
            continue
        name, _, value = chunk.partition("=")
        if _classify_field(name, value) == "runtime":
            parts.append(f"{name}={{{{runtime.{name}}}}}")
        else:
            parts.append(chunk)
    return base + "?" + "&".join(parts)


def parse_curl(curl_text: str) -> dict:
    url, headers, cookies, data_str = curl_to_python.parse_curl_command(curl_text)
    data = curl_to_python.parse_data(data_str) if data_str else {}
    kept, junk, variables = curl_to_python.build_request_components(data)

    url = _templateize_url(url)

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
    reference_profile_id: str,
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
               (app_user_id, reference_profile_id, internal_name, display_name,
                curl_command, url, http_method,
                selected_cookies, selected_headers, selected_data, selected_variables,
                generated_script, updated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                   (SELECT created_at FROM api_curl_patterns
                    WHERE app_user_id = ? AND reference_profile_id = ? AND internal_name = ?), ?
               ))""",
            (
                app_user_id, reference_profile_id, internal_name, display_name,
                curl_command, url, http_method,
                json.dumps(selected_cookies), json.dumps(selected_headers),
                json.dumps(selected_data), json.dumps(selected_variables),
                generated_script, now,
                app_user_id, reference_profile_id, internal_name, now,
            ),
        )
        conn.commit()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? AND reference_profile_id = ? AND internal_name = ?",
            (app_user_id, reference_profile_id, internal_name),
        )
        row = _row_to_dict(cursor.fetchone())
        assert row is not None
        return row


def get_pattern(
    app_user_id: str, reference_profile_id: str, internal_name: str,
) -> dict | None:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? AND reference_profile_id = ? AND internal_name = ?",
            (app_user_id, reference_profile_id, internal_name),
        )
        return _row_to_dict(cursor.fetchone())


_SESSION_COOKIE_MAP = {
    "csrftoken": "csrftoken",
    "sessionid": "sessionid",
    "ds_user_id": "ds_user_id",
}


def extract_session_from_curl_pattern(
    app_user_id: str,
    reference_profile_id: str,
    internal_name: str = "fetch_user_profile_data",
) -> dict:
    """Extract session values (csrftoken, sessionid, ds_user_id) from a stored curl pattern.

    Parses the stored curl command and extracts cookies/headers that map to session fields.
    Falls back to other patterns if the requested one doesn't exist.
    """
    pattern = get_pattern(app_user_id, reference_profile_id, internal_name)
    if not pattern:
        alternatives = ["follow_user", "unfollow_user", "fetch_followers_list", "fetch_following_list"]
        for alt in alternatives:
            if alt != internal_name:
                pattern = get_pattern(app_user_id, reference_profile_id, alt)
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


def list_patterns(app_user_id: str, reference_profile_id: str) -> list[dict]:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? AND reference_profile_id = ? ORDER BY internal_name",
            (app_user_id, reference_profile_id),
        )
        return [r for r in (_row_to_dict(r) for r in cursor.fetchall()) if r is not None]


def update_pattern(
    app_user_id: str, reference_profile_id: str, internal_name: str, **updates,
) -> dict | None:
    existing = get_pattern(app_user_id, reference_profile_id, internal_name)
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
            f"UPDATE api_curl_patterns SET {set_clause} WHERE app_user_id = ? AND reference_profile_id = ? AND internal_name = ?",
            (*values, app_user_id, reference_profile_id, internal_name),
        )
        conn.commit()

    return get_pattern(app_user_id, reference_profile_id, internal_name)


def delete_pattern(app_user_id: str, reference_profile_id: str, internal_name: str) -> bool:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM api_curl_patterns WHERE app_user_id = ? AND reference_profile_id = ? AND internal_name = ?",
            (app_user_id, reference_profile_id, internal_name),
        )
        conn.commit()
        return cursor.rowcount > 0


def _split_url_query(url: str) -> tuple[str, list[dict]]:
    """Split a URL into its base and a list of query params.

    Each param is a dict: {"name", "value", "kind"}.
    """
    base, sep, query = url.partition("?")
    params: list[dict] = []
    if sep:
        for chunk in query.split("&"):
            if not chunk:
                continue
            name, _, value = chunk.partition("=")
            params.append(
                {"name": name, "value": value, "kind": _classify_field(name, value)}
            )
    return base, params


def _substitute_friendships_path_id(url: str, runtime_values: dict) -> str:
    """Replace a literal numeric id in a /friendships/<id>/ path segment.

    Keeps legacy stored templates (which had the id baked in) working alongside
    newly parsed templates that already carry {{runtime.target_user_id}}.
    """
    target_user_id = runtime_values.get("target_user_id")
    if target_user_id is not None and "/friendships/" in url:
        url = re.sub(
            r"(/friendships/)(\d+)(/)",
            rf"\g<1>{target_user_id}\3",
            url,
        )
    return url


def _resolve_query_params(
    base_url: str,
    params: list[dict],
    session_values: dict,
    runtime_values: dict,
) -> tuple[str, list[dict]]:
    """Substitute session/runtime values into query params and build the final URL.

    Runtime params without a value are omitted entirely (e.g. max_id on page 1).
    """
    resolved: list[dict] = []
    for param in params:
        entry = {
            "name": param["name"],
            "kind": param["kind"],
            "value": param["value"],
            "omitted": False,
        }
        if param["kind"] == "runtime":
            value = runtime_values.get(param["name"])
            if value is None or str(value) == "":
                entry["value"] = ""
                entry["omitted"] = True
            else:
                entry["value"] = str(value)
        else:
            entry["value"] = resolve_value(
                param["value"], session_values, runtime_values
            )
        resolved.append(entry)

    included = [r for r in resolved if not r["omitted"]]
    query_string = "&".join(f'{r["name"]}={r["value"]}' for r in included)
    final_url = base_url + (f"?{query_string}" if query_string else "")
    return final_url, resolved


def _build_body_fields(
    selected_data: list[str],
    selected_variables: list[str],
    raw_data: dict,
    variables: dict | None,
    session_values: dict,
    runtime_values: dict,
) -> tuple[str | None, list[dict]]:
    """Build the form-encoded body string plus a per-field breakdown.

    Runtime fields without a value are omitted. The "variables" field nests its
    own per-key breakdown.
    """
    data_dict: dict[str, str] = {}
    body_fields: list[dict] = []

    for data_key in selected_data:
        if data_key == "variables" and selected_variables and variables:
            mapped_vars: dict[str, object] = {}
            nested: list[dict] = []
            for var_key in selected_variables:
                if var_key not in variables:
                    continue
                kind = _classify_field(var_key, "")
                entry = {"name": var_key, "kind": kind, "value": "", "omitted": False}
                if kind == "runtime":
                    value = runtime_values.get(var_key)
                    if value is None and var_key == "id":
                        value = runtime_values.get("target_user_id")
                    if value is None or str(value) == "":
                        entry["omitted"] = True
                    else:
                        if isinstance(value, bool):
                            value_str = json.dumps(value)
                            mapped_vars[var_key] = value
                        else:
                            value_str = str(value)
                            mapped_vars[var_key] = value_str
                        entry["value"] = value_str
                else:
                    raw_value = variables[var_key]
                    raw_str = (
                        json.dumps(raw_value)
                        if not isinstance(raw_value, str)
                        else raw_value
                    )
                    resolved_value = resolve_value(
                        raw_str, session_values, runtime_values
                    )
                    mapped_vars[var_key] = resolved_value
                    entry["value"] = resolved_value
                nested.append(entry)

            data_dict["variables"] = quote(json.dumps(mapped_vars))
            body_fields.append(
                {
                    "name": "variables",
                    "kind": "runtime",
                    "value": json.dumps(mapped_vars),
                    "omitted": False,
                    "nested": nested,
                }
            )
        elif data_key in raw_data:
            kind = _classify_field(data_key, raw_data[data_key])
            entry = {"name": data_key, "kind": kind, "value": "", "omitted": False}
            if kind == "runtime":
                value = runtime_values.get(data_key)
                if value is None or str(value) == "":
                    entry["omitted"] = True
                else:
                    value_str = str(value)
                    data_dict[data_key] = value_str
                    entry["value"] = value_str
            else:
                resolved_value = resolve_value(
                    raw_data[data_key], session_values, runtime_values
                )
                data_dict[data_key] = resolved_value
                entry["value"] = resolved_value
            body_fields.append(entry)

    data_string = None
    if data_dict:
        data_string = "&".join(f"{k}={v}" for k, v in data_dict.items())
    return data_string, body_fields


def _build_request_parts(
    app_user_id: str,
    reference_profile_id: str,
    internal_name: str,
    session_values: dict,
    runtime_values: dict | None = None,
) -> dict:
    """Build the exact outgoing request and its per-field breakdown.

    Returns a dict with url, headers, cookies, data_string, query_params and
    body_fields. This is the single engine shared by build_request, the test
    endpoint and the projection endpoint.
    """
    runtime_values = runtime_values or {}
    pattern = get_pattern(app_user_id, reference_profile_id, internal_name)
    if not pattern:
        raise MissingCurlPatternError(
            internal_name=internal_name,
            display_name=internal_name,
        )

    selected_cookies: list[str] = pattern.get("selected_cookies", [])
    selected_headers: list[str] = pattern.get("selected_headers", [])
    selected_data: list[str] = pattern.get("selected_data", [])
    selected_variables: list[str] = pattern.get("selected_variables", [])

    raw_url = str(pattern["url"])
    base_url, params = _split_url_query(raw_url)
    base_url = resolve_value(base_url, session_values, runtime_values)
    base_url = _substitute_friendships_path_id(base_url, runtime_values)
    url, resolved_params = _resolve_query_params(
        base_url, params, session_values, runtime_values
    )

    headers: dict[str, str] = {}
    raw_curl_url, raw_headers, raw_cookies, raw_data_str = curl_to_python.parse_curl_command(
        pattern["curl_command"]
    )
    for k in selected_headers:
        if k in raw_headers:
            headers[k] = resolve_value(raw_headers[k], session_values, runtime_values)

    cookies: dict[str, str] = {}
    for k in selected_cookies:
        if k in raw_cookies:
            cookies[k] = resolve_value(raw_cookies[k], session_values, runtime_values)

    data_string = None
    body_fields: list[dict] = []
    if selected_data and raw_data_str:
        raw_data = curl_to_python.parse_data(raw_data_str)
        _, _, variables = curl_to_python.build_request_components(raw_data)
        data_string, body_fields = _build_body_fields(
            selected_data,
            selected_variables,
            raw_data,
            variables,
            session_values,
            runtime_values,
        )

    return {
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "data_string": data_string,
        "query_params": resolved_params,
        "body_fields": body_fields,
    }


def build_request(
    app_user_id: str,
    reference_profile_id: str,
    internal_name: str,
    session_values: dict,
    runtime_values: dict | None = None,
) -> tuple[str, dict, dict, str | None]:
    parts = _build_request_parts(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        internal_name=internal_name,
        session_values=session_values,
        runtime_values=runtime_values,
    )
    return parts["url"], parts["headers"], parts["cookies"], parts["data_string"]


def test_pattern(
    app_user_id: str,
    reference_profile_id: str,
    internal_name: str,
    session_values: dict,
    runtime_values: dict | None = None,
) -> dict:
    url, headers, cookies, data_string = build_request(
        app_user_id, reference_profile_id, internal_name, session_values, runtime_values,
    )
    pattern = get_pattern(app_user_id, reference_profile_id, internal_name)
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


def _collect_runtime_keys_from_pattern(pattern: dict) -> set[str]:
    """Collect all runtime keys a pattern can vary, including literal query params."""
    keys: set[str] = set()
    raw_url, raw_headers, raw_cookies, raw_data_str = curl_to_python.parse_curl_command(
        str(pattern["curl_command"])
    )
    raw_data = curl_to_python.parse_data(raw_data_str) if raw_data_str else {}
    _, _, raw_variables = curl_to_python.build_request_components(raw_data)
    keys |= collect_runtime_keys(raw_url)
    keys |= collect_runtime_keys(raw_headers)
    keys |= collect_runtime_keys(raw_cookies)
    keys |= collect_runtime_keys(raw_data)
    keys |= collect_runtime_keys(raw_variables or {})
    keys |= collect_runtime_keys(str(pattern["url"]))
    _, params = _split_url_query(str(pattern["url"]))
    for param in params:
        if param["kind"] == "runtime":
            keys.add(param["name"])
    for data_key, data_value in raw_data.items():
        if _classify_field(data_key, str(data_value)) == "runtime":
            keys.add(data_key)
    for var_key, var_value in (raw_variables or {}).items():
        if _classify_field(var_key, str(var_value)) == "runtime":
            keys.add(var_key)
    return keys


def _default_runtime_values(runtime_keys: set[str], session_values: dict) -> dict:
    """Build sensible default runtime values for a projection, mirroring handle_generate."""
    user_id = str(session_values.get("ds_user_id") or "")
    defaults: dict[str, object] = {}
    for key in sorted(runtime_keys):
        if key in ("id", "target_user_id", "ds_user_id"):
            defaults[key] = user_id
        elif key == "username":
            defaults[key] = user_id
        elif key == "enable_integrity_filters":
            defaults[key] = True
        elif key == "first":
            defaults[key] = 50
        else:
            defaults[key] = ""
    return defaults


def default_runtime_values(pattern: dict, session_values: dict) -> dict:
    """Compute default runtime values for a pattern from its detected runtime keys."""
    runtime_keys = _collect_runtime_keys_from_pattern(pattern)
    return _default_runtime_values(runtime_keys, session_values)


def _default_projection_cases(runtime_keys: set[str], defaults: dict) -> list[dict]:
    """Build default projection cases (e.g. page 1 vs subsequent page)."""
    cases: list[dict] = [{}]
    if "max_id" in runtime_keys:
        cases.append({"max_id": "<next_max_id>"})
    if "after" in runtime_keys:
        cases.append({"after": "<end_cursor>"})
    if (
        len(cases) == 1
        and defaults.get("target_user_id")
        and "username" in runtime_keys
    ):
        cases.append({"username": "<target_username>"})
    return cases


def project_pattern(
    app_user_id: str,
    reference_profile_id: str,
    internal_name: str,
    cases: list[dict] | None = None,
) -> dict:
    """Project the exact outgoing request(s) for a pattern.

    Returns the final URL, query-param breakdown and body breakdown for each
    requested runtime-values case (or sensible defaults when none are given).
    """
    pattern = get_pattern(app_user_id, reference_profile_id, internal_name)
    if not pattern:
        raise MissingCurlPatternError(
            internal_name=internal_name,
            display_name=internal_name,
        )

    session_values = extract_session_from_curl_pattern(
        app_user_id, reference_profile_id, internal_name
    )
    runtime_keys = _collect_runtime_keys_from_pattern(pattern)
    defaults = default_runtime_values(pattern, session_values)

    if not cases:
        cases = _default_projection_cases(runtime_keys, defaults)

    projected_cases: list[dict] = []
    for case_values in cases:
        merged = dict(defaults)
        merged.update(case_values or {})
        parts = _build_request_parts(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            internal_name=internal_name,
            session_values=session_values,
            runtime_values=merged,
        )
        projected_cases.append(
            {
                "runtime_values": {
                    k: v for k, v in merged.items() if v is not None and str(v) != ""
                },
                "url": parts["url"],
                "headers": parts["headers"],
                "cookies": parts["cookies"],
                "query_params": parts["query_params"],
                "body": parts["data_string"],
                "body_fields": parts["body_fields"],
            }
        )

    return {
        "internal_name": str(pattern["internal_name"]),
        "display_name": str(pattern["display_name"]),
        "http_method": str(pattern.get("http_method", "POST")),
        "runtime_keys": sorted(runtime_keys),
        "defaults": {
            k: v for k, v in defaults.items() if v is not None and str(v) != ""
        },
        "cases": projected_cases,
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
