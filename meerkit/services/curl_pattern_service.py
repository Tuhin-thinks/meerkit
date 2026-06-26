import json
import logging
import re
from datetime import datetime
from urllib.parse import parse_qs, quote, urlencode, urlparse

import curl_to_python
import requests
from meerkit.config import app_user_db
from meerkit.services.db_service import get_worker_db
from meerkit.services.exceptions import MissingCurlPatternError

logger = logging.getLogger(__name__)

SESSION_FIELDS = {"fb_dtsg", "lsd", "jazoest", "csrftoken", "sessionid", "x-csrftoken"}
CONSTANT_FIELDS = {
    "x-ig-app-id", "content-type", "doc_id", "fb_api_req_friendly_name",
    "server_timestamps", "fb_api_caller_class", "x-fb-friendly-name",
}
RUNTIME_VARIABLE_KEYS = {"id", "target_user_id", "first", "after", "query", "username"}
JUNK_FIELDS = curl_to_python.JUNK_FIELDS


def _now_iso() -> str:
    return datetime.now().isoformat()


def parse_curl(curl_text: str) -> dict:
    url, headers, cookies, data_str = curl_to_python.parse_curl_command(curl_text)
    data = curl_to_python.parse_data(data_str) if data_str else {}
    kept, junk, variables = curl_to_python.build_request_components(data)

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


def _map_session_value(template: str, session_values: dict) -> str:
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        return str(session_values.get(key, m.group(0)))
    return re.sub(r"\{\{session\.(\w+)\}\}", _replacer, template)


def _map_runtime_value(template: str, runtime_values: dict) -> str:
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        if key in runtime_values:
            val = runtime_values[key]
            return json.dumps(val) if not isinstance(val, str) else val
        return m.group(0)
    return re.sub(r"\{\{runtime\.(\w+)\}\}", _replacer, template)


def _apply_placeholders(value: str, session_values: dict, runtime_values: dict) -> str:
    value = _map_session_value(value, session_values)
    value = _map_runtime_value(value, runtime_values)
    return value


def generate_script(
    internal_name: str,
    display_name: str,
    url: str,
    http_method: str,
    selected_cookies: list[str],
    selected_headers: list[str],
    selected_data: list[str],
    selected_variables: list[str],
    all_cookies: dict[str, str],
    all_headers: dict[str, str],
    all_data: dict[str, str],
    all_variables: dict | None,
) -> str:
    lines = []
    lines.append("import json")
    lines.append("from urllib.parse import quote")
    lines.append("import requests")
    lines.append("")
    lines.append("#" + "=" * 46)
    lines.append(f"# Script: {display_name}")
    lines.append(f"# Internal Name: {internal_name}")
    lines.append("#" + "=" * 46)
    lines.append("")

    lines.append(f'url = "{url}"')
    lines.append("")

    if selected_headers:
        lines.append("headers = {")
        for k in selected_headers:
            if k in all_headers:
                v = all_headers[k]
                if k in SESSION_FIELDS:
                    lines.append(f'    "{k}": "{{{{session.{k}}}}}",')
                else:
                    lines.append(f'    "{k}": "{v}",')
        lines.append("}")
        lines.append("")

    if selected_cookies:
        lines.append("cookies = {")
        for k in selected_cookies:
            if k in all_cookies:
                v = all_cookies[k]
                if k in SESSION_FIELDS:
                    lines.append(f'    "{k}": "{{{{session.{k}}}}}",')
                else:
                    lines.append(f'    "{k}": "{v}",')
        lines.append("}")
        lines.append("")

    has_variables = selected_variables and all_variables
    if has_variables:
        lines.append("variables = {")
        for vk in selected_variables:
            lines.append(f'    "{vk}": {{{{runtime.{vk}}}}},')
        lines.append("}")
        lines.append("")

    if selected_data:
        lines.append("data = {")
        for dk in selected_data:
            if dk in all_data:
                dv = all_data[dk]
                if dk in SESSION_FIELDS:
                    lines.append(f'    "{dk}": "{{{{session.{dk}}}}}",')
                elif dk in CONSTANT_FIELDS:
                    lines.append(f'    "{dk}": "{dv}",')
                elif dk in RUNTIME_VARIABLE_KEYS:
                    lines.append(f'    "{dk}": "{{{{runtime.{dk}}}}}",')
                elif dk == "variables":
                    lines.append(f'    "{dk}": quote(json.dumps(variables)),')
                else:
                    lines.append(f'    "{dk}": "{dv}",')
        lines.append("}")
        lines.append("")

    if selected_data:
        lines.append('data_string = "&".join(f"{k}={v}" for k, v in data.items())')
        lines.append("")

    method = http_method.lower()
    if method == "get" and not selected_data:
        lines.append(f"response = requests.get(url, headers=headers, cookies=cookies)")
    else:
        lines.append(f"response = requests.{method}(url, headers=headers, cookies=cookies, data=data_string)")

    lines.append("")
    lines.append("print(response.status_code)")
    lines.append("print(response.text)")

    return "\n".join(lines)


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
                generated_script, now, now,
                app_user_id, internal_name, now,
            ),
        )
        conn.commit()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? AND internal_name = ?",
            (app_user_id, internal_name),
        )
        return _row_to_dict(cursor.fetchone())


def get_pattern(app_user_id: str, internal_name: str) -> dict | None:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? AND internal_name = ?",
            (app_user_id, internal_name),
        )
        return _row_to_dict(cursor.fetchone())


def list_patterns(app_user_id: str) -> list[dict]:
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM api_curl_patterns WHERE app_user_id = ? ORDER BY internal_name",
            (app_user_id,),
        )
        return [_row_to_dict(r) for r in cursor.fetchall()]


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
            display_name=pattern.get("display_name") if pattern else internal_name,
        )

    selected_cookies: list[str] = pattern.get("selected_cookies", [])
    selected_headers: list[str] = pattern.get("selected_headers", [])
    selected_data: list[str] = pattern.get("selected_data", [])
    selected_variables: list[str] = pattern.get("selected_variables", [])

    url = _apply_placeholders(str(pattern["url"]), session_values, runtime_values)

    headers = {}
    raw_curl_url, raw_headers, raw_cookies, raw_data_str = curl_to_python.parse_curl_command(
        pattern["curl_command"]
    )
    for k in selected_headers:
        if k in raw_headers:
            headers[k] = _apply_placeholders(raw_headers[k], session_values, runtime_values)

    cookies = {}
    for k in selected_cookies:
        if k in raw_cookies:
            cookies[k] = _apply_placeholders(raw_cookies[k], session_values, runtime_values)

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
                        mapped_vars[vk] = _apply_placeholders(
                            json.dumps(variables[vk]) if not isinstance(variables[vk], str) else str(variables[vk]),
                            session_values, runtime_values,
                        )
                data_dict["variables"] = quote(json.dumps(mapped_vars))
            elif dk in raw_data:
                data_dict[dk] = _apply_placeholders(raw_data[dk], session_values, runtime_values)

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


def refresh_session_tokens(csrf_token: str, session_id: str, user_id: str) -> dict:
    cookies = {
        "csrftoken": csrf_token,
        "sessionid": session_id,
        "ds_user_id": user_id,
    }
    try:
        resp = requests.get(
            "https://www.instagram.com/",
            cookies=cookies,
            headers={
                "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            },
            timeout=30,
        )
        html = resp.text
    except requests.RequestException as e:
        logger.exception("Failed to fetch Instagram homepage for token refresh")
        raise MissingCurlPatternError(
            internal_name="_session_refresh",
            display_name="Session Token Refresh",
            message=f"Could not reach Instagram: {e}",
        ) from e

    fb_dtsg = ""
    m = re.search(r'"fb_dtsg"[^:]*:\s*"([^"]+)"', html)
    if m:
        fb_dtsg = m.group(1)

    lsd = ""
    m = re.search(r'"LSD"[^:]*:\s*"([^"]+)"', html)
    if m:
        lsd = m.group(1)

    jazoest = ""
    m = re.search(r'name="jazoest"[^>]*value="([^"]+)"', html)
    if m:
        jazoest = m.group(1)
    if not jazoest:
        m = re.search(r'"jazoest"[^:]*:\s*"([^"]+)"', html)
        if m:
            jazoest = m.group(1)

    if not fb_dtsg:
        logger.warning("Could not extract fb_dtsg from Instagram homepage")

    return {
        "fb_dtsg": fb_dtsg,
        "lsd": lsd,
        "jazoest": jazoest,
    }
