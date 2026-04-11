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


def test_live_deactivated_map_marks_empty_and_fetch_errors(monkeypatch):
    upserts: list[dict] = []

    def capture_upsert(**kwargs):
        upserts.append(kwargs)
        return kwargs

    monkeypatch.setattr(
        diff_accessibility.db_service,
        "get_target_profile",
        lambda **kwargs: {
            "fetch_status": "partial",
            "username": kwargs["target_profile_id"],
        },
    )
    monkeypatch.setattr(
        diff_accessibility.db_service,
        "upsert_target_profile",
        capture_upsert,
    )

    def fake_followers(**kwargs):
        if kwargs["target_user_id"] == "broken":
            raise ii.RelationshipFetchError("edge_followed_by", "target unavailable")
        return []

    monkeypatch.setattr(
        diff_accessibility.instagram_gateway,
        "get_target_followers_v2",
        fake_followers,
    )
    monkeypatch.setattr(
        diff_accessibility.instagram_gateway,
        "get_target_following_v2",
        lambda **kwargs: [],
    )

    result = diff_accessibility.live_deactivated_map(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        profile=ii.InstagramProfile("csrf", "session", "ig_1"),
        target_profile_ids={"empty", "broken"},
        fetch_at_max=10,
        caller_service="tests",
        caller_method="test_live_deactivated_map_marks_empty_and_fetch_errors",
    )

    assert result == {"broken": True, "empty": True}
    assert {item["target_profile_id"] for item in upserts} == {"broken", "empty"}
    assert all(item["is_deactivated"] is True for item in upserts)


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
