import json
import re
from urllib.parse import quote

from jinja2 import Template

_SESSION_PATTERN = re.compile(r"\{\{session\.(\w+)\}\}")
_RUNTIME_PATTERN = re.compile(r"\{\{runtime\.(\w+)\}\}")

_SCRIPT_TEMPLATE = """\
import pprint
import json
from urllib.parse import quote
import requests

# ==============================================
# Script: {{ display_name }}
# Internal Name: {{ internal_name }}
# ==============================================

url = {{ url | tojson }}

{%- if headers %}

headers = {
{%- for key, value in headers.items() %}
    {{ key | tojson }}: {{ value | tojson }},
{%- endfor %}
}
{%- endif %}

{%- if cookies %}

cookies = {
{%- for key, value in cookies.items() %}
    {{ key | tojson }}: {{ value | tojson }},
{%- endfor %}
}
{%- endif %}

{%- if variables %}

variables = {
{%- for key, value in variables.items() %}
    {{ key | tojson }}: {{ value | tojson }},
{%- endfor %}
}
{%- endif %}

{%- if data %}

data = {
{%- for key, value in data.items() %}
    {{ key | tojson }}: {{ value | tojson }},
{%- endfor %}
}

data_string = "&".join(f"{k}={v}" for k, v in data.items())
{%- endif %}

{%- if http_method.lower() == "get" and not data %}
response = requests.get(url{% if headers %}, headers=headers{% endif %}{% if cookies %}, cookies=cookies{% endif %})
{%- else %}
response = requests.{{ http_method.lower() }}(
    url,
{%- if headers %}    headers=headers,
{%- endif %}{%- if cookies %}    cookies=cookies,
{%- endif %}{%- if data %}    data=data_string,
{%- endif %})
{%- endif %}

print(response.status_code)
if response.status_code == 200:
    pprint.pprint(response.json(), indent=2)
else:
    print("Error: \\n", response.text)

"""

_TEMPLATE = Template(_SCRIPT_TEMPLATE)


def resolve_value(raw: str, session_values: dict, runtime_values: dict) -> str:
    """Replace all {{session.*}} and {{runtime.*}} placeholders.

    Unknown runtime keys are replaced with empty string so the
    generated script is always valid Python.
    """

    def _session_replacer(m: re.Match) -> str:
        return str(session_values.get(m.group(1), ""))

    raw = _SESSION_PATTERN.sub(_session_replacer, raw)

    def _runtime_replacer(m: re.Match) -> str:
        key = m.group(1)
        if key in runtime_values:
            val = runtime_values[key]
            return json.dumps(val) if not isinstance(val, str) else val
        return '""'

    raw = _RUNTIME_PATTERN.sub(_runtime_replacer, raw)
    return raw


def collect_runtime_keys(obj: object) -> set[str]:
    """Recursively extract all {{runtime.*}} placeholder keys from a value."""
    keys: set[str] = set()
    if isinstance(obj, str):
        for m in _RUNTIME_PATTERN.finditer(obj):
            keys.add(m.group(1))
    elif isinstance(obj, dict):
        for v in obj.values():
            keys.update(collect_runtime_keys(v))
    return keys


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
    session_values: dict | None = None,
    runtime_values: dict | None = None,
) -> str:
    session_values = session_values or {}
    runtime_values = runtime_values or {}

    url = resolve_value(url, session_values, runtime_values)

    headers = {
        k: resolve_value(all_headers[k], session_values, runtime_values)
        for k in selected_headers
        if k in all_headers
    }

    cookies = {
        k: resolve_value(all_cookies[k], session_values, runtime_values)
        for k in selected_cookies
        if k in all_cookies
    }

    data: dict[str, str] = {}
    for dk in selected_data:
        if dk == "variables" and selected_variables and all_variables:
            mapped: dict[str, str] = {}
            for vk in selected_variables:
                if vk in all_variables:
                    v = all_variables[vk]
                    raw = json.dumps(v) if not isinstance(v, str) else str(v)
                    mapped[vk] = resolve_value(raw, session_values, runtime_values)
            data["variables"] = quote(json.dumps(mapped))
        elif dk in all_data:
            data[dk] = resolve_value(all_data[dk], session_values, runtime_values)

    variables: dict[str, str] = {}
    if all_variables:
        for vk in selected_variables:
            if vk in all_variables:
                v = all_variables[vk]
                raw = json.dumps(v) if not isinstance(v, str) else str(v)
                variables[vk] = resolve_value(raw, session_values, runtime_values)

    return _TEMPLATE.render(
        internal_name=internal_name,
        display_name=display_name,
        url=url,
        http_method=http_method,
        headers=headers,
        cookies=cookies,
        data=data,
        variables=variables,
    )
