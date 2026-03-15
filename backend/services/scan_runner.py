import threading
import traceback
from datetime import datetime
from pathlib import Path

from backend import scan_worker
from backend.services import persistence

_locks: dict[str, threading.Lock] = {}
_states: dict[str, dict] = {}


def _scope_key(app_user_id: str, profile_id: str) -> str:
    """Build a stable lock/state key for one user's profile scans."""
    return f"{app_user_id}:{profile_id}"


def _ensure_state(key: str) -> dict:
    if key not in _states:
        _states[key] = {
            "status": "idle",  # idle | running | error
            "started_at": None,
            "last_scan_id": None,
            "last_scan_at": None,
            "error": None,
        }
    if key not in _locks:
        _locks[key] = threading.Lock()
    return _states[key]


def get_status(app_user_id: str, profile_id: str, data_dir: Path | None = None) -> dict:
    """Return scan status for one user/profile scope.

    If the server has restarted and no scan has run in this process,
    last_scan_at / last_scan_id are hydrated from the persisted scan index
    so the dashboard never incorrectly shows 'Never'.
    """
    key = _scope_key(app_user_id, profile_id)
    state = _ensure_state(key)
    if (
        data_dir is not None
        and state["last_scan_at"] is None
        and state["status"] == "idle"
    ):
        meta = persistence.get_latest_scan_meta(data_dir)
        if meta:
            state["last_scan_at"] = meta.get("timestamp")
            state["last_scan_id"] = meta.get("scan_id")
    return dict(state)


def _run_worker(data_dir: Path, credentials: dict, target_user_id: str) -> dict:
    """Run scan directly via Python function using explicit credentials."""
    return scan_worker.run_scoped_scan(
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
            result = _run_worker(data_dir, credentials, target_user_id)
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
            state.update({"status": "error", "error": str(exc)})
        finally:
            lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return True
