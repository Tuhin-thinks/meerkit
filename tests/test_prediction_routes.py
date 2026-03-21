from backend.app import create_app


def test_create_followback_prediction_returns_queued_payload(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "backend.routes.predict.get_active_context",
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
        "backend.routes.predict.account_handler.request_followback_prediction",
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
        "backend.routes.predict.get_active_context",
        lambda instagram_user_id_override=None: (
            "app_test_user",
            {"instagram_user_id": "ig_123"},
        ),
    )
    monkeypatch.setattr(
        "backend.routes.predict.db_service.list_predictions",
        lambda **kwargs: [
            {
                "prediction_id": "pred_123",
                "prediction_type": "follow_back",
                "status": "completed",
            }
        ],
    )

    response = client.get("/api/predictions/history")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == [
        {
            "prediction_id": "pred_123",
            "prediction_type": "follow_back",
            "status": "completed",
        }
    ]
