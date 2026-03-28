from pathlib import Path

from meerkit.app import create_app


def test_cache_efficiency_requires_login(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.automation.get_active_context",
        lambda instagram_user_id=None: (None, ({"error": "Not logged in"}, 401)),
    )

    response = client.get("/api/automation/cache-efficiency")

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["error"] == "Not logged in"


def test_cache_efficiency_returns_metrics(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.automation.get_active_context",
        lambda instagram_user_id=None: (
            "app_1",
            {"instagram_user_id": "ig_1"},
        ),
    )

    monkeypatch.setattr(
        "meerkit.routes.automation.db_service.get_instagram_api_usage_summary",
        lambda **kwargs: {
            "generated_at": "2026-03-22T10:00:00",
            "window_start_24h": "2026-03-21T10:00:00",
            "totals": {"all_time_count": 10, "last_24h_count": 4},
            "accounts": [
                {
                    "instagram_user_id": "ig_1",
                    "all_time_count": 10,
                    "last_24h_count": 4,
                    "categories": [
                        {
                            "category": "followers_discovery",
                            "all_time_count": 3,
                            "last_24h_count": 1,
                            "callers": [],
                        },
                        {
                            "category": "followers_discovery_cache_hit",
                            "all_time_count": 5,
                            "last_24h_count": 2,
                            "callers": [],
                        },
                    ],
                }
            ],
        },
    )

    monkeypatch.setattr(
        "meerkit.routes.automation._cache_size_summary",
        lambda cache_scope_dir: {"cache_size_bytes": 2048, "cache_file_count": 4},
    )

    response = client.get("/api/automation/cache-efficiency")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["instagram_user_id"] == "ig_1"
    assert payload["all_time"]["cache_hits"] == 5
    assert payload["all_time"]["api_calls"] == 3
    assert payload["all_time"]["total_reads"] == 8
    assert payload["cache_size"]["cache_size_bytes"] == 2048


def test_cache_size_returns_scope_size(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.automation.get_active_context",
        lambda instagram_user_id=None: (
            "app_1",
            {"instagram_user_id": "ig_1"},
        ),
    )

    monkeypatch.setattr(
        "meerkit.routes.automation._cache_size_summary",
        lambda cache_scope_dir: {"cache_size_bytes": 4096, "cache_file_count": 8},
    )

    response = client.get("/api/automation/cache-size")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["instagram_user_id"] == "ig_1"
    assert payload["cache_size_bytes"] == 4096
    assert payload["cache_file_count"] == 8


def test_cache_size_summary_counts_files(tmp_path: Path):
    from meerkit.routes.automation import _cache_size_summary

    scope = tmp_path / "cache_scope"
    (scope / "a").mkdir(parents=True)
    (scope / "a" / "one.json").write_text("abcd", encoding="utf-8")
    (scope / "a" / "two.json").write_text("123456", encoding="utf-8")

    payload = _cache_size_summary(scope)

    assert payload["cache_file_count"] == 2
    assert payload["cache_size_bytes"] == 10
