from datetime import datetime, timedelta

import insta_interface as ii
from backend.services import account_handler, prediction_runner


def test_extract_user_summary_includes_new_metadata_fields():
    payload = {
        "data": {
            "user": {
                "id": "123",
                "username": "target.user",
                "full_name": "Target User",
                "follower_count": 420,
                "following_count": 88,
                "mutual_followers_count": 4,
                "media_count": 315,
                "is_private": False,
                "is_verified": True,
                "is_professional_account": True,
                "has_highlight_reels": True,
                "profile_pic_url": "https://example.com/pic.jpg",
                "category_name": "Artist",
                "biography": "Music, travel, and visual notes.",
                "account_type": 2,
                "bio_links": [{"url": "https://example.com"}],
                "friendship_status": {
                    "following": True,
                    "followed_by": False,
                },
            }
        }
    }

    result = ii._extract_user_summary(payload)

    assert result["username"] == "target.user"
    assert result["mutual_followers_count"] == 4
    assert result["media_count"] == 315
    assert result["category"] == "Artist"
    assert result["biography"] == "Music, travel, and visual notes."
    assert result["account_type"] == "2"
    assert result["bio_links_count"] == 1
    assert result["is_professional_account"] is True
    assert result["has_highlight_reels"] is True


def test_compute_followback_chances_uses_richer_metadata(monkeypatch):
    monkeypatch.setattr(
        account_handler.db_service,
        "get_target_profile",
        lambda app_user_id, reference_profile_id, target_profile_id: {
            "username": "target.user",
            "is_private": False,
            "is_verified": False,
            "me_following_account": True,
            "being_followed_by_account": False,
            "follower_count": 5000,
            "following_count": 300,
        },
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "get_latest_scanned_profile_ids",
        lambda app_user_id, reference_profile_id: set(),
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "get_target_profile_relationship_ids",
        lambda app_user_id, reference_profile_id, target_profile_id, relationship_type: (
            set()
        ),
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "list_labeled_followback_predictions",
        lambda app_user_id, reference_profile_id, limit=400: [],
    )

    result = account_handler.compute_followback_chances(
        pk_id="123",
        reference_profile_id="ig_123",
        app_user_id="app_test_user",
        metadata={
            "mutual_followers_count": 3,
            "media_count": 1500,
            "category": "Public Figure",
            "biography": "x" * 120,
            "account_type": "2",
            "is_professional_account": True,
            "has_highlight_reels": True,
        },
    )

    assert result["target_username"] == "target.user"
    assert result["feature_breakdown"]["mutual_followers_count"] == 3
    assert result["feature_breakdown"]["category"] == "Public Figure"
    assert result["feature_breakdown"]["is_professional_account"] is True
    assert result["feature_breakdown"]["following_to_follower_ratio"] == 0.06
    assert result["feature_breakdown"]["target_size_bucket"] == "mid"
    assert result["confidence"] > 0.45
    assert any(
        "Mutual followers increase likelihood" in reason for reason in result["reasons"]
    )


def test_request_followback_prediction_reuses_cached_metadata(monkeypatch):
    monkeypatch.setattr(
        account_handler,
        "_cache_ready",
        lambda app_user_id, reference_profile_id, target_profile_id: True,
    )
    monkeypatch.setattr(
        account_handler,
        "_build_profile",
        lambda credentials: object(),
    )
    monkeypatch.setattr(
        account_handler.ii,
        "resolve_target_user_pk",
        lambda username, profile: "target_123",
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "get_target_profile",
        lambda app_user_id, reference_profile_id, target_profile_id: {
            "username": "target.user",
            "follower_count": 100,
            "following_count": 50,
        },
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "get_latest_prediction_for_target",
        lambda app_user_id, reference_profile_id, target_profile_id, prediction_type="follow_back": {
            "result_payload": {
                "target_profile": {
                    "full_name": "Target User",
                    "mutual_followers_count": 6,
                    "category": "Artist",
                    "biography": "Notes",
                    "account_type": "2",
                    "is_professional_account": True,
                    "has_highlight_reels": True,
                    "bio_links_count": 1,
                    "media_count": 77,
                }
            }
        },
    )

    captured: dict[str, object] = {}

    def fake_compute_followback_chances(**kwargs):
        captured.update(kwargs)
        return {
            "target_profile_id": "target_123",
            "target_username": "target.user",
            "followback_probability": 0.5,
            "confidence": 0.6,
            "matched_followers_count": 0,
            "matched_following_count": 0,
            "graph_fetch_status": "metadata_only",
            "used_cached_followers": False,
            "used_cached_following": False,
            "used_fresh_fetch": False,
            "feature_breakdown": {},
            "reasons": [],
        }

    monkeypatch.setattr(
        account_handler,
        "compute_followback_chances",
        fake_compute_followback_chances,
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "create_prediction",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "list_labeled_followback_predictions",
        lambda app_user_id, reference_profile_id, limit=400: [],
    )

    result = account_handler.request_followback_prediction(
        app_user_id="app_test_user",
        instagram_user={
            "instagram_user_id": "ig_123",
            "csrf_token": "csrf",
            "session_id": "session",
            "user_id": "viewer_1",
        },
        username="target.user",
    )

    assert captured["metadata"] == {
        "full_name": "Target User",
        "mutual_followers_count": 6,
        "category": "Artist",
        "biography": "Notes",
        "account_type": "2",
        "is_professional_account": True,
        "has_highlight_reels": True,
        "bio_links_count": 1,
        "media_count": 77,
    }
    assert (
        result["prediction"]["result_payload"]["target_profile"]["category"] == "Artist"
    )
    assert result["task"] is None


def test_request_followback_prediction_reuses_active_task(monkeypatch):
    monkeypatch.setattr(
        account_handler,
        "_cache_ready",
        lambda app_user_id, reference_profile_id, target_profile_id: False,
    )
    monkeypatch.setattr(
        account_handler,
        "_build_profile",
        lambda credentials: object(),
    )
    monkeypatch.setattr(
        account_handler.ii,
        "resolve_target_user_pk",
        lambda username, profile: "target_123",
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "get_target_profile",
        lambda app_user_id, reference_profile_id, target_profile_id: {
            "username": "target.user"
        },
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "list_labeled_followback_predictions",
        lambda app_user_id, reference_profile_id, limit=400: [],
    )

    reused_bundle = {
        "prediction": {
            "prediction_id": "pred_existing",
            "status": "queued",
            "target_profile_id": "target_123",
        },
        "task": {
            "task_id": "task_existing",
            "prediction_id": "pred_existing",
            "status": "queued",
        },
    }
    monkeypatch.setattr(
        prediction_runner,
        "get_active_task_bundle",
        lambda **kwargs: reused_bundle,
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "create_prediction",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("should not create new prediction")
        ),
    )

    result = account_handler.request_followback_prediction(
        app_user_id="app_test_user",
        instagram_user={
            "instagram_user_id": "ig_123",
            "csrf_token": "csrf",
            "session_id": "session",
            "user_id": "viewer_1",
        },
        username="target.user",
        refresh=True,
    )

    assert result == reused_bundle


def test_get_active_task_bundle_reuses_queued_task(monkeypatch):
    queued_task = {
        "task_id": "task_queued",
        "prediction_id": "pred_queued",
        "status": "queued",
        "queued_at": datetime.now().isoformat(),
        "started_at": None,
    }
    prediction = {
        "prediction_id": "pred_queued",
        "status": "queued",
        "target_profile_id": "target_123",
    }

    monkeypatch.setattr(
        prediction_runner.db_service,
        "get_latest_active_prediction_task",
        lambda **kwargs: queued_task,
    )
    monkeypatch.setattr(
        prediction_runner.db_service,
        "get_prediction",
        lambda prediction_id: prediction,
    )

    result = prediction_runner.get_active_task_bundle(
        app_user_id="app_test_user",
        reference_profile_id="ig_123",
        target_profile_id="target_123",
    )

    assert result == {"task": queued_task, "prediction": prediction}


def test_get_active_task_bundle_marks_stale_running_task_as_error(monkeypatch):
    stale_task = {
        "task_id": "task_stale",
        "prediction_id": "pred_stale",
        "status": "running",
        "queued_at": (datetime.now() - timedelta(minutes=6)).isoformat(),
        "started_at": (datetime.now() - timedelta(minutes=6)).isoformat(),
    }
    errored_task = {
        **stale_task,
        "status": "error",
        "error": "Prediction task became inactive after running for more than 5 minutes.",
        "completed_at": datetime.now().isoformat(),
    }
    updated_predictions: list[tuple[str, str]] = []

    monkeypatch.setattr(
        prediction_runner.db_service,
        "get_latest_active_prediction_task",
        lambda **kwargs: stale_task,
    )
    monkeypatch.setattr(
        prediction_runner,
        "mark_task_error",
        lambda task_id, error: errored_task,
    )
    monkeypatch.setattr(
        prediction_runner.db_service,
        "update_prediction",
        lambda prediction_id, status=None, **kwargs: updated_predictions.append(
            (prediction_id, status)
        ),
    )

    result = prediction_runner.get_active_task_bundle(
        app_user_id="app_test_user",
        reference_profile_id="ig_123",
        target_profile_id="target_123",
    )

    assert result is None
    assert updated_predictions == [("pred_stale", "error")]


def test_get_task_status_marks_stale_running_task_as_error(monkeypatch):
    stale_task = {
        "task_id": "task_stale",
        "prediction_id": "pred_stale",
        "status": "running",
        "queued_at": (datetime.now() - timedelta(minutes=6)).isoformat(),
        "started_at": (datetime.now() - timedelta(minutes=6)).isoformat(),
    }
    errored_task = {
        **stale_task,
        "status": "error",
        "error": "Prediction task became inactive after running for more than 5 minutes.",
        "completed_at": datetime.now().isoformat(),
    }
    updated_predictions: list[tuple[str, str]] = []

    monkeypatch.setattr(
        prediction_runner.db_service,
        "get_prediction_task",
        lambda task_id: stale_task,
    )
    monkeypatch.setattr(
        prediction_runner,
        "mark_task_error",
        lambda task_id, error: errored_task,
    )
    monkeypatch.setattr(
        prediction_runner.db_service,
        "update_prediction",
        lambda prediction_id, status=None, **kwargs: updated_predictions.append(
            (prediction_id, status)
        ),
    )

    result = prediction_runner.get_task_status("task_stale")

    assert result == errored_task
    assert updated_predictions == [("pred_stale", "error")]


def test_compute_followback_chances_uses_historical_reference(monkeypatch):
    monkeypatch.setattr(
        account_handler.db_service,
        "get_target_profile",
        lambda app_user_id, reference_profile_id, target_profile_id: {
            "username": "target.user",
            "is_private": False,
            "is_verified": False,
            "me_following_account": True,
            "being_followed_by_account": False,
            "follower_count": 900,
            "following_count": 750,
        },
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "get_latest_scanned_profile_ids",
        lambda app_user_id, reference_profile_id: {"a", "b", "c", "d", "e"},
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "get_target_profile_relationship_ids",
        lambda app_user_id, reference_profile_id, target_profile_id, relationship_type: (
            {"a", "b"} if relationship_type == "followers" else {"c"}
        ),
    )
    monkeypatch.setattr(
        account_handler.db_service,
        "list_labeled_followback_predictions",
        lambda app_user_id, reference_profile_id, limit=400: [
            {
                "outcome_status": "correct",
                "feature_breakdown": {
                    "target_size_bucket": "small",
                    "is_private": False,
                    "is_professional_account": False,
                    "is_verified": False,
                    "mutual_bucket": "medium",
                    "overlap_followers_bucket": "low",
                    "overlap_following_bucket": "low",
                    "graph_fetch_status": "ready",
                    "me_following_account": True,
                    "being_followed_by_account": False,
                },
            },
            {
                "outcome_status": "correct",
                "feature_breakdown": {
                    "target_size_bucket": "small",
                    "is_private": False,
                    "is_professional_account": False,
                    "is_verified": False,
                    "mutual_bucket": "medium",
                    "overlap_followers_bucket": "low",
                    "overlap_following_bucket": "low",
                    "graph_fetch_status": "ready",
                    "me_following_account": True,
                    "being_followed_by_account": False,
                },
            },
            {
                "outcome_status": "wrong",
                "feature_breakdown": {
                    "target_size_bucket": "large",
                    "is_private": True,
                    "is_professional_account": True,
                    "is_verified": False,
                    "mutual_bucket": "none",
                    "overlap_followers_bucket": "none",
                    "overlap_following_bucket": "none",
                    "graph_fetch_status": "metadata_only",
                    "me_following_account": False,
                    "being_followed_by_account": False,
                },
            },
        ],
    )

    result = account_handler.compute_followback_chances(
        pk_id="123",
        reference_profile_id="ig_123",
        app_user_id="app_test_user",
        metadata={
            "mutual_followers_count": 4,
            "media_count": 80,
            "is_professional_account": False,
        },
    )

    assert result["statistical_reference_count"] == 3
    assert result["statistical_reference_rate"] > result["global_historical_rate"]
    assert any(
        "Historical confirmed outcomes were used to calibrate this score" in reason
        for reason in result["reasons"]
    )
