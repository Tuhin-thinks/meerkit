import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict, cast

import requests

import insta_interface as ii
from meerkit.config import (
    ACCESSIBILITY_DB_STATUS_MAX_AGE_HOURS,
    MAX_LIVE_DEACTIVATION_CHECKS_PER_SCAN,
)
from meerkit.services import db_service
from meerkit.services.db_service import get_diff_file_path
from meerkit.services.exceptions import MissingCurlPatternError
from meerkit.services.instagram_gateway import instagram_gateway

logger = logging.getLogger(__name__)


class TargetProfileValues(TypedDict):
    username: str | None
    full_name: str | None
    follower_count: int | None
    following_count: int | None
    is_private: bool | None
    is_verified: bool | None
    me_following_account: bool | None
    being_followed_by_account: bool | None
    is_deactivated: bool | None
    fetch_status: str
    metadata_fetched_at: str | None
    relationships_fetched_at: str | None
    last_error: str | None


class DiffAccessibilityResult(TypedDict):
    seeded_profiles: int
    reactivated_profile_ids: set[str]
    checked_profile_ids: set[str]
    updated_rows: int
    diff_path: Path | None


def _best_value(*values: object) -> object:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _normalize_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _row_to_record(row: dict) -> ii.FollowerUserRecord | None:
    profile_id = str(row.get("pk_id") or row.get("id") or "").strip()
    username = str(row.get("username") or "").strip()
    if not profile_id or not username:
        return None
    return ii.FollowerUserRecord(
        pk_id=profile_id,
        id=profile_id,
        profile_pic_url=str(row.get("profile_pic_url") or ""),
        username=username,
        full_name=str(row.get("full_name") or ""),
        is_private=bool(row.get("is_private", False)),
        fbid_v2=(
            str(row.get("fbid_v2")) if row.get("fbid_v2") not in (None, "") else None
        ),
        profile_pic_id=(
            str(row.get("profile_pic_id"))
            if row.get("profile_pic_id") not in (None, "")
            else None
        ),
        is_verified=_normalize_bool(row.get("is_verified")),
    )


def _extract_records(payload: dict, key: str) -> list[ii.FollowerUserRecord]:
    rows = payload.get(key)
    if not isinstance(rows, list):
        return []
    records: list[ii.FollowerUserRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = _row_to_record(row)
        if record is not None:
            records.append(record)
    return records


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return str(value)


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _as_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _target_profile_values(
    existing: dict | None,
    follower: ii.FollowerUserRecord,
) -> TargetProfileValues:
    existing = existing or {}
    return {
        "username": cast(
            str | None,
            _best_value(follower.username, _as_str(existing.get("username"))),
        ),
        "full_name": cast(
            str | None,
            _best_value(follower.full_name, _as_str(existing.get("full_name"))),
        ),
        "follower_count": _as_int(existing.get("follower_count")),
        "following_count": _as_int(existing.get("following_count")),
        "is_private": cast(
            bool | None,
            _best_value(follower.is_private, _as_bool(existing.get("is_private"))),
        ),
        "is_verified": cast(
            bool | None,
            _best_value(follower.is_verified, _as_bool(existing.get("is_verified"))),
        ),
        "me_following_account": _as_bool(existing.get("me_following_account")),
        "being_followed_by_account": _as_bool(
            existing.get("being_followed_by_account")
        ),
        "is_deactivated": _as_bool(existing.get("is_deactivated")),
        "fetch_status": _as_str(existing.get("fetch_status")) or "partial",
        "metadata_fetched_at": _as_str(existing.get("metadata_fetched_at")),
        "relationships_fetched_at": _as_str(existing.get("relationships_fetched_at")),
        "last_error": _as_str(existing.get("last_error")),
    }


def seed_target_profiles_from_records(
    *,
    app_user_id: str,
    reference_profile_id: str,
    records: list[ii.FollowerUserRecord],
) -> int:
    seeded = 0
    for follower in records:
        profile_id = str(follower.pk_id or "").strip()
        username = str(follower.username or "").strip()
        if not profile_id or not username:
            continue
        existing = db_service.get_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=profile_id,
        )
        values = _target_profile_values(existing, follower)
        db_service.upsert_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=profile_id,
            username=values["username"],
            full_name=values["full_name"],
            follower_count=values["follower_count"],
            following_count=values["following_count"],
            is_private=values["is_private"],
            is_verified=values["is_verified"],
            me_following_account=values["me_following_account"],
            being_followed_by_account=values["being_followed_by_account"],
            is_deactivated=values["is_deactivated"],
            fetch_status=str(values["fetch_status"]),
            metadata_fetched_at=values["metadata_fetched_at"],
            relationships_fetched_at=values["relationships_fetched_at"],
            last_error=values["last_error"],
        )
        if existing is None:
            seeded += 1
    return seeded


def seed_target_profiles_from_diff_payload(
    *,
    app_user_id: str,
    reference_profile_id: str,
    payload: dict,
) -> int:
    records = _extract_records(payload, "new_followers") + _extract_records(
        payload,
        "unfollowers",
    )
    return seed_target_profiles_from_records(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        records=records,
    )


def reactivate_returned_accounts(
    *,
    app_user_id: str,
    reference_profile_id: str,
    new_followers: list[ii.FollowerUserRecord],
) -> set[str]:
    reactivated_ids: set[str] = set()
    for follower in new_followers:
        profile_id = str(follower.pk_id or "").strip()
        if not profile_id:
            continue
        existing = db_service.get_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=profile_id,
        )
        if not existing or not existing.get("is_deactivated"):
            continue
        values = _target_profile_values(existing, follower)
        db_service.upsert_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=profile_id,
            username=values["username"],
            full_name=values["full_name"],
            follower_count=values["follower_count"],
            following_count=values["following_count"],
            is_private=values["is_private"],
            is_verified=values["is_verified"],
            me_following_account=values["me_following_account"],
            being_followed_by_account=values["being_followed_by_account"],
            is_deactivated=False,
            fetch_status=str(values["fetch_status"]),
            metadata_fetched_at=values["metadata_fetched_at"],
            relationships_fetched_at=values["relationships_fetched_at"],
            last_error=None,
        )
        reactivated_ids.add(profile_id)
    return reactivated_ids


def _parse_iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _fresh_db_deactivation_status(target_profile: dict) -> bool | None:
    """Return a stored deactivation decision only while it is fresh enough.

    Returns None when there is no decision, or the decision is older than
    ACCESSIBILITY_DB_STATUS_MAX_AGE_HOURS, forcing a live re-check.
    """
    if not target_profile:
        return None
    status_value = target_profile.get("is_deactivated")
    if status_value is None:
        return None

    updated_at = _parse_iso_timestamp(
        target_profile.get("updated_at") or target_profile.get("update_date")
    )
    if updated_at is None:
        return None

    max_age = timedelta(hours=max(1, ACCESSIBILITY_DB_STATUS_MAX_AGE_HOURS))
    now = (
        datetime.now(updated_at.tzinfo)
        if updated_at.tzinfo is not None
        else datetime.now()
    )
    if now - updated_at > max_age:
        return None
    return bool(status_value)


def _extract_user_values(user_data: dict) -> dict:
    """Pull target_profiles metadata fields out of a user object."""
    friendship_status = user_data.get("friendship_status")
    friendship_status = friendship_status if isinstance(friendship_status, dict) else {}
    return {
        "username": _as_str(user_data.get("username")),
        "full_name": _as_str(user_data.get("full_name")),
        "follower_count": _as_int(user_data.get("follower_count")),
        "following_count": _as_int(user_data.get("following_count")),
        "is_private": _as_bool(user_data.get("is_private")),
        "is_verified": _as_bool(user_data.get("is_verified")),
        "me_following_account": _as_bool(friendship_status.get("following")),
        "being_followed_by_account": _as_bool(friendship_status.get("followed_by")),
    }


def live_deactivated_map(
    *,
    app_user_id: str,
    reference_profile_id: str,
    profile: ii.InstagramProfile,
    target_profile_ids: set[str],
    caller_service: str,
    caller_method: str,
    max_checks: int = MAX_LIVE_DEACTIVATION_CHECKS_PER_SCAN,
) -> tuple[dict[str, bool], set[str]]:
    """Decide which target accounts are deactivated / not accessible.

    Each target is resolved with a SINGLE live user-data probe
    (``get_target_user_data``) instead of paginating their full follower and
    following lists: a missing user object (GraphQL ``errors`` or null user)
    means the account is not accessible. Fresh stored decisions from
    ``target_profiles`` are reused within the configured max age, and the
    number of live probes per call is capped by ``max_checks``.

    Transport errors never fail the scan: the target keeps its stored decision
    and the error is recorded, but it is excluded from the returned map.

    Returns (deactivated_map, live_checked_profile_ids).
    """
    result: dict[str, bool] = {}
    checked_ids: set[str] = set()
    checked_at = datetime.now().isoformat()

    for target_profile_id in sorted(target_profile_ids):
        existing = (
            db_service.get_target_profile(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                target_profile_id=target_profile_id,
            )
            or {}
        )

        fresh_status = _fresh_db_deactivation_status(existing)
        if fresh_status is not None:
            result[target_profile_id] = fresh_status
            continue

        if len(checked_ids) >= max_checks:
            logger.info(
                "Skipping live accessibility check for %s: budget %s reached",
                target_profile_id,
                max_checks,
            )
            continue

        checked_ids.add(target_profile_id)
        try:
            user_data = instagram_gateway.get_target_user_data(
                app_user_id=app_user_id,
                instagram_user_id=reference_profile_id,
                profile=profile,
                target_user_id=target_profile_id,
                caller_service=caller_service,
                caller_method=caller_method,
                force_refresh=True,
            )
            user_dict = (
                user_data
                if isinstance(user_data, dict) and user_data.get("id") is not None
                else {}
            )
            is_deactivated = not bool(user_dict)
            values = _extract_user_values(user_dict)
            db_service.upsert_target_profile(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                target_profile_id=target_profile_id,
                username=values["username"],
                full_name=values["full_name"],
                follower_count=values["follower_count"],
                following_count=values["following_count"],
                is_private=values["is_private"],
                is_verified=values["is_verified"],
                me_following_account=values["me_following_account"],
                being_followed_by_account=values["being_followed_by_account"],
                is_deactivated=is_deactivated,
                fetch_status="live",
                metadata_fetched_at=checked_at,
                relationships_fetched_at=checked_at,
                last_error=None,
            )
        except (requests.RequestException, MissingCurlPatternError) as exc:
            logger.warning(
                "Live accessibility check failed for %s: %s",
                target_profile_id,
                exc,
            )
            db_service.upsert_target_profile(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                target_profile_id=target_profile_id,
                username=existing.get("username"),
                full_name=existing.get("full_name"),
                follower_count=existing.get("follower_count"),
                following_count=existing.get("following_count"),
                is_private=existing.get("is_private"),
                is_verified=existing.get("is_verified"),
                me_following_account=existing.get("me_following_account"),
                being_followed_by_account=existing.get("being_followed_by_account"),
                is_deactivated=existing.get("is_deactivated"),
                fetch_status=str(existing.get("fetch_status") or "partial"),
                metadata_fetched_at=existing.get("metadata_fetched_at"),
                relationships_fetched_at=checked_at,
                last_error=str(exc)[:500],
            )
            continue

        result[target_profile_id] = is_deactivated

    return result, checked_ids


def apply_account_accessibility_to_unfollowers(
    payload: dict,
    deactivated_map: dict[str, bool],
) -> int:
    updated = 0
    rows = payload.get("unfollowers")
    if not isinstance(rows, list):
        return 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        profile_id = str(row.get("pk_id") or "").strip()
        if not profile_id or profile_id not in deactivated_map:
            continue
        new_value = bool(deactivated_map[profile_id])
        if row.get("account_not_accessible") != new_value:
            updated += 1
        row["account_not_accessible"] = new_value
    return updated


def load_diff_payload(diff_id: str) -> dict | None:
    return db_service.get_diff_by_id(diff_id)


def write_diff_payload(diff_id: str, payload: dict) -> Path:
    diff_file_path = get_diff_file_path(diff_id)
    if not diff_file_path:
        raise FileNotFoundError(f"Diff file path not found for diff_id={diff_id}")
    diff_path = Path(diff_file_path)
    with diff_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
        f.write("\n")
    return diff_path


def enrich_diff_accessibility_for_scan(
    *,
    app_user_id: str,
    reference_profile_id: str,
    profile: ii.InstagramProfile,
    diff_id: str,
) -> DiffAccessibilityResult:
    payload = load_diff_payload(diff_id)
    if not payload:
        return {
            "seeded_profiles": 0,
            "reactivated_profile_ids": set(),
            "checked_profile_ids": set(),
            "updated_rows": 0,
            "diff_path": None,
        }

    seeded_profiles = seed_target_profiles_from_diff_payload(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        payload=payload,
    )
    reactivated_profile_ids = reactivate_returned_accounts(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        new_followers=_extract_records(payload, "new_followers"),
    )
    unfollowers = payload.get("unfollowers")
    target_profile_ids = set()
    if isinstance(unfollowers, list):
        target_profile_ids = {
            str(row.get("pk_id") or "").strip()
            for row in unfollowers
            if isinstance(row, dict) and str(row.get("pk_id") or "").strip()
        }
    deactivated_map: dict[str, bool] = {}
    checked_profile_ids: set[str] = set()
    if target_profile_ids:
        deactivated_map, checked_profile_ids = live_deactivated_map(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            profile=profile,
            target_profile_ids=target_profile_ids,
            caller_service="scan_flow",
            caller_method="enrich_diff_accessibility_for_scan",
        )
    updated_rows = apply_account_accessibility_to_unfollowers(payload, deactivated_map)
    diff_path = write_diff_payload(diff_id, payload)
    logger.info(
        "Updated diff accessibility for %s: seeded=%s reactivated=%s checked=%s updated_rows=%s",
        diff_id,
        seeded_profiles,
        len(reactivated_profile_ids),
        len(checked_profile_ids),
        updated_rows,
    )
    return {
        "seeded_profiles": seeded_profiles,
        "reactivated_profile_ids": reactivated_profile_ids,
        "checked_profile_ids": checked_profile_ids,
        "updated_rows": updated_rows,
        "diff_path": diff_path,
    }


def enrich_diff_accessibility_once(
    *,
    app_user_id: str,
    reference_profile_id: str,
    profile: ii.InstagramProfile,
    diff_id: str,
) -> DiffAccessibilityResult:
    payload = load_diff_payload(diff_id)
    if not payload:
        raise FileNotFoundError(f"Diff payload not found for diff_id={diff_id}")

    seeded_profiles = seed_target_profiles_from_diff_payload(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        payload=payload,
    )
    unfollowers = payload.get("unfollowers")
    target_profile_ids = set()
    if isinstance(unfollowers, list):
        target_profile_ids = {
            str(row.get("pk_id") or "").strip()
            for row in unfollowers
            if isinstance(row, dict) and str(row.get("pk_id") or "").strip()
        }
    deactivated_map: dict[str, bool] = {}
    checked_profile_ids: set[str] = set()
    if target_profile_ids:
        deactivated_map, checked_profile_ids = live_deactivated_map(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            profile=profile,
            target_profile_ids=target_profile_ids,
            caller_service="backfill_diff_accessibility_once",
            caller_method="enrich_diff_accessibility_once",
        )
    updated_rows = apply_account_accessibility_to_unfollowers(payload, deactivated_map)
    diff_path = write_diff_payload(diff_id, payload)
    return {
        "seeded_profiles": seeded_profiles,
        "reactivated_profile_ids": set(),
        "checked_profile_ids": checked_profile_ids,
        "updated_rows": updated_rows,
        "diff_path": diff_path,
    }
