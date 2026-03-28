import json
from datetime import datetime
from pathlib import Path

from meerkit.config import CACHE_DIR

RELATIONSHIP_CACHE_ROOT = CACHE_DIR
VALID_RELATIONSHIP_TYPES = {"followers", "following"}


def _target_cache_dir(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
) -> Path:
    return (
        RELATIONSHIP_CACHE_ROOT / app_user_id / reference_profile_id / target_profile_id
    )


def build_cache_file_path(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
    fetched_at: str,
) -> Path:
    if relationship_type not in VALID_RELATIONSHIP_TYPES:
        raise ValueError(f"Unsupported relationship type: {relationship_type}")

    try:
        parsed = datetime.fromisoformat(fetched_at)
    except ValueError:
        parsed = datetime.now()
    date_fragment = parsed.strftime("%d_%m_%Y_%H%M%S")
    filename = f"{relationship_type}_{date_fragment}.json"
    return (
        _target_cache_dir(app_user_id, reference_profile_id, target_profile_id)
        / filename
    )


def write_relationship_cache_file(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
    fetched_at: str,
    profiles_payload: list[dict],
) -> str:
    cache_path = build_cache_file_path(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        relationship_type=relationship_type,
        fetched_at=fetched_at,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = cache_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(profiles_payload, handle, indent=2)
    temp_path.replace(cache_path)
    return str(cache_path)


def delete_cache_file(cache_file_path: str | None) -> None:
    if not cache_file_path:
        return
    path = Path(cache_file_path)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        return
