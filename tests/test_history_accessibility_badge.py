from meerkit.routes import history


def test_enrich_diff_marks_account_not_accessible_from_task_error(monkeypatch):
    monkeypatch.setattr(
        history._db_service,
        "get_latest_scanned_profile_ids",
        lambda app_user_id, reference_profile_id: set(),
    )
    monkeypatch.setattr(
        history._db_service,
        "get_target_profile",
        lambda app_user_id, reference_profile_id, target_profile_id: {
            "target_profile_id": target_profile_id,
            "last_error": None,
        },
    )
    monkeypatch.setattr(
        history._db_service,
        "get_latest_prediction_task",
        lambda app_user_id, reference_profile_id, target_profile_id: {
            "status": "error",
            "error": "Could not load this target right now.",
        },
    )
    monkeypatch.setattr(
        history.account_handler,
        "get_alt_followback_assessment_for_target",
        lambda **kwargs: {"is_alt_account_following_you": False},
    )

    diff = {
        "new_followers": [],
        "unfollowers": [
            {
                "pk_id": "123",
                "username": "chatpati_manisha",
            }
        ],
    }

    result = history._enrich_diff_with_alt_followback(
        diff,
        app_user_id="app_user_1",
        reference_profile_id="ig_1",
    )

    assert result is not None
    assert result["unfollowers"][0]["account_not_accessible"] is True


def test_enrich_diff_does_not_mark_accessible_accounts(monkeypatch):
    monkeypatch.setattr(
        history._db_service,
        "get_latest_scanned_profile_ids",
        lambda app_user_id, reference_profile_id: set(),
    )
    monkeypatch.setattr(
        history._db_service,
        "get_target_profile",
        lambda app_user_id, reference_profile_id, target_profile_id: {
            "target_profile_id": target_profile_id,
            "last_error": None,
        },
    )
    monkeypatch.setattr(
        history._db_service,
        "get_latest_prediction_task",
        lambda app_user_id, reference_profile_id, target_profile_id: {
            "status": "completed",
            "error": None,
        },
    )
    monkeypatch.setattr(
        history.account_handler,
        "get_alt_followback_assessment_for_target",
        lambda **kwargs: {"is_alt_account_following_you": False},
    )

    diff = {
        "new_followers": [],
        "unfollowers": [
            {
                "pk_id": "123",
                "username": "normal_user",
            }
        ],
    }

    result = history._enrich_diff_with_alt_followback(
        diff,
        app_user_id="app_user_1",
        reference_profile_id="ig_1",
    )

    assert result is not None
    assert result["unfollowers"][0]["account_not_accessible"] is False
