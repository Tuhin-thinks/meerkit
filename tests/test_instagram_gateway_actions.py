import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meerkit.services.instagram_gateway import InstagramGateway, ii


def _profile() -> ii.InstagramProfile:
    return ii.InstagramProfile(
        csrf_token="csrf",
        session_id="session",
        user_id="123",
    )


def _install_mutation(monkeypatch, gateway: InstagramGateway, response: dict) -> int:
    monkeypatch.setattr(gateway, "_pattern_call", lambda **kw: response)
    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.instagram_api_usage_tracker.track_call",
        lambda *, execute, **kwargs: execute(),
    )


def test_unfollow_success_with_destroy_friendship_payload(monkeypatch):
    gateway = InstagramGateway()
    response = {
        "data": {
            "xdt_destroy_friendship": {
                "username": "itz__gayu_",
                "friendship_status": {
                    "following": False,
                    "outgoing_request": False,
                    "followed_by": False,
                    "is_bestie": False,
                },
                "id": "4747076548",
            }
        },
        "extensions": {"server_metadata": {}, "is_final": True},
    }
    _install_mutation(monkeypatch, gateway, response)

    result = gateway.unfollow_user_by_id(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        target_user_id="4747076548",
        target_username="itz__gayu_",
        caller_service="test",
        caller_method="unfollow_action",
    )

    assert result == 1


def test_unfollow_fails_when_still_following(monkeypatch):
    gateway = InstagramGateway()
    response = {
        "data": {
            "xdt_destroy_friendship": {
                "friendship_status": {"following": True, "outgoing_request": False},
                "id": "4747076548",
            }
        }
    }
    _install_mutation(monkeypatch, gateway, response)

    result = gateway.unfollow_user_by_id(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        target_user_id="4747076548",
        target_username="itz__gayu_",
        caller_service="test",
        caller_method="unfollow_action",
    )

    assert result == -1


def test_follow_success_with_create_friendship_payload(monkeypatch):
    gateway = InstagramGateway()
    response = {
        "data": {
            "xdt_create_friendship": {
                "username": "example_user",
                "friendship_status": {
                    "following": True,
                    "outgoing_request": False,
                    "followed_by": False,
                },
                "id": "987654321",
            }
        }
    }
    _install_mutation(monkeypatch, gateway, response)

    result = gateway.follow_user_by_id(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        target_user_id="987654321",
        target_username="example_user",
        caller_service="test",
        caller_method="follow_action",
    )

    assert result == 1


def test_follow_accepts_legacy_status_ok_payload(monkeypatch):
    gateway = InstagramGateway()
    _install_mutation(monkeypatch, gateway, {"status": "ok"})

    result = gateway.follow_user_by_id(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        target_user_id="55",
        target_username="bob",
        caller_service="test",
        caller_method="follow_action",
    )

    assert result == 1
