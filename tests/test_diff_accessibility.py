import requests

import insta_interface as ii
from meerkit.services import diff_accessibility


def _record(pk_id: str, username: str) -> ii.FollowerUserRecord:
    return ii.FollowerUserRecord(
        pk_id=pk_id,
        id=pk_id,
        profile_pic_url=f"https://img.example/{username}.jpg",
        username=username,
        full_name=username.title(),
        is_private=False,
        fbid_v2=None,
        profile_pic_id=None,
        is_verified=False,
    )


def test_seed_target_profiles_from_diff_payload_creates_missing_rows(monkeypatch):
    upserts: list[dict] = []

    def capture_upsert(**kwargs):
        upserts.append(kwargs)
        return kwargs

    monkeypatch.setattr(
        diff_accessibility.db_service,
        "get_target_profile",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        diff_accessibility.db_service,
        "upsert_target_profile",
        capture_upsert,
    )

    seeded = diff_accessibility.seed_target_profiles_from_diff_payload(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        payload={
            "new_followers": [
                {
                    "pk_id": "101",
                    "username": "alice",
                    "full_name": "Alice",
                    "is_private": False,
                    "is_verified": False,
                    "profile_pic_url": "https://img.example/alice.jpg",
                }
            ],
            "unfollowers": [
                {
                    "pk_id": "202",
                    "username": "bob",
                    "full_name": "Bob",
                    "is_private": True,
                    "is_verified": True,
                    "profile_pic_url": "https://img.example/bob.jpg",
                }
            ],
        },
    )

    assert seeded == 2
    assert {item["target_profile_id"] for item in upserts} == {"101", "202"}
    assert {item["fetch_status"] for item in upserts} == {"partial"}


def test_reactivate_returned_accounts_updates_known_deactivated_rows(monkeypatch):
    existing_rows = {
        "101": {
            "target_profile_id": "101",
            "username": "alice_old",
            "full_name": "Alice Old",
            "is_deactivated": True,
            "fetch_status": "partial",
        },
        "202": {
            "target_profile_id": "202",
            "username": "bob",
            "full_name": "Bob",
            "is_deactivated": False,
            "fetch_status": "partial",
        },
    }
    upserts: list[dict] = []

    def capture_upsert(**kwargs):
        upserts.append(kwargs)
        return kwargs

    monkeypatch.setattr(
        diff_accessibility.db_service,
        "get_target_profile",
        lambda **kwargs: existing_rows.get(kwargs["target_profile_id"]),
    )
    monkeypatch.setattr(
        diff_accessibility.db_service,
        "upsert_target_profile",
        capture_upsert,
    )

    reactivated = diff_accessibility.reactivate_returned_accounts(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        new_followers=[_record("101", "alice_new"), _record("202", "bob")],
    )

    assert reactivated == {"101"}
    assert len(upserts) == 1
    assert upserts[0]["target_profile_id"] == "101"
    assert upserts[0]["is_deactivated"] is False
    assert upserts[0]["username"] == "alice_new"
    assert upserts[0]["last_error"] is None


def _existing_row(target_profile_id: str, **overrides) -> dict:
    row = {
        "target_profile_id": target_profile_id,
        "username": target_profile_id,
        "full_name": None,
        "fetch_status": "partial",
        "is_deactivated": None,
        "metadata_fetched_at": None,
        "relationships_fetched_at": None,
        "last_error": None,
        "update_date": None,
    }
    row.update(overrides)
    return row


def _live_map(
    monkeypatch,
    existing_rows: dict[str, dict],
    *,
    fake_user_data=None,
    fake_raise=None,
    max_checks: int = 50,
) -> tuple[dict[str, bool], set[str]]:
    upserts: list[dict] = []

    def capture_upsert(**kwargs):
        upserts.append(kwargs)
        return kwargs

    monkeypatch.setattr(
        diff_accessibility.db_service,
        "get_target_profile",
        lambda **kwargs: existing_rows.get(kwargs["target_profile_id"]),
    )
    monkeypatch.setattr(
        diff_accessibility.db_service,
        "upsert_target_profile",
        capture_upsert,
    )

    def fake_user_data_call(**kwargs):
        if fake_raise is not None:
            raise fake_raise
        return fake_user_data

    monkeypatch.setattr(
        diff_accessibility.instagram_gateway,
        "get_target_user_data",
        fake_user_data_call,
    )

    deactivated_map, checked_ids = diff_accessibility.live_deactivated_map(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        profile=ii.InstagramProfile("csrf", "session", "ig_1"),
        target_profile_ids=set(existing_rows),
        caller_service="tests",
        caller_method="test_live_deactivated_map",
        max_checks=max_checks,
    )
    assert checked_ids <= set(existing_rows)
    return deactivated_map, checked_ids


def test_live_deactivated_map_user_object_means_active(monkeypatch):
    user_data = {
        "id": "101",
        "pk": "101",
        "username": "alice",
        "full_name": "Alice",
        "is_private": False,
        "is_verified": True,
        "follower_count": 42,
        "following_count": 7,
        "friendship_status": {
            "following": True,
            "followed_by": True,
            "blocking": False,
        },
    }
    deactivated_map, checked_ids = _live_map(
        monkeypatch,
        {"101": _existing_row("101")},
        fake_user_data=user_data,
    )

    assert deactivated_map == {"101": False}
    assert checked_ids == {"101"}


def test_live_deactivated_map_errors_payload_means_not_accessible(monkeypatch):
    deactivated_map, checked_ids = _live_map(
        monkeypatch,
        {"202": _existing_row("202")},
        fake_user_data={"errors": [{"message": "field_exception", "code": 16}]},
    )

    assert deactivated_map == {"202": True}
    assert checked_ids == {"202"}


def test_live_deactivated_map_transport_error_keeps_existing_decision(monkeypatch):
    existing = _existing_row(
        "202",
        is_deactivated=False,
        fetch_status="live",
        update_date="2020-01-01T00:00:00.000000",
    )
    deactivated_map, checked_ids = _live_map(
        monkeypatch,
        {"202": existing},
        fake_raise=requests.exceptions.RequestException("rate limited"),
    )

    assert deactivated_map == {}
    assert checked_ids == {"202"}


def test_live_deactivated_map_reuses_fresh_stored_decision(monkeypatch):
    from datetime import datetime

    existing = _existing_row(
        "303",
        is_deactivated=True,
        fetch_status="live",
        update_date=datetime.now().isoformat(),
    )

    deactivated_map, checked_ids = _live_map(
        monkeypatch,
        {"303": existing},
        fake_user_data={"id": "303", "username": "should_not_be_called"},
    )

    assert deactivated_map == {"303": True}
    assert checked_ids == set()


def test_live_deactivated_map_stale_decision_forces_live_check(monkeypatch):
    existing = _existing_row(
        "303",
        is_deactivated=True,
        fetch_status="live",
        update_date="2020-01-01T00:00:00.000000",
    )

    deactivated_map, checked_ids = _live_map(
        monkeypatch,
        {"303": existing},
        fake_user_data={"id": "303", "username": "back_online"},
    )

    assert deactivated_map == {"303": False}
    assert checked_ids == {"303"}


def test_live_deactivated_map_respects_budget(monkeypatch):
    deactivated_map, checked_ids = _live_map(
        monkeypatch,
        {"a": _existing_row("a"), "b": _existing_row("b")},
        fake_user_data={"id": "x", "username": "x"},
        max_checks=1,
    )

    assert len(checked_ids) == 1
    assert len(deactivated_map) == 1


def test_apply_account_accessibility_to_unfollowers_only_updates_unfollowers():
    payload = {
        "new_followers": [
            {
                "pk_id": "101",
                "username": "alice",
            }
        ],
        "unfollowers": [
            {
                "pk_id": "202",
                "username": "bob",
            }
        ],
    }

    updated = diff_accessibility.apply_account_accessibility_to_unfollowers(
        payload,
        {"101": True, "202": True},
    )

    assert updated == 1
    assert "account_not_accessible" not in payload["new_followers"][0]
    assert payload["unfollowers"][0]["account_not_accessible"] is True
