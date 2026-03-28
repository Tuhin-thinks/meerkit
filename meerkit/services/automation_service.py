"""
Automation domain service.

Handles candidate normalization, safelist management, batch follow/unfollow
prepare flows, and per-item execution delegates (called by the worker).
"""

import random as _random
import re as _re
import threading
import time
from datetime import datetime
from uuid import uuid4

import insta_interface as ii
from meerkit.config import (
    AUTOMATION_INTER_ACTION_DELAY_SECONDS as _INTER_ACTION_DELAY_SECONDS,
)
from meerkit.config import (
    AUTOMATION_INTER_ACTION_JITTER_SECONDS as _INTER_ACTION_JITTER_SECONDS,
)
from meerkit.extensions import automation_action_queue
from meerkit.services import db_service
from meerkit.services.account_handler import (
    _build_profile,
    _extract_username_from_target_input,
)
from meerkit.services.instagram_gateway import instagram_gateway

_USER_ID_RE = _re.compile(r"^\d+$")
_USERNAME_RE = _re.compile(r"^[A-Za-z0-9._]+$")
_THREAD_LOCAL = threading.local()


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


def _resolve_identity_to_user_id(
    *,
    app_user_id: str,
    reference_profile_id: str,
    instagram_user: dict,
    normalized_username: str | None,
) -> str | None:
    if not normalized_username:
        return None
    profile = _get_cached_profile(instagram_user)
    return instagram_gateway.resolve_target_user_pk_for_automation(
        app_user_id=app_user_id,
        instagram_user_id=reference_profile_id,
        profile=profile,
        username=normalized_username,
        caller_service="automation_service",
        caller_method="_resolve_identity_to_user_id",
    )


def _parse_unique_linkedin_accounts(raw_lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_lines:
        candidate = str(raw).strip()
        if not candidate:
            continue
        dedup_key = candidate.lower()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        result.append(candidate)
    return result


def _run_discovery_for_identity_keys(
    *,
    app_user_id: str,
    instagram_user: dict,
    identity_keys: list[str],
) -> dict:
    from meerkit.services import account_handler

    queued_prediction_ids: list[str] = []
    queued_task_ids: list[str] = []
    skipped_identity_keys: list[str] = []

    for identity_key in identity_keys:
        try:
            payload = account_handler.request_followback_prediction(
                app_user_id=app_user_id,
                instagram_user=instagram_user,
                user_id=identity_key if _USER_ID_RE.fullmatch(identity_key) else None,
                username=None if _USER_ID_RE.fullmatch(identity_key) else identity_key,
                refresh=True,
                force_background=True,
            )
            prediction = payload.get("prediction") or {}
            task = payload.get("task") or {}
            prediction_id = prediction.get("prediction_id")
            task_id = task.get("task_id")
            if isinstance(prediction_id, str):
                queued_prediction_ids.append(prediction_id)
            if isinstance(task_id, str):
                queued_task_ids.append(task_id)
        except Exception:
            skipped_identity_keys.append(identity_key)

    return {
        "queued_prediction_ids": queued_prediction_ids,
        "queued_task_ids": queued_task_ids,
        "queued_count": len(queued_prediction_ids),
        "skipped_discovery_identity_keys": skipped_identity_keys,
    }


def add_alt_account_links(
    *,
    app_user_id: str,
    reference_profile_id: str,
    primary_raw_input: str,
    alt_raw_lines: list[str],
    linkedin_raw_lines: list[str] | None = None,
    trigger_discovery: bool = False,
    instagram_user: dict | None = None,
) -> dict:
    primary_username, primary_user_id, primary_identity_key = normalize_input_entry(
        primary_raw_input
    )
    if not primary_identity_key:
        raise ValueError("primary_account is invalid")

    if instagram_user and primary_username and not primary_user_id:
        resolved_primary = _resolve_identity_to_user_id(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            instagram_user=instagram_user,
            normalized_username=primary_username,
        )
        if resolved_primary:
            primary_user_id = resolved_primary
            primary_identity_key = resolved_primary

    normalized_alt_entries = bulk_normalize_entries(alt_raw_lines)
    linkedin_accounts = _parse_unique_linkedin_accounts(linkedin_raw_lines or [])

    db_service.upsert_primary_account_registry_entry(
        primary_id=str(uuid4()),
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_raw_input=primary_raw_input.strip(),
        primary_normalized_username=primary_username,
        primary_normalized_user_id=primary_user_id,
        primary_identity_key=primary_identity_key,
        linkedin_accounts=linkedin_accounts,
    )

    added = 0
    skipped_invalid = 0
    discovery_identity_keys: list[str] = [primary_identity_key]

    for alt_entry in normalized_alt_entries:
        if not alt_entry["is_valid"]:
            skipped_invalid += 1
            continue

        alt_username = alt_entry.get("normalized_username")
        alt_user_id = alt_entry.get("normalized_user_id")
        alt_identity_key = alt_entry.get("identity_key")

        if instagram_user and alt_username and not alt_user_id:
            resolved_alt = _resolve_identity_to_user_id(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                instagram_user=instagram_user,
                normalized_username=alt_username,
            )
            if resolved_alt:
                alt_user_id = resolved_alt
                alt_identity_key = resolved_alt

        if not alt_identity_key:
            skipped_invalid += 1
            continue
        if alt_identity_key == primary_identity_key:
            skipped_invalid += 1
            continue

        db_service.upsert_alt_account_link(
            link_id=str(uuid4()),
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            primary_raw_input=primary_raw_input.strip(),
            primary_normalized_username=primary_username,
            primary_normalized_user_id=primary_user_id,
            primary_identity_key=primary_identity_key,
            alt_raw_input=alt_entry["raw_input"],
            alt_normalized_username=alt_username,
            alt_normalized_user_id=alt_user_id,
            alt_identity_key=alt_identity_key,
        )
        added += 1
        if alt_identity_key not in discovery_identity_keys:
            discovery_identity_keys.append(alt_identity_key)

    entries = db_service.list_alt_account_links(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_identity_key=primary_identity_key,
    )
    primary_entry = db_service.get_primary_account_registry_entry(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_identity_key=primary_identity_key,
    )

    discovery_result = {
        "queued_prediction_ids": [],
        "queued_task_ids": [],
        "queued_count": 0,
        "skipped_discovery_identity_keys": [],
    }
    if trigger_discovery and instagram_user:
        discovery_result = _run_discovery_for_identity_keys(
            app_user_id=app_user_id,
            instagram_user=instagram_user,
            identity_keys=discovery_identity_keys,
        )

    return {
        "primary_identity_key": primary_identity_key,
        "added": added,
        "skipped_invalid": skipped_invalid,
        "linkedin_accounts": primary_entry.get("linkedin_accounts", [])
        if primary_entry
        else linkedin_accounts,
        "entries": entries,
        "total": len(entries),
        "discovery": discovery_result,
    }


def list_alt_links(
    app_user_id: str,
    reference_profile_id: str,
    primary_identity_key: str | None = None,
) -> list[dict]:
    entries = db_service.list_alt_account_links(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_identity_key=primary_identity_key,
    )
    primary_entries = db_service.list_primary_account_registry_entries(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_identity_key=primary_identity_key,
    )
    linkedin_by_primary = {
        entry.get("primary_identity_key"): entry.get("linkedin_accounts", [])
        for entry in primary_entries
        if isinstance(entry.get("primary_identity_key"), str)
    }
    for entry in entries:
        primary_key = entry.get("primary_identity_key")
        if isinstance(primary_key, str):
            entry["linkedin_accounts"] = linkedin_by_primary.get(primary_key, [])
    existing_primary_keys = {
        entry.get("primary_identity_key")
        for entry in entries
        if isinstance(entry.get("primary_identity_key"), str)
    }
    for primary_entry in primary_entries:
        primary_key = primary_entry.get("primary_identity_key")
        if not isinstance(primary_key, str) or primary_key in existing_primary_keys:
            continue
        entries.append(
            {
                "link_id": f"primary::{primary_key}",
                "app_user_id": app_user_id,
                "reference_profile_id": reference_profile_id,
                "primary_raw_input": primary_entry.get("primary_raw_input")
                or primary_key,
                "primary_normalized_username": primary_entry.get(
                    "primary_normalized_username"
                ),
                "primary_normalized_user_id": primary_entry.get(
                    "primary_normalized_user_id"
                ),
                "primary_identity_key": primary_key,
                "alt_raw_input": None,
                "alt_normalized_username": None,
                "alt_normalized_user_id": None,
                "alt_identity_key": None,
                "create_date": primary_entry.get("create_date") or _now_iso(),
                "linkedin_accounts": primary_entry.get("linkedin_accounts", []),
            }
        )
    return entries


def remove_alt_link(
    *,
    app_user_id: str,
    reference_profile_id: str,
    primary_identity_key: str,
    alt_identity_key: str,
) -> bool:
    return db_service.delete_alt_account_link(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_identity_key=primary_identity_key,
        alt_identity_key=alt_identity_key,
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
    instagram_user: dict | None,
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
    candidate_identity_aliases: list[set[str]] = []
    all_candidate_identity_keys: set[str] = set()
    for entry in candidates:
        identity_keys = {entry["identity_key"]} if entry.get("identity_key") else set()
        if (
            instagram_user
            and entry.get("is_valid")
            and not entry.get("normalized_user_id")
            and entry.get("normalized_username")
        ):
            resolved_user_id = _resolve_identity_to_user_id(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                instagram_user=instagram_user,
                normalized_username=entry["normalized_username"],
            )
            if resolved_user_id:
                entry["normalized_user_id"] = resolved_user_id
                identity_keys.add(resolved_user_id)
        candidate_identity_aliases.append(identity_keys)
        all_candidate_identity_keys.update(identity_keys)

    linked_alt_identity_keys_by_primary = (
        db_service.get_alt_identity_keys_map_for_primary_keys(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            primary_identity_keys=all_candidate_identity_keys,
        )
    )
    active_follower_ids = db_service.get_target_profile_relationship_ids(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=reference_profile_id,
        relationship_type="followers",
    )

    selected: list[dict] = []
    excluded: list[dict] = []

    for index, entry in enumerate(candidates):
        if not entry["is_valid"]:
            excluded.append({**entry, "exclusion_reason": "invalid_input"})
            continue
        if entry["identity_key"] in combined_exclusion_keys:
            excluded.append({**entry, "exclusion_reason": "safelist"})
            continue

        candidate_alt_keys: set[str] = set()
        for key in candidate_identity_aliases[index]:
            candidate_alt_keys.update(
                linked_alt_identity_keys_by_primary.get(key, set())
            )
        if candidate_alt_keys and (candidate_alt_keys & active_follower_ids):
            excluded.append(
                {
                    **entry,
                    "exclusion_reason": "alternative_account_follows_you",
                }
            )
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


def prepare_left_right_compare(
    *,
    app_user_id: str,
    reference_profile_id: str,
    instagram_user: dict | None,
    left_lines: list[str],
    right_lines: list[str],
    config: dict,
) -> dict:
    """Stage a left-right follower comparison action.

    For each left profile, execution checks whether each right profile is present
    in the left profile's followers list (right -> left direction).
    """
    max_left_count = int(config.get("max_left_count") or 50)
    max_right_count = int(config.get("max_right_count") or 500)

    if max_left_count < 1 or max_right_count < 1:
        raise ValueError("max_left_count and max_right_count must be >= 1")

    left_candidates = bulk_normalize_entries(left_lines)
    right_candidates = bulk_normalize_entries(right_lines)

    left_selected: list[dict] = []
    left_excluded: list[dict] = []
    right_selected: list[dict] = []
    right_excluded: list[dict] = []

    for entry in left_candidates:
        if not entry["is_valid"]:
            left_excluded.append({**entry, "exclusion_reason": "invalid_input"})
            continue
        if len(left_selected) >= max_left_count:
            left_excluded.append({**entry, "exclusion_reason": "cap_reached"})
            continue
        left_selected.append(entry)

    for entry in right_candidates:
        if not entry["is_valid"]:
            right_excluded.append({**entry, "exclusion_reason": "invalid_input"})
            continue
        if len(right_selected) >= max_right_count:
            right_excluded.append({**entry, "exclusion_reason": "cap_reached"})
            continue
        right_selected.append(entry)

    if not left_selected:
        raise ValueError("No valid left-side targets were provided")
    if not right_selected:
        raise ValueError("No valid right-side targets were provided")

    if instagram_user:
        for entry in right_selected:
            if entry.get("normalized_user_id") or not entry.get("normalized_username"):
                continue
            resolved_right = _resolve_identity_to_user_id(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                instagram_user=instagram_user,
                normalized_username=entry["normalized_username"],
            )
            if resolved_right:
                entry["normalized_user_id"] = resolved_right

    action_id = str(uuid4())

    right_targets_config = [
        {
            "raw_input": e["raw_input"],
            "display_username": e.get("normalized_username")
            or e.get("normalized_user_id"),
            "normalized_username": e.get("normalized_username"),
            "normalized_user_id": e.get("normalized_user_id"),
            "identity_key": e.get("identity_key"),
        }
        for e in right_selected
    ]

    comparison_result = {
        "schema_version": 1,
        "status": "staged",
        "left_rows": [],
        "right_targets": right_targets_config,
        "totals": {
            "left_total": len(left_selected),
            "right_total": len(right_selected),
            "relations_total": len(left_selected) * len(right_selected),
            "follows_total": 0,
            "missing_total": len(left_selected) * len(right_selected),
            "unresolved_total": 0,
        },
    }

    db_service.create_automation_action(
        action_id=action_id,
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        action_type="left_right_compare",
        status="staged",
        config={
            **config,
            "max_left_count": max_left_count,
            "max_right_count": max_right_count,
            "comparison_result": comparison_result,
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
        for e in left_selected
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
        for e in left_excluded
    ]

    db_service.insert_automation_action_items(item_rows)
    db_service.update_automation_action(
        action_id,
        total_items=len(left_selected),
        skipped_items=len(left_excluded),
    )

    return {
        "action_id": action_id,
        "action_type": "left_right_compare",
        "status": "staged",
        "selected_count": len(left_selected),
        "excluded_count": len(left_excluded),
        "right_selected_count": len(right_selected),
        "right_excluded_count": len(right_excluded),
        "selected_items": [
            {
                "raw_input": e["raw_input"],
                "display_username": e.get("normalized_username")
                or e.get("normalized_user_id"),
            }
            for e in left_selected
        ],
        "excluded_items": [
            {
                "raw_input": e["raw_input"],
                "exclusion_reason": e.get("exclusion_reason"),
            }
            for e in left_excluded
        ],
        "right_excluded_items": [
            {
                "raw_input": e["raw_input"],
                "exclusion_reason": e.get("exclusion_reason"),
            }
            for e in right_excluded
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


def execute_left_right_compare_item(
    *,
    item: dict,
    instagram_user: dict,
    app_user_id: str,
) -> bool:
    """Execute one left-side comparison item against all right-side targets."""
    item_id = item["item_id"]
    action_id = item["action_id"]
    db_service.update_automation_action_item(item_id, status="running")

    left_user_id = _resolve_item_user_id(item, instagram_user, app_user_id)
    if not left_user_id:
        db_service.update_automation_action_item(
            item_id,
            status="error",
            error="Could not resolve left-side target user ID",
            executed_at=_now_iso(),
        )
        return False

    left_display = (
        item.get("normalized_username") or item.get("display_username") or left_user_id
    )

    profile = _get_cached_profile(instagram_user)
    try:
        left_followers = instagram_gateway.get_target_followers_v2(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user["instagram_user_id"],
            profile=profile,
            target_user_id=left_user_id,
            caller_service="automation_service",
            caller_method="execute_left_right_compare_item",
        )
    except Exception as exc:
        db_service.update_automation_action_item(
            item_id,
            status="error",
            error=f"Failed fetching followers for {left_display}: {exc}",
            executed_at=_now_iso(),
        )
        return False

    follower_ids = {record.pk_id for record in left_followers}
    action = db_service.get_automation_action(action_id)
    config = (action or {}).get("config") or {}
    comparison_result = dict(config.get("comparison_result") or {})
    right_targets = list(comparison_result.get("right_targets") or [])

    updated_right_targets: list[dict] = []
    connections: list[dict] = []
    follows_count = 0
    unresolved_count = 0

    for target in right_targets:
        right_target = dict(target)
        right_user_id = right_target.get("normalized_user_id")
        right_username = right_target.get("normalized_username")

        if not right_user_id and right_username:
            resolved_right = _resolve_identity_to_user_id(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user["instagram_user_id"],
                instagram_user=instagram_user,
                normalized_username=right_username,
            )
            if resolved_right:
                right_user_id = resolved_right
                right_target["normalized_user_id"] = resolved_right

        is_following = bool(right_user_id and right_user_id in follower_ids)
        if is_following:
            follows_count += 1
        if not right_user_id:
            unresolved_count += 1

        connections.append(
            {
                "right_identity_key": right_target.get("identity_key"),
                "right_display": right_target.get("display_username")
                or right_target.get("normalized_username")
                or right_target.get("normalized_user_id"),
                "right_user_id": right_user_id,
                "is_following": is_following,
                "resolved": bool(right_user_id),
            }
        )
        updated_right_targets.append(right_target)

    missing_count = len(connections) - follows_count

    left_row = {
        "left_item_id": item_id,
        "left_raw_input": item.get("raw_input"),
        "left_display": left_display,
        "left_user_id": left_user_id,
        "left_followers_count": len(left_followers),
        "follows_count": follows_count,
        "missing_count": missing_count,
        "unresolved_count": unresolved_count,
        "connections": connections,
    }

    existing_rows = [
        row
        for row in list(comparison_result.get("left_rows") or [])
        if row.get("left_item_id") != item_id
    ]
    existing_rows.append(left_row)

    total_follows = sum(int(row.get("follows_count") or 0) for row in existing_rows)
    total_missing = sum(int(row.get("missing_count") or 0) for row in existing_rows)
    total_unresolved = sum(
        int(row.get("unresolved_count") or 0) for row in existing_rows
    )

    totals = dict(comparison_result.get("totals") or {})
    totals["left_total"] = int(totals.get("left_total") or len(existing_rows))
    totals["right_total"] = int(totals.get("right_total") or len(updated_right_targets))
    totals["relations_total"] = int(
        totals.get("relations_total") or totals["left_total"] * totals["right_total"]
    )
    totals["follows_total"] = total_follows
    totals["missing_total"] = total_missing
    totals["unresolved_total"] = total_unresolved

    comparison_result.update(
        {
            "status": "running",
            "left_rows": existing_rows,
            "right_targets": updated_right_targets,
            "totals": totals,
        }
    )

    config["comparison_result"] = comparison_result
    db_service.update_automation_action(action_id, config_json=config)
    db_service.update_automation_action_item(
        item_id,
        status="completed",
        result_json=left_row,
        executed_at=_now_iso(),
    )
    return True


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
