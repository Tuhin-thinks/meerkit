from meerkit.app import create_app


def test_create_followback_prediction_returns_queued_payload(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.predict.get_active_context",
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
    monkeypatch.setattr(
        "meerkit.routes.predict.account_handler.request_followback_prediction",
        lambda **kwargs: {
            "prediction": {
                "prediction_id": "pred_123",
                "status": "queued",
                "target_profile_id": "target_1",
            },
            "task": {"task_id": "task_123", "status": "queued"},
        },
    )

    response = client.post(
        "/api/predictions/follow-back",
        json={"username": "target.user", "refresh": True},
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["prediction"]["prediction_id"] == "pred_123"
    assert payload["task"]["task_id"] == "task_123"


def test_prediction_history_returns_persisted_rows(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.predict.get_active_context",
        lambda instagram_user_id_override=None: (
            "app_test_user",
            {"instagram_user_id": "ig_123"},
        ),
    )
    monkeypatch.setattr(
        "meerkit.routes.predict.db_service.list_prediction_sessions",
        lambda **kwargs: [
            {
                "prediction_session_id": "pred_session_123",
                "latest_prediction_id": "pred_123",
                "prediction_type": "follow_back",
                "status": "completed",
                "prediction_count": 12,
            }
        ],
    )

    response = client.get("/api/predictions/history")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == [
        {
            "prediction_session_id": "pred_session_123",
            "latest_prediction_id": "pred_123",
            "prediction_type": "follow_back",
            "status": "completed",
            "prediction_count": 12,
        }
    ]


def test_prediction_history_session_items_returns_rows(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.predict.get_active_context",
        lambda instagram_user_id_override=None: (
            "app_test_user",
            {"instagram_user_id": "ig_123"},
        ),
    )
    monkeypatch.setattr(
        "meerkit.routes.predict.db_service.list_predictions_for_session",
        lambda **kwargs: [
            {
                "prediction_id": "pred_1",
                "target_username": "alice",
                "target_profile_summary": {
                    "full_name": "Alice A",
                    "profile_pic_url": "https://example.com/a.jpg",
                },
            }
        ],
    )

    response = client.get("/api/predictions/history/sessions/pred_session_123")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == [
        {
            "prediction_id": "pred_1",
            "target_username": "alice",
            "target_profile_summary": {
                "full_name": "Alice A",
                "profile_pic_url": "https://example.com/a.jpg",
            },
        }
    ]


def test_prediction_task_status_returns_normalized_error(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.predict.get_active_context",
        lambda instagram_user_id_override=None: (
            "app_test_user",
            {"instagram_user_id": "ig_123"},
        ),
    )
    monkeypatch.setattr(
        "meerkit.routes.predict.prediction_runner.get_task_status",
        lambda task_id: {
            "task_id": task_id,
            "prediction_id": "pred_123",
            "status": "error",
            "error": "Prediction task became inactive after running for more than 5 minutes.",
        },
    )

    response = client.get("/api/prediction-tasks/task_123/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "error"


def test_relationship_cache_status_returns_payload(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.predict.get_active_context",
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
    monkeypatch.setattr(
        "meerkit.routes.predict.account_handler.get_target_relationship_cache_status",
        lambda **kwargs: {
            "followers": {
                "relationship_type": "followers",
                "days_since_fetch": 2,
                "is_outdated": False,
            },
            "following": {
                "relationship_type": "following",
                "days_since_fetch": 1,
                "is_outdated": True,
            },
        },
    )

    response = client.get("/api/targets/target_1/relationship-cache")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["followers"]["relationship_type"] == "followers"
    assert payload["following"]["is_outdated"] is True


def test_refresh_relationship_cache_requires_valid_type(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "meerkit.routes.predict.get_active_context",
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

    response = client.post(
        "/api/targets/target_1/relationship-cache/refresh",
        json={"relationship_type": "invalid"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert "relationship_type" in payload["error"]
