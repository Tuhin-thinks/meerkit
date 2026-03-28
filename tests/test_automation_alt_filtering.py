from meerkit.services import automation_service


def test_prepare_batch_unfollow_excludes_when_linked_alt_follows_you(monkeypatch):
    monkeypatch.setattr(
        automation_service.db_service,
        "get_safelist_identity_keys",
        lambda app_user_id, reference_profile_id, list_type: set(),
    )
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
