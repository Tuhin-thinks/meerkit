import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meerkit.db.db_handler import SqliteDBHandler
from meerkit.services import curl_pattern_service
from meerkit.services.curl_pattern_service import (
    _build_request_parts,
    project_pattern,
    store_pattern,
    update_pattern,
)

APP_USER_ID = "app_1"
REFERENCE_PROFILE_ID = "5165665016"

_FOLLOWING_CURL = """curl --url 'https://www.instagram.com/api/v1/friendships/5165665016/following/?count=12&max_id=12' \\
  -H 'accept: */*' \\
  -b 'ds_user_id=5165665016; sessionid=sid; csrftoken=csrf' \\
  -H 'x-csrftoken: csrf'"""


def _seed_following_pattern(tmp_path):
    db_handler = SqliteDBHandler(db_path=tmp_path / "test.sqlite")
    curl_pattern_service.get_worker_db = lambda db_path=None: db_handler
    store_pattern(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
        display_name="Fetch Following List",
        curl_command=_FOLLOWING_CURL,
        url="https://www.instagram.com/api/v1/friendships/5165665016/following/?count=12&max_id=12",
        http_method="GET",
        selected_cookies=["ds_user_id", "sessionid", "csrftoken"],
        selected_headers=["accept", "x-csrftoken"],
        selected_data=[],
        selected_variables=[],
    )
    return db_handler


def test_build_request_omits_max_id_when_no_runtime_value(tmp_path):
    _seed_following_pattern(tmp_path)
    parts = _build_request_parts(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
        session_values={
            "ds_user_id": "5165665016",
            "sessionid": "sid",
            "csrftoken": "csrf",
        },
    )
    assert parts["url"] == (
        "https://www.instagram.com/api/v1/friendships/5165665016/following/?count=12"
    )
    params = {p["name"]: p for p in parts["query_params"]}
    assert params["count"]["kind"] == "constant"
    assert params["max_id"]["kind"] == "runtime"
    assert params["max_id"]["omitted"] is True


def test_build_request_injects_runtime_max_id(tmp_path):
    _seed_following_pattern(tmp_path)
    parts = _build_request_parts(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
        session_values={
            "ds_user_id": "5165665016",
            "sessionid": "sid",
            "csrftoken": "csrf",
        },
        runtime_values={"max_id": "CURSOR_123"},
    )
    assert parts["url"] == (
        "https://www.instagram.com/api/v1/friendships/5165665016/following/"
        "?count=12&max_id=CURSOR_123"
    )


def test_project_pattern_returns_default_cases(tmp_path):
    _seed_following_pattern(tmp_path)
    result = project_pattern(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
    )
    assert result["runtime_keys"] == ["max_id"]
    assert len(result["cases"]) == 2
    page1, page2 = result["cases"]
    assert page1["url"].endswith("?count=12")
    assert page2["runtime_values"] == {"max_id": "<next_max_id>"}
    assert page2["url"].endswith("?count=12&max_id=<next_max_id>")
    assert page2["query_params"][1]["name"] == "max_id"


def test_project_pattern_accepts_custom_cases(tmp_path):
    _seed_following_pattern(tmp_path)
    result = project_pattern(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
        cases=[{"max_id": "CURSOR_ABC"}, {}],
    )
    assert result["cases"][0]["url"].endswith("max_id=CURSOR_ABC")
    assert result["cases"][1]["url"].endswith("?count=12")


def test_projection_route(tmp_path, monkeypatch):
    from meerkit.app import create_app

    _seed_following_pattern(tmp_path)
    monkeypatch.setattr(
        "meerkit.routes.curl_patterns._get_app_and_ig_user",
        lambda: (APP_USER_ID, REFERENCE_PROFILE_ID, {}),
    )
    client = create_app().test_client()

    response = client.post("/api/curl-patterns/fetch_following_list/project", json={})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["runtime_keys"] == ["max_id"]
    assert payload["cases"][1]["url"].endswith("max_id=<next_max_id>")


_PROFILE_CURL = """curl --url 'https://www.instagram.com/api/graphql' \\
  -H 'accept: */*' \\
  -H 'content-type: application/x-www-form-urlencoded' \\
  -b 'ds_user_id=5165665016; sessionid=sid; csrftoken=csrf' \\
  -H 'x-csrftoken: csrf' \\
  --data-raw 'doc_id=38611279431804694&variables=%7B%22enable_integrity_filters%22%3Atrue%2C%22id%22%3A%225165665016%22%7D'"""


def test_project_pattern_detects_templated_path_runtime_key(tmp_path):
    _seed_following_pattern(tmp_path)
    update_pattern(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
        url="https://www.instagram.com/api/v1/friendships/{{runtime.target_user_id}}/following/?count=12&max_id={{runtime.max_id}}",
    )
    result = project_pattern(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
    )
    assert set(result["runtime_keys"]) == {"max_id", "target_user_id"}
    assert result["defaults"]["target_user_id"] == "5165665016"
    assert result["cases"][0]["url"] == (
        "https://www.instagram.com/api/v1/friendships/5165665016/following/?count=12"
    )
    assert result["cases"][1]["url"] == (
        "https://www.instagram.com/api/v1/friendships/5165665016/following/"
        "?count=12&max_id=<next_max_id>"
    )


def test_default_runtime_values_prevents_empty_user_id(tmp_path):
    _seed_following_pattern(tmp_path)
    update_pattern(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
        url="https://www.instagram.com/api/v1/friendships/{{runtime.target_user_id}}/following/?count=12&max_id={{runtime.max_id}}",
    )
    session_values = {
        "ds_user_id": "5165665016",
        "sessionid": "sid",
        "csrftoken": "csrf",
    }
    pattern = curl_pattern_service.get_pattern(
        APP_USER_ID, REFERENCE_PROFILE_ID, "fetch_following_list"
    )
    defaults = curl_pattern_service.default_runtime_values(pattern, session_values)
    assert defaults["target_user_id"] == "5165665016"

    parts = _build_request_parts(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_following_list",
        session_values=session_values,
        runtime_values=defaults,
    )
    assert parts["url"] == (
        "https://www.instagram.com/api/v1/friendships/5165665016/following/?count=12"
    )
    assert '""' not in parts["url"]


def test_project_pattern_post_body_preserves_variable_types(tmp_path):
    db_handler = SqliteDBHandler(db_path=tmp_path / "test.sqlite")
    curl_pattern_service.get_worker_db = lambda db_path=None: db_handler
    store_pattern(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_user_profile_data",
        display_name="Fetch User Profile Data",
        curl_command=_PROFILE_CURL,
        url="https://www.instagram.com/api/graphql",
        http_method="POST",
        selected_cookies=["ds_user_id", "sessionid", "csrftoken"],
        selected_headers=["accept", "content-type", "x-csrftoken"],
        selected_data=["doc_id", "variables"],
        selected_variables=["enable_integrity_filters", "id"],
    )

    result = project_pattern(
        app_user_id=APP_USER_ID,
        reference_profile_id=REFERENCE_PROFILE_ID,
        internal_name="fetch_user_profile_data",
    )

    assert set(result["runtime_keys"]) == {"enable_integrity_filters", "id"}
    variables_field = next(
        f for f in result["cases"][0]["body_fields"] if f["name"] == "variables"
    )
    assert variables_field["value"].startswith(
        '{"enable_integrity_filters": true, "id": "5165665016"'
    )
    nested = {f["name"]: f for f in variables_field["nested"]}
    assert nested["enable_integrity_filters"]["value"] == "true"
    assert nested["id"]["value"] == "5165665016"
