from meerkit.app import create_app


def _mock_context(monkeypatch):
    monkeypatch.setattr(
        "meerkit.routes.automation.get_active_context",
        lambda instagram_user_id_override=None: (
            "app_test_user",
            {
                "instagram_user_id": "ig_123",
                "csrf_token": "csrf",
                "session_id": "session",
                "user_id": "viewer_1",
            },
        ),
    )


def test_list_alternative_account_links(monkeypatch):
    app = create_app()
    client = app.test_client()
    _mock_context(monkeypatch)

    monkeypatch.setattr(
        "meerkit.routes.automation.list_alt_links",
        lambda **kwargs: [
            {
                "link_id": "link_1",
                "primary_identity_key": "main_user",
                "alt_identity_key": "alt_user",
            }
        ],
    )

    response = client.get("/api/automation/alternative-account-links")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert payload["entries"][0]["primary_identity_key"] == "main_user"


def test_add_alternative_account_links(monkeypatch):
    app = create_app()
    client = app.test_client()
    _mock_context(monkeypatch)

    monkeypatch.setattr(
        "meerkit.routes.automation.add_alt_account_links",
        lambda **kwargs: {
            "primary_identity_key": "main_user",
            "added": 1,
            "skipped_invalid": 0,
            "entries": [
                {
                    "link_id": "link_1",
                    "primary_identity_key": "main_user",
                    "alt_identity_key": "alt_user",
                }
            ],
            "total": 1,
        },
    )

    response = client.post(
        "/api/automation/alternative-account-links",
        json={
            "primary_account": "main_user",
            "alternative_accounts": ["alt_user"],
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["added"] == 1
    assert payload["primary_identity_key"] == "main_user"


def test_delete_alternative_account_link(monkeypatch):
    app = create_app()
    client = app.test_client()
    _mock_context(monkeypatch)

    monkeypatch.setattr(
        "meerkit.routes.automation.remove_alt_link",
        lambda **kwargs: True,
    )

    response = client.delete(
        "/api/automation/alternative-account-links/main_user/alt_user"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["removed"] is True
    assert payload["primary_identity_key"] == "main_user"
    assert payload["alt_identity_key"] == "alt_user"
