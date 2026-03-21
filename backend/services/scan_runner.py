import threading
import traceback
from datetime import datetime
from pathlib import Path

from backend import scan_worker
from backend.services import persistence

_locks: dict[str, threading.Lock] = {}
_states: dict[str, dict] = {}
_threads: dict[str, threading.Thread] = {}
_STALE_STARTUP_GRACE_SECONDS = 5


def _scope_key(app_user_id: str, profile_id: str) -> str:
    """Build a stable lock/state key for one user's profile scans."""
    return f"{app_user_id}:{profile_id}"


def _ensure_state(key: str) -> dict:
    if key not in _states:
        _states[key] = {
            "status": "idle",  # idle | running | cancelled | error
            "started_at": None,
            "last_scan_id": None,
            "last_scan_at": None,
            "error": None,
        }
    if key not in _locks:
        _locks[key] = threading.Lock()
    return _states[key]


def get_status(app_user_id: str, profile_id: str) -> dict:
    """Return scan status for one user/profile scope.

    If the server has restarted and no scan has run in this process,
    last_scan_at / last_scan_id are hydrated from the persisted scan index
    so the dashboard never incorrectly shows 'Never'.
    """
    key = _scope_key(app_user_id, profile_id)
    state = _ensure_state(key)
    _cleanup_stale_running_state(key, state)
    if state["last_scan_at"] is None and state["status"] == "idle":
        meta = persistence.get_latest_scan_meta(profile_id)
        if meta:
            state["last_scan_at"] = meta.get("timestamp")
            state["last_scan_id"] = meta.get("scan_id")
    return dict(state)


def _started_recently(started_at: object) -> bool:
    if not isinstance(started_at, str) or not started_at:
        return False
    try:
        started_at_value = datetime.fromisoformat(started_at)
    except ValueError:
        return False
    return (
        datetime.now() - started_at_value
    ).total_seconds() < _STALE_STARTUP_GRACE_SECONDS


def _cleanup_stale_running_state(key: str, state: dict) -> None:
    if state.get("status") != "running":
        return
    scan_thread = _threads.get(key)
    if scan_thread is not None:
        if scan_thread.is_alive():
            return
    elif _started_recently(state.get("started_at")):
        return
    state.update(
        {
            "status": "error",
            "error": "Scan task is stale because its worker thread is no longer active.",
        }
    )


def _run_worker(
    app_user_id: str, data_dir: Path, credentials: dict, target_user_id: str
) -> dict:
    """Run scan directly via Python function using explicit credentials."""
    return scan_worker.run_scoped_scan(
        app_user_id=app_user_id,
        data_dir=data_dir,
        csrf_token=credentials["csrf_token"],
        session_id=credentials["session_id"],
        target_user_id=target_user_id,
    )


def start_scan(
    app_user_id: str,
    profile_id: str,
    data_dir: Path,
    credentials: dict,
    target_user_id: str,
) -> bool:
    """Start a background scan for one user/profile, returning False if already running."""
    key = _scope_key(app_user_id, profile_id)
    state = _ensure_state(key)
    _cleanup_stale_running_state(key, state)
    lock = _locks[key]

    acquired = lock.acquire(blocking=False)
    if not acquired:
        return False

    state.update(
        {
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "error": None,
        }
    )

    def _run() -> None:
        try:
            result = _run_worker(app_user_id, data_dir, credentials, target_user_id)
            if state.get("status") != "cancelled":
                state.update(
                    {
                        "status": "idle",
                        "last_scan_id": result["scan_id"],
                        "last_scan_at": result["timestamp"],
                    }
                )
        except Exception as exc:
            _detailed_error = traceback.format_exc()
            print(f"Scan worker error for {key}: {_detailed_error}")
            if state.get("status") != "cancelled":
                state.update({"status": "error", "error": str(exc)})
        finally:
            _threads.pop(key, None)
            lock.release()

    thread = threading.Thread(target=_run, daemon=True)
    _threads[key] = thread
    thread.start()
    return True


def cancel_scan(app_user_id: str, profile_id: str) -> dict:
    key = _scope_key(app_user_id, profile_id)
    state = _ensure_state(key)
    _cleanup_stale_running_state(key, state)

    if state.get("status") != "running":
        return {
            "ok": False,
            "status": state.get("status"),
            "message": "No running scan to cancel.",
        }

    state.update(
        {
            "status": "cancelled",
            "error": "Cancelled by user.",
        }
    )
    return {
        "ok": True,
        "status": "cancelled",
        "message": "Scan marked as cancelled.",
    }


def list_running_scans(app_user_id: str) -> list[dict]:
    tasks: list[dict] = []
    prefix = f"{app_user_id}:"

    for key, state in list(_states.items()):
        if not key.startswith(prefix):
            continue

        _cleanup_stale_running_state(key, state)
        if state.get("status") not in {"running", "cancelled"}:
            continue

        _scope_app_user_id, profile_id = key.split(":", 1)
        latest_meta = persistence.get_latest_scan_meta(profile_id)
        tasks.append(
            {
                "task_id": f"scan:{key}",
                "task_type": "scan",
                "source": "scan",
                "status": state.get("status"),
                "progress": None,
                "error": state.get("error"),
                "queued_at": state.get("started_at"),
                "started_at": state.get("started_at"),
                "completed_at": None,
                "target_profile_id": profile_id,
                "target_username": None,
                "can_cancel": state.get("status") == "running",
                "metric_label": "last follower count",
                "metric_value": latest_meta.get("follower_count")
                if latest_meta
                else None,
            }
        )

    return tasks


def get_active_scan_task(app_user_id: str, profile_id: str) -> dict | None:
    key = _scope_key(app_user_id, profile_id)
    state = _ensure_state(key)
    _cleanup_stale_running_state(key, state)

    if state.get("status") not in {"running", "cancelled"}:
        return None

    latest_meta = persistence.get_latest_scan_meta(profile_id)
    return {
        "task_id": f"scan:{key}",
        "task_type": "scan",
        "source": "scan",
        "status": state.get("status"),
        "progress": None,
        "error": state.get("error"),
        "queued_at": state.get("started_at"),
        "started_at": state.get("started_at"),
        "completed_at": None,
        "target_profile_id": profile_id,
        "target_username": None,
        "can_cancel": state.get("status") == "running",
        "metric_label": "last follower count",
        "metric_value": latest_meta.get("follower_count") if latest_meta else None,
    }
