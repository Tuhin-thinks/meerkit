"""
Automation domain service.

Handles candidate normalization, safelist management, batch follow/unfollow
prepare flows, and per-item execution delegates (called by the worker).
"""

import re as _re
import threading
import time
from datetime import datetime, timedelta
from uuid import uuid4

import insta_interface as ii
from backend.extensions import automation_action_queue
from backend.services import db_service
from backend.services.account_handler import (
    _build_profile,
    _extract_username_from_target_input,
    _normalize_prediction_target_input,
)
from backend.services.instagram_gateway import instagram_gateway

_USER_ID_RE = _re.compile(r"^\d+$")
_USERNAME_RE = _re.compile(r"^[A-Za-z0-9._]+$")
_THREAD_LOCAL = threading.local()


# Delay between individual follow/unfollow actions (seconds).
_INTER_ACTION_DELAY_SECONDS = 3.0
# Extra jitter ceiling on top of the base delay (seconds).
_INTER_ACTION_JITTER_SECONDS = 4.0

import random as _random


def _now_iso() -> str:
    return datetime.now().isoformat()


# ── Normalization ──────────────────────────────────────────────────────────────


def normalize_input_entry(raw: str) -> tuple[str | None, str | None, str | None]:
    """Normalize one raw input entry into (username, user_id, identity_key).

    identity_key is normalized_user_id if we got a numeric id, else username.
    Returns (None, None, None) when the input cannot be parsed.
    """
    extracted = _extract_username_from_target_input(raw)
    if not extracted:
        return None, None, None

    if _USER_ID_RE.fullmatch(extracted):
        return None, extracted, extracted

    # Reject strings that contain characters invalid for Instagram usernames.
    if not _USERNAME_RE.fullmatch(extracted):
        return None, None, None

    return extracted, None, extracted


def bulk_normalize_entries(raw_lines: list[str]) -> list[dict]:
    """Normalize and deduplicate a list of raw input strings.

    Returns a list of dicts with keys: raw_input, normalized_username,
    normalized_user_id, identity_key, is_valid.
    """
    seen: set[str] = set()
    result: list[dict] = []
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            continue
        username, user_id, identity_key = normalize_input_entry(stripped)
        is_valid = identity_key is not None
        dedup_key = identity_key or stripped.lower()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        result.append(
            {
                "raw_input": stripped,
                "normalized_username": username,
                "normalized_user_id": user_id,
                "identity_key": identity_key,
                "is_valid": is_valid,
            }
        )
    return result


# ── Safelist management ────────────────────────────────────────────────────────


def sync_safelist(
    *,
    app_user_id: str,
    reference_profile_id: str,
    list_type: str,
    raw_lines: list[str],
) -> dict:
    """Replace the safelist for (app_user_id, reference_profile_id, list_type) with
    the supplied entries. Returns counts: added, skipped_invalid, total."""
    if list_type not in {"do_not_follow", "never_unfollow"}:
        raise ValueError("list_type must be do_not_follow or never_unfollow")

    normalized = bulk_normalize_entries(raw_lines)
    added = 0
    skipped_invalid = 0

    for entry in normalized:
        if not entry["is_valid"]:
            skipped_invalid += 1
            continue
        db_service.upsert_safelist_entry(
            safelist_id=str(uuid4()),
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            list_type=list_type,
            raw_input=entry["raw_input"],
            normalized_username=entry["normalized_username"],
            normalized_user_id=entry["normalized_user_id"],
            identity_key=entry["identity_key"],
        )
        added += 1

    existing = db_service.list_safelist_entries(
        app_user_id, reference_profile_id, list_type
    )
    return {"added": added, "skipped_invalid": skipped_invalid, "total": len(existing)}


def add_safelist_entries(
    *,
    app_user_id: str,
    reference_profile_id: str,
    list_type: str,
    raw_lines: list[str],
) -> dict:
    """Append entries to a safelist without removing existing ones."""
    if list_type not in {"do_not_follow", "never_unfollow"}:
        raise ValueError("list_type must be do_not_follow or never_unfollow")

    normalized = bulk_normalize_entries(raw_lines)
    added = 0
    skipped_invalid = 0

    for entry in normalized:
        if not entry["is_valid"]:
            skipped_invalid += 1
            continue
        db_service.upsert_safelist_entry(
            safelist_id=str(uuid4()),
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            list_type=list_type,
            raw_input=entry["raw_input"],
            normalized_username=entry["normalized_username"],
            normalized_user_id=entry["normalized_user_id"],
            identity_key=entry["identity_key"],
        )
        added += 1

    existing = db_service.list_safelist_entries(
        app_user_id, reference_profile_id, list_type
    )
    return {"added": added, "skipped_invalid": skipped_invalid, "total": len(existing)}


def remove_safelist_entry(
    *,
    app_user_id: str,
    reference_profile_id: str,
    list_type: str,
    identity_key: str,
) -> bool:
    return db_service.delete_safelist_entry(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        list_type=list_type,
        identity_key=identity_key,
    )


def list_safelist(
    app_user_id: str,
    reference_profile_id: str,
    list_type: str,
) -> list[dict]:
    return db_service.list_safelist_entries(
        app_user_id, reference_profile_id, list_type
    )


# ── Prepare: batch follow ──────────────────────────────────────────────────────


def prepare_batch_follow(
    *,
    app_user_id: str,
    reference_profile_id: str,
    candidate_lines: list[str],
    do_not_follow_lines: list[str],
    config: dict,
) -> dict:
    """Stage a batch follow action for confirmation.

    candidate_lines: raw entries pasted by user
    do_not_follow_lines: raw entries for in-request exclusions (merged with DB safelist)
    config: dict with keys max_follow_count (int), skip_private (bool), skip_no_recent_interaction (bool)

    Returns dict with action, selected_items, excluded_items counts and action_id.
    """
    max_follow_count: int = int(config.get("max_follow_count") or 50)

    # Merge DB safelist with in-request do_not_follow list
    db_dnf_keys = db_service.get_safelist_identity_keys(
        app_user_id, reference_profile_id, "do_not_follow"
    )
    request_dnf = bulk_normalize_entries(do_not_follow_lines)
    combined_exclusion_keys: set[str] = db_dnf_keys | {
        e["identity_key"] for e in request_dnf if e["is_valid"]
    }

    # Normalize candidates
    candidates = bulk_normalize_entries(candidate_lines)

    selected: list[dict] = []
    excluded: list[dict] = []

    for entry in candidates:
        if not entry["is_valid"]:
            excluded.append({**entry, "exclusion_reason": "invalid_input"})
            continue
        if entry["identity_key"] in combined_exclusion_keys:
            excluded.append({**entry, "exclusion_reason": "safelist"})
            continue
        if len(selected) >= max_follow_count:
            excluded.append({**entry, "exclusion_reason": "cap_reached"})
            continue
        selected.append(entry)

    # Persist
    action_id = str(uuid4())
    db_service.create_automation_action(
        action_id=action_id,
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        action_type="batch_follow",
        status="staged",
        config={**config, "max_follow_count": max_follow_count},
    )

    now = _now_iso()
    item_rows = [
        {
            "item_id": str(uuid4()),
            "action_id": action_id,
            "app_user_id": app_user_id,
            "reference_profile_id": reference_profile_id,
            "raw_input": e["raw_input"],
            "normalized_username": e["normalized_username"],
            "normalized_user_id": e["normalized_user_id"],
            "display_username": e.get("normalized_username")
            or e.get("normalized_user_id"),
            "status": "pending",
            "exclusion_reason": None,
        }
        for e in selected
    ] + [
        {
            "item_id": str(uuid4()),
            "action_id": action_id,
            "app_user_id": app_user_id,
            "reference_profile_id": reference_profile_id,
            "raw_input": e["raw_input"],
            "normalized_username": e["normalized_username"],
            "normalized_user_id": e["normalized_user_id"],
            "display_username": e.get("normalized_username")
            or e.get("normalized_user_id"),
            "status": "skipped",
            "exclusion_reason": e.get("exclusion_reason"),
        }
        for e in excluded
    ]

    db_service.insert_automation_action_items(item_rows)
    db_service.update_automation_action(
        action_id,
        total_items=len(selected),
        skipped_items=len(excluded),
    )

    return {
        "action_id": action_id,
        "action_type": "batch_follow",
        "status": "staged",
        "selected_count": len(selected),
        "excluded_count": len(excluded),
        "selected_items": [
            {
                "raw_input": e["raw_input"],
                "display_username": e.get("normalized_username")
                or e.get("normalized_user_id"),
            }
            for e in selected
        ],
        "excluded_items": [
            {
                "raw_input": e["raw_input"],
                "exclusion_reason": e.get("exclusion_reason"),
            }
            for e in excluded
        ],
    }


# ── Prepare: batch unfollow ────────────────────────────────────────────────────


def prepare_batch_unfollow(
    *,
    app_user_id: str,
    reference_profile_id: str,
    candidate_lines: list[str],
    never_unfollow_lines: list[str],
    config: dict,
    use_auto_discovery: bool = False,
) -> dict:
    """Stage a batch unfollow action for confirmation.

    candidate_lines: raw entries pasted by user (can be empty if use_auto_discovery=True)
    never_unfollow_lines: raw in-request exclusions (merged with DB safelist)
    config: dict with max_unfollow_count (int), skip_mutual (bool), skip_recent (bool)
    use_auto_discovery: derive candidates from cached following-minus-followers if True
    """
    max_unfollow_count: int = int(config.get("max_unfollow_count") or 50)
    skip_mutual: bool = bool(config.get("skip_mutual", True))

    # Merge DB safelist with in-request list
    db_nu_keys = db_service.get_safelist_identity_keys(
        app_user_id, reference_profile_id, "never_unfollow"
    )
    request_nu = bulk_normalize_entries(never_unfollow_lines)
    combined_exclusion_keys: set[str] = db_nu_keys | {
        e["identity_key"] for e in request_nu if e["is_valid"]
    }

    if use_auto_discovery and not candidate_lines:
        # Derive candidates from relationship cache: following – followers – safelist
        following_ids = db_service.get_target_profile_relationship_ids(
            app_user_id, reference_profile_id, reference_profile_id, "following"
        )
        follower_ids = db_service.get_target_profile_relationship_ids(
            app_user_id, reference_profile_id, reference_profile_id, "followers"
        )
        non_followers = following_ids - follower_ids
        # Build synthetic candidate lines from derived IDs
        candidate_lines = list(non_followers)

    candidates = bulk_normalize_entries(candidate_lines)

    selected: list[dict] = []
    excluded: list[dict] = []

    for entry in candidates:
        if not entry["is_valid"]:
            excluded.append({**entry, "exclusion_reason": "invalid_input"})
            continue
        if entry["identity_key"] in combined_exclusion_keys:
            excluded.append({**entry, "exclusion_reason": "safelist"})
            continue
        if len(selected) >= max_unfollow_count:
            excluded.append({**entry, "exclusion_reason": "cap_reached"})
            continue
        selected.append(entry)

    action_id = str(uuid4())
    db_service.create_automation_action(
        action_id=action_id,
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        action_type="batch_unfollow",
        status="staged",
        config={
            **config,
            "max_unfollow_count": max_unfollow_count,
            "use_auto_discovery": use_auto_discovery,
        },
    )

    item_rows = [
        {
            "item_id": str(uuid4()),
            "action_id": action_id,
            "app_user_id": app_user_id,
            "reference_profile_id": reference_profile_id,
            "raw_input": e["raw_input"],
            "normalized_username": e["normalized_username"],
            "normalized_user_id": e["normalized_user_id"],
            "display_username": e.get("normalized_username")
            or e.get("normalized_user_id"),
            "status": "pending",
            "exclusion_reason": None,
        }
        for e in selected
    ] + [
        {
            "item_id": str(uuid4()),
            "action_id": action_id,
            "app_user_id": app_user_id,
            "reference_profile_id": reference_profile_id,
            "raw_input": e["raw_input"],
            "normalized_username": e["normalized_username"],
            "normalized_user_id": e["normalized_user_id"],
            "display_username": e.get("normalized_username")
            or e.get("normalized_user_id"),
            "status": "skipped",
            "exclusion_reason": e.get("exclusion_reason"),
        }
        for e in excluded
    ]

    db_service.insert_automation_action_items(item_rows)
    db_service.update_automation_action(
        action_id,
        total_items=len(selected),
        skipped_items=len(excluded),
    )

    return {
        "action_id": action_id,
        "action_type": "batch_unfollow",
        "status": "staged",
        "selected_count": len(selected),
        "excluded_count": len(excluded),
        "selected_items": [
            {
                "raw_input": e["raw_input"],
                "display_username": e.get("normalized_username")
                or e.get("normalized_user_id"),
            }
            for e in selected
        ],
        "excluded_items": [
            {
                "raw_input": e["raw_input"],
                "exclusion_reason": e.get("exclusion_reason"),
            }
            for e in excluded
        ],
    }


# ── Confirm and enqueue ────────────────────────────────────────────────────────


def confirm_action(
    *,
    action_id: str,
    app_user_id: str,
    instagram_user: dict,
) -> dict:
    """Lock a staged action and enqueue it for execution.

    Returns updated action dict or raises ValueError on invalid state.
    """
    action = db_service.get_automation_action(action_id)
    if not action:
        raise ValueError(f"Action {action_id} not found")
    if action["app_user_id"] != app_user_id:
        raise ValueError("Action does not belong to the active user")
    if action["status"] != "staged":
        raise ValueError(
            f"Action {action_id} is not in staged state (status={action['status']})"
        )

    db_service.update_automation_action(
        action_id, status="queued", queued_at=_now_iso()
    )
    automation_action_queue.put(
        {
            "action_id": action_id,
            "app_user_id": app_user_id,
            "action_type": action["action_type"],
            "instagram_user": instagram_user,
        }
    )
    return db_service.get_automation_action(action_id)  # type: ignore[return-value]


# ── Execution (called by worker) ───────────────────────────────────────────────


def _resolve_item_user_id(
    item: dict,
    instagram_user: dict,
    app_user_id: str,
) -> str | None:
    """Resolve the target numeric user ID for an action item."""
    if item.get("normalized_user_id"):
        return item["normalized_user_id"]

    username = item.get("normalized_username")
    if not username:
        return None

    profile = _get_cached_profile(instagram_user)
    resolved = instagram_gateway.resolve_target_user_pk_for_automation(
        app_user_id=app_user_id,
        instagram_user_id=instagram_user["instagram_user_id"],
        profile=profile,
        username=username,
        caller_service="automation_service",
        caller_method="_resolve_item_user_id",
    )
    if resolved:
        db_service.update_automation_action_item(
            item["item_id"], normalized_user_id=resolved
        )
    return resolved


def execute_follow_item(
    *,
    item: dict,
    instagram_user: dict,
    app_user_id: str,
) -> bool:
    """Execute one follow action item. Returns True on success."""
    item_id = item["item_id"]
    db_service.update_automation_action_item(item_id, status="running")

    target_user_id = _resolve_item_user_id(item, instagram_user, app_user_id)
    if not target_user_id:
        db_service.update_automation_action_item(
            item_id,
            status="error",
            error="Could not resolve target user ID",
            executed_at=_now_iso(),
        )
        return False

    target_username = (
        item.get("normalized_username")
        or item.get("display_username")
        or target_user_id
    )
    profile = _get_cached_profile(instagram_user)

    result_code = instagram_gateway.follow_user_by_id(
        app_user_id=app_user_id,
        instagram_user_id=instagram_user["instagram_user_id"],
        profile=profile,
        target_user_id=target_user_id,
        target_username=target_username,
        caller_service="automation_service",
        caller_method="execute_follow_item",
    )

    if result_code == 1:
        db_service.update_automation_action_item(
            item_id,
            status="completed",
            result_json={"result_code": result_code},
            executed_at=_now_iso(),
        )
        return True

    db_service.update_automation_action_item(
        item_id,
        status="error",
        error=f"Follow returned code {result_code}",
        result_json={"result_code": result_code},
        executed_at=_now_iso(),
    )
    return False


def execute_unfollow_item(
    *,
    item: dict,
    instagram_user: dict,
    app_user_id: str,
) -> bool:
    """Execute one unfollow action item. Returns True on success."""
    item_id = item["item_id"]
    db_service.update_automation_action_item(item_id, status="running")

    target_user_id = _resolve_item_user_id(item, instagram_user, app_user_id)
    if not target_user_id:
        db_service.update_automation_action_item(
            item_id,
            status="error",
            error="Could not resolve target user ID",
            executed_at=_now_iso(),
        )
        return False

    target_username = (
        item.get("normalized_username")
        or item.get("display_username")
        or target_user_id
    )
    profile = _get_cached_profile(instagram_user)

    result_code = instagram_gateway.unfollow_user_by_id(
        app_user_id=app_user_id,
        instagram_user_id=instagram_user["instagram_user_id"],
        profile=profile,
        target_user_id=target_user_id,
        target_username=target_username,
        caller_service="automation_service",
        caller_method="execute_unfollow_item",
    )

    if result_code == 1:
        db_service.update_automation_action_item(
            item_id,
            status="completed",
            result_json={"result_code": result_code},
            executed_at=_now_iso(),
        )
        return True

    db_service.update_automation_action_item(
        item_id,
        status="error",
        error=f"Unfollow returned code {result_code}",
        result_json={"result_code": result_code},
        executed_at=_now_iso(),
    )
    return False


def inter_action_delay() -> None:
    """Sleep a conservative random delay between individual actions."""
    delay = _INTER_ACTION_DELAY_SECONDS + _random.uniform(
        0, _INTER_ACTION_JITTER_SECONDS
    )
    time.sleep(delay)


def _get_cached_profile(instagram_user: dict) -> ii.InstagramProfile:
    profile_cache = getattr(_THREAD_LOCAL, "profile_cache", None)
    if not isinstance(profile_cache, dict):
        profile_cache = {}
        _THREAD_LOCAL.profile_cache = profile_cache

    profile_key = str(instagram_user.get("instagram_user_id") or "")
    cached_profile = profile_cache.get(profile_key)
    if cached_profile is not None:
        return cached_profile

    profile = _build_profile(instagram_user)
    profile_cache[profile_key] = profile
    return profile
