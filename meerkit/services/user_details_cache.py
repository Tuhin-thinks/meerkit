"""Central cache handler for Instagram user-profile details.

Cache layout::

    data/cache/{app_user_id}/{instagram_user_id}/user_details.json
    data/cache/{app_user_id}/{instagram_user_id}/targets/{target_user_id}_user_details.json

All public functions use atomic temp-file writes so partial writes never leave
a corrupt file on disk.  Call ``invalidate()`` / ``invalidate_target()`` to
force a fresh API fetch on the next request.
"""

import json
from datetime import datetime
from pathlib import Path

from meerkit.config import CACHE_DIR

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _own_path(app_user_id: str, instagram_user_id: str) -> Path:
    return CACHE_DIR / app_user_id / instagram_user_id / "user_details.json"


def _target_path(app_user_id: str, instagram_user_id: str, target_user_id: str) -> Path:
    return (
        CACHE_DIR
        / app_user_id
        / instagram_user_id
        / "targets"
        / f"{target_user_id}_user_details.json"
    )


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump({"cached_at": datetime.now().isoformat(), **data}, fh, indent=2)
    tmp.replace(path)


def _delete(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Own-user profile (the logged-in Instagram account)
# ---------------------------------------------------------------------------


def load(app_user_id: str, instagram_user_id: str) -> dict | None:
    """Return cached own-user details, or None on miss."""
    return _read(_own_path(app_user_id, instagram_user_id))


def save(app_user_id: str, instagram_user_id: str, data: dict) -> None:
    """Persist own-user details. Overwrites any existing file."""
    _write(_own_path(app_user_id, instagram_user_id), data)


def invalidate(app_user_id: str, instagram_user_id: str) -> None:
    """Delete cached own-user details so the next call hits the API."""
    _delete(_own_path(app_user_id, instagram_user_id))


# ---------------------------------------------------------------------------
# Target-user profile (profiles looked up by the logged-in account)
# ---------------------------------------------------------------------------


def load_target(
    app_user_id: str, instagram_user_id: str, target_user_id: str
) -> dict | None:
    """Return cached target-user details, or None on miss."""
    return _read(_target_path(app_user_id, instagram_user_id, target_user_id))


def save_target(
    app_user_id: str, instagram_user_id: str, target_user_id: str, data: dict
) -> None:
    """Persist target-user details. Overwrites any existing file."""
    _write(_target_path(app_user_id, instagram_user_id, target_user_id), data)


def invalidate_target(
    app_user_id: str, instagram_user_id: str, target_user_id: str
) -> None:
    """Delete cached target-user details so the next call hits the API."""
    _delete(_target_path(app_user_id, instagram_user_id, target_user_id))
