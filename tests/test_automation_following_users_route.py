from types import SimpleNamespace

from meerkit.app import create_app


def _mock_context(monkeypatch):
    monkeypatch.setattr(
        "meerkit.routes.automation.get_active_context",
        lambda instagram_user_id=None: (
            "app_1",
            {
                "instagram_user_id": "ig_1",
                "csrf_token": "csrf",
                "session_id": "session",
                "user_id": "viewer_1",
            },
        ),
    )


def _record(pk_id: str, username: str) -> SimpleNamespace:
    return SimpleNamespace(
        pk_id=pk_id,
        username=username,
        full_name=username,
        is_private=False,
        profile_pic_url=f"https://img/{pk_id}.jpg",
    )


def test_following_users_prefers_metadata_follows_you(monkeypatch):
    app = create_app()
    client = app.test_client()
    _mock_context(monkeypatch)

    monkeypatch.setattr(
        "meerkit.routes.automation._build_profile",
        lambda app_user_id, reference_profile_id: object(),
    )
    monkeypatch.setattr(
        "meerkit.routes.automation.instagram_gateway.get_current_following_v2",
        lambda **kwargs: [_record("u1", "one"), _record("u2", "two")],
    )
    monkeypatch.setattr(
        "meerkit.routes.automation.instagram_gateway.get_current_followers_v2",
        lambda **kwargs: [_record("u2", "two")],
    )
    monkeypatch.setattr(
        "meerkit.routes.automation._load_following_user_counts_bulk",
        lambda **kwargs: {
            "u1": {
                "follower_count": 11,
                "following_count": 7,
                "being_followed_by_account": True,
            },
            "u2": {
                "follower_count": 5,
                "following_count": 9,
                "being_followed_by_account": False,
            },
        },
    )

    response = client.get("/api/automation/following-users")

    assert response.status_code == 200
    payload = response.get_json()
    users_by_id = {row["user_id"]: row for row in payload["users"]}
    assert users_by_id["u1"]["follows_you"] is True
    assert users_by_id["u2"]["follows_you"] is False


def test_following_users_falls_back_to_membership_when_metadata_missing(monkeypatch):
    app = create_app()
    client = app.test_client()
    _mock_context(monkeypatch)

    monkeypatch.setattr(
        "meerkit.routes.automation._build_profile",
        lambda app_user_id, reference_profile_id: object(),
    )
    monkeypatch.setattr(
        "meerkit.routes.automation.instagram_gateway.get_current_following_v2",
        lambda **kwargs: [_record("u1", "one"), _record("u2", "two")],
    )
    monkeypatch.setattr(
        "meerkit.routes.automation.instagram_gateway.get_current_followers_v2",
        lambda **kwargs: [_record("u2", "two")],
    )
    monkeypatch.setattr(
        "meerkit.routes.automation._load_following_user_counts_bulk",
        lambda **kwargs: {
            "u1": {
                "follower_count": 11,
                "following_count": 7,
                "being_followed_by_account": True,
            },
            "u2": {
                "follower_count": 5,
                "following_count": 9,
                "being_followed_by_account": None,
            },
        },
    )

    response = client.get("/api/automation/following-users")

    assert response.status_code == 200
    payload = response.get_json()
    users_by_id = {row["user_id"]: row for row in payload["users"]}
    assert users_by_id["u1"]["follows_you"] is True
    assert users_by_id["u2"]["follows_you"] is True
