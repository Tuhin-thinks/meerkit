import sqlite3
import threading
from datetime import datetime, timedelta

from backend.db.db_handler import SqliteDBHandler
from backend.services import automation_runner, db_service
from backend.workers import automation_worker


def _use_temp_worker_db(monkeypatch, tmp_path):
    db_path = tmp_path / "app_user_db.sqlite"
    monkeypatch.setattr(db_service, "_thread_local", threading.local())
    monkeypatch.setattr(db_service, "app_user_db", lambda: db_path)
    return db_path


def test_sqlite_init_backfills_automation_heartbeat_column(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE automation_actions (
                action_id TEXT PRIMARY KEY,
                app_user_id TEXT NOT NULL,
                reference_profile_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                config_json TEXT,
                total_items INTEGER NOT NULL DEFAULT 0,
                completed_items INTEGER NOT NULL DEFAULT 0,
                failed_items INTEGER NOT NULL DEFAULT 0,
                skipped_items INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                queued_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                create_date TEXT NOT NULL,
                update_date TEXT NOT NULL
            )
            """
        )
        conn.commit()

    SqliteDBHandler(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(automation_actions)")
        }

    assert "last_heartbeat_at" in columns


def test_update_automation_action_persists_last_heartbeat(monkeypatch, tmp_path):
    _use_temp_worker_db(monkeypatch, tmp_path)

    action = db_service.create_automation_action(
        action_id="action_1",
        app_user_id="app_1",
        reference_profile_id="ig_1",
        action_type="batch_unfollow",
    )

    heartbeat_at = datetime.now().isoformat()
    db_service.update_automation_action(
        action["action_id"],
        status="running",
        started_at=heartbeat_at,
        last_heartbeat_at=heartbeat_at,
    )

    refreshed = db_service.get_automation_action(action["action_id"])

    assert refreshed is not None
    assert refreshed["last_heartbeat_at"] == heartbeat_at
    assert refreshed["started_at"] == heartbeat_at


def test_get_action_status_keeps_recent_heartbeat_running(monkeypatch):
    recent_action = {
        "action_id": "action_recent",
        "status": "running",
        "started_at": (datetime.now() - timedelta(minutes=25)).isoformat(),
        "last_heartbeat_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
    }
    monkeypatch.setattr(automation_runner, "_states", {})
    monkeypatch.setattr(
        automation_runner.db_service,
        "get_automation_action",
        lambda action_id: recent_action,
    )

    result = automation_runner.get_action_status("action_recent")

    assert result == recent_action


def test_get_action_status_marks_expired_heartbeat_as_error(monkeypatch):
    stale_action = {
        "action_id": "action_stale",
        "status": "running",
        "started_at": (datetime.now() - timedelta(minutes=20)).isoformat(),
        "last_heartbeat_at": (datetime.now() - timedelta(minutes=11)).isoformat(),
    }
    errored_action = {
        **stale_action,
        "status": "error",
        "error": "Automation action became inactive after running for more than 10 minutes.",
    }

    monkeypatch.setattr(automation_runner, "_states", {})
    monkeypatch.setattr(
        automation_runner.db_service,
        "get_automation_action",
        lambda action_id: stale_action,
    )
    monkeypatch.setattr(
        automation_runner,
        "mark_action_error",
        lambda action_id, error: {**errored_action, "error": error},
    )

    result = automation_runner.get_action_status("action_stale")

    assert result == errored_action


def test_get_action_status_uses_started_at_for_legacy_rows(monkeypatch):
    legacy_action = {
        "action_id": "action_legacy",
        "status": "running",
        "started_at": (datetime.now() - timedelta(minutes=11)).isoformat(),
        "last_heartbeat_at": None,
    }
    errored_action = {
        **legacy_action,
        "status": "error",
        "error": "Automation action became inactive after running for more than 10 minutes.",
    }

    monkeypatch.setattr(automation_runner, "_states", {})
    monkeypatch.setattr(
        automation_runner.db_service,
        "get_automation_action",
        lambda action_id: legacy_action,
    )
    monkeypatch.setattr(
        automation_runner,
        "mark_action_error",
        lambda action_id, error: {**errored_action, "error": error},
    )

    result = automation_runner.get_action_status("action_legacy")

    assert result == errored_action


def test_get_action_status_keeps_queued_timeout_logic(monkeypatch):
    queued_action = {
        "action_id": "action_queued",
        "status": "queued",
        "queued_at": (datetime.now() - timedelta(minutes=11)).isoformat(),
        "started_at": None,
        "last_heartbeat_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
    }
    errored_action = {
        **queued_action,
        "status": "error",
        "error": "Automation action stayed queued for more than 10 minutes.",
    }

    monkeypatch.setattr(automation_runner, "_states", {})
    monkeypatch.setattr(
        automation_runner.db_service,
        "get_automation_action",
        lambda action_id: queued_action,
    )
    monkeypatch.setattr(
        automation_runner,
        "mark_action_error",
        lambda action_id, error: {**errored_action, "error": error},
    )

    result = automation_runner.get_action_status("action_queued")

    assert result == errored_action


def test_execute_action_emits_heartbeats_during_shared_loop(monkeypatch):
    heartbeats: list[str] = []
    completed: list[str] = []
    failed: list[str] = []
    delays: list[str] = []
    terminal: list[str] = []

    pending_items = [
        {"item_id": "item_1", "status": "pending"},
        {"item_id": "item_2", "status": "pending"},
    ]
    outcomes = iter([True, False])

    monkeypatch.setattr(
        automation_worker.db_service,
        "list_automation_action_items",
        lambda action_id, statuses=None: pending_items,
    )
    monkeypatch.setattr(
        automation_worker.automation_runner,
        "get_action_status",
        lambda action_id: {"action_id": action_id, "status": "running"},
    )
    monkeypatch.setattr(
        automation_worker,
        "execute_follow_item",
        lambda item, instagram_user, app_user_id: next(outcomes),
    )
    monkeypatch.setattr(
        automation_worker.automation_runner,
        "mark_action_heartbeat",
        lambda action_id: heartbeats.append(action_id),
    )
    monkeypatch.setattr(
        automation_worker.automation_runner,
        "record_item_completed",
        lambda action_id: completed.append(action_id),
    )
    monkeypatch.setattr(
        automation_worker.automation_runner,
        "record_item_failed",
        lambda action_id: failed.append(action_id),
    )
    monkeypatch.setattr(
        automation_worker,
        "inter_action_delay",
        lambda: delays.append("delay"),
    )
    monkeypatch.setattr(
        automation_worker.db_service,
        "get_automation_action",
        lambda action_id: {
            "action_id": action_id,
            "action_type": "batch_follow",
            "completed_items": 1,
            "failed_items": 1,
            "config": None,
        },
    )
    monkeypatch.setattr(
        automation_worker.automation_runner,
        "mark_action_partial",
        lambda action_id: terminal.append(action_id),
    )

    automation_worker._execute_action(
        action_id="action_1",
        action_type="batch_follow",
        app_user_id="app_1",
        instagram_user={"instagram_user_id": "ig_1"},
    )

    assert heartbeats == ["action_1", "action_1", "action_1"]
    assert completed == ["action_1"]
    assert failed == ["action_1"]
    assert delays == ["delay"]
    assert terminal == ["action_1"]
