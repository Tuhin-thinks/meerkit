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


def test_gateway_uses_cache_for_target_user_data(monkeypatch):
    gateway = InstagramGateway()

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.load_gateway_response",
        lambda **kwargs: (
            True,
            {"username": "cached-user", "account_followers_count": 12},
        ),
    )

    def fail_if_called(**kwargs):
        raise AssertionError("Instagram API tracker should not run on cache hit")

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.instagram_api_usage_tracker.track_call",
        fail_if_called,
    )

    result = gateway.get_target_user_data(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        target_user_id="456",
        caller_service="test",
        caller_method="cache_hit",
    )

    assert result["username"] == "cached-user"
    assert result["account_followers_count"] == 12


def test_gateway_fetches_and_stores_on_cache_miss(monkeypatch):
    gateway = InstagramGateway()

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.load_gateway_response",
        lambda **kwargs: (False, None),
    )

    stored_payloads: list[object] = []

    def capture_store(**kwargs):
        stored_payloads.append(kwargs["payload"])
        return "data/cache/app_1/ig_1/instagram_gateway/user_data_fetch/fake.json"

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.store_gateway_response",
        capture_store,
    )

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.ii.get_target_user_data",
        lambda profile, target_user_id: {
            "user_id": target_user_id,
            "username": "fresh-user",
            "account_followers_count": 33,
        },
    )

    def run_tracker(*, execute, **kwargs):
        return execute()

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.instagram_api_usage_tracker.track_call",
        run_tracker,
    )

    result = gateway.get_target_user_data(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        target_user_id="789",
        caller_service="test",
        caller_method="cache_miss",
    )

    assert result["username"] == "fresh-user"
    assert stored_payloads == [result]


def test_gateway_deserializes_relationship_records_from_cache(monkeypatch):
    gateway = InstagramGateway()

    cached_payload = [
        {
            "pk_id": "u1",
            "id": "u1",
            "profile_pic_url": "https://img.example/u1.jpg",
            "username": "alice",
            "full_name": "Alice",
            "is_private": False,
            "fbid_v2": None,
            "profile_pic_id": None,
            "is_verified": True,
        }
    ]

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.load_gateway_response",
        lambda **kwargs: (True, cached_payload),
    )

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.instagram_api_usage_tracker.track_call",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Tracker should not run on relationship cache hit")
        ),
    )

    records = gateway.get_current_following_v2(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        caller_service="test",
        caller_method="relationship_cache_hit",
    )

    assert len(records) == 1
    assert isinstance(records[0], ii.FollowerUserRecord)
    assert records[0].pk_id == "u1"


def test_gateway_force_refresh_bypasses_cache_lookup(monkeypatch):
    gateway = InstagramGateway()

    cache_lookups: list[object] = []

    def capture_lookup(**kwargs):
        cache_lookups.append(kwargs)
        return True, {"username": "stale-user"}

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.load_gateway_response",
        capture_lookup,
    )

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.ii.get_target_user_data",
        lambda profile, target_user_id: {
            "user_id": target_user_id,
            "username": "fresh-user",
        },
    )

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.instagram_api_usage_tracker.track_call",
        lambda *, execute, **kwargs: execute(),
    )

    result = gateway.get_target_user_data(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        target_user_id="789",
        caller_service="test",
        caller_method="force_refresh",
        force_refresh=True,
    )

    assert result["username"] == "fresh-user"
    assert cache_lookups == []


def test_gateway_uses_cache_for_automation_user_lookup(monkeypatch):
    gateway = InstagramGateway()

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.load_gateway_response",
        lambda **kwargs: (True, "1234567890"),
    )

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.instagram_api_usage_tracker.track_call",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Tracker should not run on lookup cache hit")
        ),
    )

    resolved = gateway.resolve_target_user_pk_for_automation(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        profile=_profile(),
        username="target_user",
        caller_service="test",
        caller_method="automation_lookup_cache_hit",
    )

    assert resolved == "1234567890"


def test_follow_action_bypasses_cache(monkeypatch):
    gateway = InstagramGateway()

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.load_gateway_response",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Cache lookup should not run for follow action")
        ),
    )

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.store_gateway_response",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Cache store should not run for follow action")
        ),
    )

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.ii.follow_user_by_id",
        lambda target_user_id, target_username, profile: 1,
    )

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.instagram_api_usage_tracker.track_call",
        lambda *, execute, **kwargs: execute(),
    )

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
