import json
from pathlib import Path

from backend.services import db_service


def _scan_index_file(data_dir: Path) -> Path:
    """Return the scan index file path under a scoped data directory."""
    return data_dir / "scan_index.jsonl"


def _scans_dir(data_dir: Path) -> Path:
    """Return the scoped scans directory."""
    return data_dir / "scans"


def get_scan_index(data_dir: Path) -> list[dict]:
    """Return all scan metadata entries, newest first."""
    index_file = _scan_index_file(data_dir)
    if not index_file.exists():
        return []
    entries: list[dict] = []
    with open(index_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return list(reversed(entries))


def get_latest_scan_meta(reference_profile_id: str):
    """Return the newest scan metadata entry, if present."""
    db = db_service.get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scan_id, scan_time FROM scan_history WHERE reference_profile_id = ? ORDER BY scan_time DESC LIMIT 1",
            (reference_profile_id,),
        )
        latest_scan = cursor.fetchone()
        follower_count = 0
        if latest_scan:
            cursor.execute(
                "SELECT COUNT(*) AS follower_count FROM scanned_data WHERE scan_id = ?",
                (latest_scan["scan_id"],),
            )
            follower_count = cursor.fetchone()["follower_count"]
    diff_id = db_service.get_latest_diff_id(reference_profile_id=reference_profile_id)
    if not latest_scan:
        return None
    return {
        "scan_id": latest_scan["scan_id"],
        "timestamp": latest_scan["scan_time"],
        "follower_count": follower_count,
        "diff_id": diff_id,
    }


def get_diff(diff_id: str) -> dict | None:
    """Return a persisted diff payload by diff ID."""
    return db_service.get_diff_by_id(diff_id=diff_id)


def get_latest_diff(reference_profile_id: str) -> dict | None:
    """Return the latest diff payload for the newest scan."""
    meta = get_latest_scan_meta(reference_profile_id)
    if not meta or not meta.get("diff_id"):
        return None
    return get_diff(meta["diff_id"])


def get_profile_pic_url(
    app_user_id: str,
    reference_profile_id: str,
    pk_id: str,
    data_dir: Path | None = None,
) -> str | None:
    """Find the latest known profile_pic_url for a follower within the current scope."""
    latest_url = db_service.get_latest_profile_pic_url(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        pk_id=pk_id,
    )
    if latest_url:
        return latest_url

    if data_dir is None:
        return None
    return None
