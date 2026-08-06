from meerkit.services import automation_service


def _patch_common_db(monkeypatch):
    monkeypatch.setattr(
        automation_service.db_service,
        "get_safelist_identity_keys",
        lambda app_user_id, reference_profile_id, list_type: set(),
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "create_automation_action",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "insert_automation_action_items",
        lambda rows: None,
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "update_automation_action",
        lambda action_id, **kwargs: None,
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_deactivated_map",
        lambda app_user_id, reference_profile_id, target_profile_ids: {},
    )


def test_prepare_batch_follow_returns_selected_items(monkeypatch):
    _patch_common_db(monkeypatch)

    result = automation_service.prepare_batch_follow(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        candidate_lines=["known_user"],
        do_not_follow_lines=[],
        config={"max_follow_count": 50},
    )

    assert result["selected_count"] == 1
    assert result["selected_items"] == [
        {
            "raw_input": "known_user",
            "normalized_username": "known_user",
            "normalized_user_id": None,
            "display_username": "known_user",
        }
    ]


def test_prepare_batch_unfollow_excludes_when_linked_alt_follows_you(monkeypatch):
    _patch_common_db(monkeypatch)
    monkeypatch.setattr(
        automation_service.db_service,
        "get_alt_identity_keys_map_for_primary_keys",
        lambda app_user_id, reference_profile_id, primary_identity_keys: {
            "main_user": {"alt_1"}
        },
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_relationship_ids",
        lambda app_user_id, reference_profile_id, target_profile_id, relationship_type: (
            {"alt_1"}
            if target_profile_id == reference_profile_id
            and relationship_type == "followers"
            else set()
        ),
    )

    result = automation_service.prepare_batch_unfollow(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        instagram_user=None,
        candidate_lines=["main_user"],
        never_unfollow_lines=[],
        config={"max_unfollow_count": 50},
        use_auto_discovery=False,
    )

    assert result["selected_count"] == 0
    assert result["excluded_count"] == 1
    assert (
        result["excluded_items"][0]["exclusion_reason"]
        == "alternative_account_follows_you"
    )


def test_prepare_batch_unfollow_excludes_when_alt_follow_detected_from_metadata(
    monkeypatch,
):
    _patch_common_db(monkeypatch)
    monkeypatch.setattr(
        automation_service.db_service,
        "get_alt_identity_keys_map_for_primary_keys",
        lambda app_user_id, reference_profile_id, primary_identity_keys: {
            "100": {"200"}
        },
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_relationship_ids",
        lambda app_user_id, reference_profile_id, target_profile_id, relationship_type: (
            set()
        ),
    )
    monkeypatch.setattr(
        automation_service,
        "_get_cached_profile",
        lambda app_user_id, reference_profile_id: object(),
    )
    monkeypatch.setattr(
        automation_service.instagram_gateway,
        "get_target_user_data",
        lambda **kwargs: {
            "being_followed_by_account": kwargs["target_user_id"] == "200"
        },
    )

    result = automation_service.prepare_batch_unfollow(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        instagram_user={"instagram_user_id": "ig_1"},
        candidate_lines=["100"],
        never_unfollow_lines=[],
        config={"max_unfollow_count": 50},
        use_auto_discovery=False,
    )

    assert result["selected_count"] == 0
    assert result["excluded_count"] == 1
    assert (
        result["excluded_items"][0]["exclusion_reason"]
        == "alternative_account_follows_you"
    )


def test_prepare_batch_unfollow_fallbacks_when_metadata_fetch_fails(monkeypatch):
    _patch_common_db(monkeypatch)
    monkeypatch.setattr(
        automation_service.db_service,
        "get_alt_identity_keys_map_for_primary_keys",
        lambda app_user_id, reference_profile_id, primary_identity_keys: {
            "100": {"200"}
        },
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_relationship_ids",
        lambda app_user_id, reference_profile_id, target_profile_id, relationship_type: (
            set()
        ),
    )
    monkeypatch.setattr(
        automation_service,
        "_get_cached_profile",
        lambda app_user_id, reference_profile_id: object(),
    )

    def _raise_fetch_error(**kwargs):
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(
        automation_service.instagram_gateway,
        "get_target_user_data",
        _raise_fetch_error,
    )

    result = automation_service.prepare_batch_unfollow(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        instagram_user={"instagram_user_id": "ig_1"},
        candidate_lines=["100"],
        never_unfollow_lines=[],
        config={"max_unfollow_count": 50},
        use_auto_discovery=False,
    )

    assert result["selected_count"] == 1
    assert result["excluded_count"] == 0


def test_prepare_batch_unfollow_excludes_direct_follower_when_skip_mutual(monkeypatch):
    _patch_common_db(monkeypatch)
    monkeypatch.setattr(
        automation_service.db_service,
        "get_alt_identity_keys_map_for_primary_keys",
        lambda app_user_id, reference_profile_id, primary_identity_keys: {},
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_relationship_ids",
        lambda app_user_id, reference_profile_id, target_profile_id, relationship_type: (
            set()
        ),
    )
    monkeypatch.setattr(
        automation_service,
        "_get_cached_profile",
        lambda app_user_id, reference_profile_id: object(),
    )
    monkeypatch.setattr(
        automation_service.instagram_gateway,
        "get_target_user_data",
        lambda **kwargs: {"being_followed_by_account": True},
    )

    result = automation_service.prepare_batch_unfollow(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        instagram_user={"instagram_user_id": "ig_1"},
        candidate_lines=["100"],
        never_unfollow_lines=[],
        config={"max_unfollow_count": 50, "skip_mutual": True},
        use_auto_discovery=False,
    )

    assert result["selected_count"] == 0
    assert result["excluded_count"] == 1
    assert result["excluded_items"][0]["exclusion_reason"] == "already_follows_you"


def test_prepare_batch_unfollow_excludes_deactivated_accounts(monkeypatch):
    _patch_common_db(monkeypatch)
    monkeypatch.setattr(
        automation_service.db_service,
        "get_alt_identity_keys_map_for_primary_keys",
        lambda app_user_id, reference_profile_id, primary_identity_keys: {},
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_relationship_ids",
        lambda app_user_id, reference_profile_id, target_profile_id, relationship_type: (
            set()
        ),
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_deactivated_map",
        lambda app_user_id, reference_profile_id, target_profile_ids: {"100": True},
    )

    result = automation_service.prepare_batch_unfollow(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        instagram_user=None,
        candidate_lines=["100"],
        never_unfollow_lines=[],
        config={"max_unfollow_count": 50},
        use_auto_discovery=False,
    )

    assert result["selected_count"] == 0
    assert result["excluded_count"] == 1
    assert result["excluded_items"][0]["exclusion_reason"] == "account_not_accessible"


def test_prepare_batch_unfollow_prefers_deactivated_exclusion_over_mutual(monkeypatch):
    _patch_common_db(monkeypatch)
    monkeypatch.setattr(
        automation_service.db_service,
        "get_alt_identity_keys_map_for_primary_keys",
        lambda app_user_id, reference_profile_id, primary_identity_keys: {},
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_relationship_ids",
        lambda app_user_id, reference_profile_id, target_profile_id, relationship_type: (
            set()
        ),
    )
    monkeypatch.setattr(
        automation_service.db_service,
        "get_target_profile_deactivated_map",
        lambda app_user_id, reference_profile_id, target_profile_ids: {"100": True},
    )
    monkeypatch.setattr(
        automation_service,
        "_get_cached_profile",
        lambda app_user_id, reference_profile_id: object(),
    )
    monkeypatch.setattr(
        automation_service.instagram_gateway,
        "get_target_user_data",
        lambda **kwargs: {"being_followed_by_account": True},
    )

    result = automation_service.prepare_batch_unfollow(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        instagram_user={"instagram_user_id": "ig_1"},
        candidate_lines=["100"],
        never_unfollow_lines=[],
        config={"max_unfollow_count": 50, "skip_mutual": True},
        use_auto_discovery=False,
    )

    assert result["selected_count"] == 0
    assert result["excluded_count"] == 1
    assert result["excluded_items"][0]["exclusion_reason"] == "account_not_accessible"
