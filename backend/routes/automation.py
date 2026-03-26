"""
Automation API routes.

Endpoints:
  GET    /api/automation/following-users            — Fetch accounts the active profile follows
  POST   /api/automation/batch-follow/prepare       — Stage a batch follow action
  POST   /api/automation/batch-unfollow/prepare     — Stage a batch unfollow action
  POST   /api/automation/actions/<id>/confirm       — Confirm and enqueue staged action
  POST   /api/automation/actions/<id>/cancel        — Cancel a queued/running action
  GET    /api/automation/actions/<id>               — Get action status + item summary
  GET    /api/automation/actions                    — List actions for current scope
  GET    /api/automation/safelists/<list_type>      — List safelist entries
  POST   /api/automation/safelists/<list_type>      — Add entries to safelist
  DELETE /api/automation/safelists/<list_type>/<key> — Remove one safelist entry
    GET    /api/automation/alternative-account-links  — List alternative-account links
    POST   /api/automation/alternative-account-links  — Add alternative-account links
    DELETE /api/automation/alternative-account-links/<primary>/<alt> — Remove one alt link
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import local
from typing import cast

from flask import Blueprint, jsonify, request

from backend import config as backend_config
from backend.config import CACHE_DIR
from backend.routes import get_active_context
from backend.services import automation_runner, db_service
from backend.services.account_handler import _build_profile
from backend.services.automation_service import (
    add_alt_account_links,
    add_safelist_entries,
    confirm_action,
    list_alt_links,
    list_safelist,
    prepare_batch_follow,
    prepare_batch_unfollow,
    remove_alt_link,
    remove_safelist_entry,
)
from backend.services.instagram_gateway import instagram_gateway

bp = Blueprint("automation", __name__, url_prefix="/api/automation")

_VALID_LIST_TYPES = {"do_not_follow", "never_unfollow"}
_READ_USAGE_CATEGORIES = {
    "user_lookup",
    "user_data_fetch",
    "followers_discovery",
    "following_discovery",
}
_THREAD_LOCAL_PROFILE = local()


def _active_scope() -> tuple[str | None, dict | tuple[dict, int]]:
    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    return get_active_context(instagram_user_id)


def _query_flag(name: str) -> bool:
    value = (request.args.get(name) or "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _cache_scope_dir(app_user_id: str, reference_profile_id: str) -> Path:
    return CACHE_DIR / app_user_id / reference_profile_id


def _cache_size_summary(cache_scope_dir: Path) -> dict[str, int]:
    total_bytes = 0
    file_count = 0
    if cache_scope_dir.exists():
        for entry in cache_scope_dir.rglob("*"):
            if not entry.is_file():
                continue
            try:
                total_bytes += entry.stat().st_size
                file_count += 1
            except OSError:
                continue
    return {
        "cache_size_bytes": total_bytes,
        "cache_file_count": file_count,
    }


def _cache_efficiency_payload(app_user_id: str, reference_profile_id: str) -> dict:
    usage_summary = db_service.get_instagram_api_usage_summary(
        app_user_id=app_user_id,
        instagram_user_id=reference_profile_id,
    )

    categories = usage_summary.get("accounts", [{}])[0].get("categories", [])
    counts_by_category: dict[str, dict[str, int]] = {}
    for category_entry in categories:
        category_name = str(category_entry.get("category") or "")
        all_time_count = int(category_entry.get("all_time_count") or 0)
        last_24h_count = int(category_entry.get("last_24h_count") or 0)
        counts_by_category[category_name] = {
            "all_time_count": all_time_count,
            "last_24h_count": last_24h_count,
        }

    per_category: list[dict[str, object]] = []
    all_time_hits_total = 0
    all_time_api_total = 0
    last_24h_hits_total = 0
    last_24h_api_total = 0

    for category in sorted(_READ_USAGE_CATEGORIES):
        api_counts = counts_by_category.get(category, {})
        hit_counts = counts_by_category.get(f"{category}_cache_hit", {})

        api_all_time = int(api_counts.get("all_time_count") or 0)
        api_last_24h = int(api_counts.get("last_24h_count") or 0)
        hit_all_time = int(hit_counts.get("all_time_count") or 0)
        hit_last_24h = int(hit_counts.get("last_24h_count") or 0)

        all_time_reads = api_all_time + hit_all_time
        last_24h_reads = api_last_24h + hit_last_24h
        all_time_efficiency = (
            round((hit_all_time / all_time_reads) * 100, 2)
            if all_time_reads > 0
            else 0.0
        )
        last_24h_efficiency = (
            round((hit_last_24h / last_24h_reads) * 100, 2)
            if last_24h_reads > 0
            else 0.0
        )

        per_category.append(
            {
                "category": category,
                "all_time": {
                    "cache_hits": hit_all_time,
                    "api_calls": api_all_time,
                    "total_reads": all_time_reads,
                    "efficiency_percent": all_time_efficiency,
                },
                "last_24h": {
                    "cache_hits": hit_last_24h,
                    "api_calls": api_last_24h,
                    "total_reads": last_24h_reads,
                    "efficiency_percent": last_24h_efficiency,
                },
            }
        )

        all_time_hits_total += hit_all_time
        all_time_api_total += api_all_time
        last_24h_hits_total += hit_last_24h
        last_24h_api_total += api_last_24h

    all_time_reads_total = all_time_hits_total + all_time_api_total
    last_24h_reads_total = last_24h_hits_total + last_24h_api_total
    cache_scope_dir = _cache_scope_dir(app_user_id, reference_profile_id)
    cache_size = _cache_size_summary(cache_scope_dir)

    return {
        "generated_at": datetime.now().isoformat(),
        "instagram_user_id": reference_profile_id,
        "all_time": {
            "cache_hits": all_time_hits_total,
            "api_calls": all_time_api_total,
            "total_reads": all_time_reads_total,
            "efficiency_percent": round(
                (all_time_hits_total / all_time_reads_total) * 100,
                2,
            )
            if all_time_reads_total > 0
            else 0.0,
        },
        "last_24h": {
            "cache_hits": last_24h_hits_total,
            "api_calls": last_24h_api_total,
            "total_reads": last_24h_reads_total,
            "efficiency_percent": round(
                (last_24h_hits_total / last_24h_reads_total) * 100,
                2,
            )
            if last_24h_reads_total > 0
            else 0.0,
        },
        "cache_size": {
            **cache_size,
            "cache_scope": str(cache_scope_dir),
        },
        "per_category": per_category,
    }


@bp.get("/cache-efficiency")
def get_cache_efficiency():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]
    return jsonify(_cache_efficiency_payload(app_user_id, reference_profile_id))


@bp.get("/cache-size")
def get_cache_size():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]
    cache_scope_dir = _cache_scope_dir(app_user_id, reference_profile_id)
    size_payload = _cache_size_summary(cache_scope_dir)
    return jsonify(
        {
            "generated_at": datetime.now().isoformat(),
            "instagram_user_id": reference_profile_id,
            "cache_scope": str(cache_scope_dir),
            **size_payload,
        }
    )


# ── Following users ────────────────────────────────────────────────────────────


@bp.get("/following-users")
def get_following_users():
    """Fetch the list of accounts the active Instagram profile currently follows.

    This endpoint is cache-first and uses local cache snapshots for relationship
    records and profile counts. Set ?force_refresh=1 to bypass cache and fetch
    fresh data from Instagram.
    """
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]
    force_refresh = _query_flag("force_refresh")

    try:
        profile = _build_profile(instagram_user)
        following_records = instagram_gateway.get_current_following_v2(
            app_user_id=app_user_id,
            instagram_user_id=reference_profile_id,
            profile=profile,
            caller_service="automation",
            caller_method="get_following_users",
            force_refresh=force_refresh,
        )
        follower_records = instagram_gateway.get_current_followers_v2(
            app_user_id=app_user_id,
            instagram_user_id=reference_profile_id,
            profile=profile,
            caller_service="automation",
            caller_method="get_following_users",
            force_refresh=force_refresh,
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to fetch following list: {exc}"}), 502

    follower_ids = {record.pk_id for record in follower_records}
    user_count_map = _load_following_user_counts_bulk(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        instagram_user=instagram_user,
        user_ids=[r.pk_id for r in following_records],
        force_refresh=force_refresh,
    )

    users = [
        {
            "user_id": r.pk_id,
            "username": r.username,
            "full_name": r.full_name,
            "is_private": r.is_private,
            "profile_pic_url": r.profile_pic_url,
            "follows_you": r.pk_id in follower_ids,
            **user_count_map.get(
                r.pk_id,
                {"follower_count": None, "following_count": None},
            ),
        }
        for r in following_records
    ]
    return jsonify(
        {
            "users": users,
            "total": len(users),
            "followers_total": len(follower_records),
            "following_total": len(following_records),
        }
    )


def _load_following_user_counts(
    *,
    app_user_id: str,
    reference_profile_id: str,
    profile,
    user_id: str,
    force_refresh: bool,
) -> dict[str, int | None]:
    try:
        summary = instagram_gateway.get_target_user_data(
            app_user_id=app_user_id,
            instagram_user_id=reference_profile_id,
            profile=profile,
            target_user_id=user_id,
            caller_service="automation",
            caller_method="get_following_users",
            force_refresh=force_refresh,
        )
    except Exception:
        return {"follower_count": None, "following_count": None}

    follower_count = summary.get("account_followers_count")
    following_count = summary.get("account_following_count")
    return {
        "follower_count": follower_count if isinstance(follower_count, int) else None,
        "following_count": following_count
        if isinstance(following_count, int)
        else None,
    }


def _load_following_user_counts_bulk(
    *,
    app_user_id: str,
    reference_profile_id: str,
    instagram_user: dict,
    user_ids: list[str],
    force_refresh: bool,
) -> dict[str, dict[str, int | None]]:
    unique_user_ids = list(dict.fromkeys(user_ids))
    if not unique_user_ids:
        return {}

    configured_max = int(
        getattr(backend_config, "MAX_USER_DETAILS_FETCH_THREADS", 8) or 8
    )
    max_workers = max(1, min(configured_max, len(unique_user_ids)))
    if max_workers == 1:
        profile = _build_profile(instagram_user)
        return {
            user_id: _load_following_user_counts(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                profile=profile,
                user_id=user_id,
                force_refresh=force_refresh,
            )
            for user_id in unique_user_ids
        }

    def _fetch_counts(user_id: str) -> tuple[str, dict[str, int | None]]:
        profile = getattr(_THREAD_LOCAL_PROFILE, "profile", None)
        profile_owner = getattr(_THREAD_LOCAL_PROFILE, "profile_owner", None)
        if profile is None or profile_owner != reference_profile_id:
            profile = _build_profile(instagram_user)
            _THREAD_LOCAL_PROFILE.profile = profile
            _THREAD_LOCAL_PROFILE.profile_owner = reference_profile_id
        return (
            user_id,
            _load_following_user_counts(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                profile=profile,
                user_id=user_id,
                force_refresh=force_refresh,
            ),
        )

    counts_by_user: dict[str, dict[str, int | None]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch_counts, user_id): user_id
            for user_id in unique_user_ids
        }
        for future in as_completed(futures):
            user_id = futures[future]
            try:
                result_user_id, result_counts = future.result()
                counts_by_user[result_user_id] = result_counts
            except Exception:
                counts_by_user[user_id] = {
                    "follower_count": None,
                    "following_count": None,
                }

    return counts_by_user


# ── Prepare: batch follow ──────────────────────────────────────────────────────


@bp.post("/batch-follow/prepare")
def prepare_follow():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    payload = request.get_json(silent=True) or {}
    candidate_lines: list[str] = payload.get("candidates") or []
    do_not_follow_lines: list[str] = payload.get("do_not_follow") or []
    config: dict = {
        "max_follow_count": int(payload.get("max_follow_count") or 50),
        "skip_private": bool(payload.get("skip_private", False)),
        "skip_no_recent_interaction": bool(
            payload.get("skip_no_recent_interaction", False)
        ),
    }

    if not candidate_lines:
        return jsonify({"error": "candidates list is required"}), 400

    try:
        result = prepare_batch_follow(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            candidate_lines=candidate_lines,
            do_not_follow_lines=do_not_follow_lines,
            config=config,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result), 201


# ── Prepare: batch unfollow ────────────────────────────────────────────────────


@bp.post("/batch-unfollow/prepare")
def prepare_unfollow():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    payload = request.get_json(silent=True) or {}
    candidate_lines: list[str] = payload.get("candidates") or []
    never_unfollow_lines: list[str] = payload.get("never_unfollow") or []
    use_auto_discovery: bool = bool(payload.get("use_auto_discovery", False))
    config: dict = {
        "max_unfollow_count": int(payload.get("max_unfollow_count") or 50),
        "skip_mutual": bool(payload.get("skip_mutual", True)),
        "skip_recent": bool(payload.get("skip_recent", False)),
    }

    if not candidate_lines and not use_auto_discovery:
        return jsonify(
            {"error": "candidates list is required (or set use_auto_discovery=true)"}
        ), 400

    try:
        result = prepare_batch_unfollow(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            instagram_user=instagram_user,
            candidate_lines=candidate_lines,
            never_unfollow_lines=never_unfollow_lines,
            config=config,
            use_auto_discovery=use_auto_discovery,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result), 201


# ── Action lifecycle ───────────────────────────────────────────────────────────


@bp.post("/actions/<action_id>/confirm")
def confirm(action_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)

    try:
        result = confirm_action(
            action_id=action_id,
            app_user_id=app_user_id,
            instagram_user=instagram_user,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result), 202


@bp.post("/actions/<action_id>/cancel")
def cancel(action_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    action = db_service.get_automation_action(action_id)
    if not action:
        return jsonify({"error": "Action not found"}), 404
    if action["app_user_id"] != app_user_id:
        return jsonify({"error": "Action not found"}), 404

    result = automation_runner.cancel_action(action_id)
    return jsonify(result)


@bp.get("/actions/<action_id>")
def get_action(action_id: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    action = automation_runner.get_action_status(action_id)
    if not action:
        return jsonify({"error": "Action not found"}), 404
    if action["app_user_id"] != app_user_id:
        return jsonify({"error": "Action not found"}), 404

    # Include item summary broken down by status
    all_items = db_service.list_automation_action_items(action_id)
    by_status: dict[str, list[dict]] = {}
    for item in all_items:
        s = item.get("status") or "unknown"
        by_status.setdefault(s, []).append(
            {
                "item_id": item["item_id"],
                "display_username": item.get("display_username"),
                "raw_input": item.get("raw_input"),
                "status": s,
                "exclusion_reason": item.get("exclusion_reason"),
                "error": item.get("error"),
                "executed_at": item.get("executed_at"),
            }
        )

    return jsonify({**action, "items_by_status": by_status})


@bp.get("/actions")
def list_actions():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    actions = automation_runner.list_active_actions(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
    )
    return jsonify({"actions": actions, "total": len(actions)})


# ── Safelists ──────────────────────────────────────────────────────────────────


@bp.get("/safelists/<list_type>")
def get_safelist(list_type: str):
    if list_type not in _VALID_LIST_TYPES:
        return jsonify(
            {"error": f"list_type must be one of {sorted(_VALID_LIST_TYPES)}"}
        ), 400

    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    entries = list_safelist(app_user_id, reference_profile_id, list_type)
    return jsonify({"list_type": list_type, "entries": entries, "total": len(entries)})


@bp.post("/safelists/<list_type>")
def add_to_safelist(list_type: str):
    if list_type not in _VALID_LIST_TYPES:
        return jsonify(
            {"error": f"list_type must be one of {sorted(_VALID_LIST_TYPES)}"}
        ), 400

    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    payload = request.get_json(silent=True) or {}
    raw_lines: list[str] = payload.get("entries") or []
    if not raw_lines:
        return jsonify({"error": "entries list is required"}), 400

    try:
        result = add_safelist_entries(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            list_type=list_type,
            raw_lines=raw_lines,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result), 201


@bp.delete("/safelists/<list_type>/<path:identity_key>")
def delete_from_safelist(list_type: str, identity_key: str):
    if list_type not in _VALID_LIST_TYPES:
        return jsonify(
            {"error": f"list_type must be one of {sorted(_VALID_LIST_TYPES)}"}
        ), 400

    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    removed = remove_safelist_entry(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        list_type=list_type,
        identity_key=identity_key,
    )
    if not removed:
        return jsonify({"error": "Entry not found"}), 404

    return jsonify({"removed": True, "identity_key": identity_key})


# ── Alternative account links ────────────────────────────────────────────────


@bp.get("/alternative-account-links")
def get_alt_account_links():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]
    primary_identity_key = (
        request.args.get("primary_identity_key") or ""
    ).strip() or None

    entries = list_alt_links(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_identity_key=primary_identity_key,
    )
    return jsonify({"entries": entries, "total": len(entries)})


@bp.post("/alternative-account-links")
def add_alt_account_link_entries():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    payload = request.get_json(silent=True) or {}
    primary_account = (payload.get("primary_account") or "").strip()
    alternative_accounts = payload.get("alternative_accounts") or []
    linkedin_accounts = payload.get("linkedin_accounts") or []
    trigger_discovery = bool(payload.get("trigger_discovery", False))

    if not primary_account:
        return jsonify({"error": "primary_account is required"}), 400
    if not isinstance(alternative_accounts, list):
        return jsonify({"error": "alternative_accounts must be a list"}), 400
    if not isinstance(linkedin_accounts, list):
        return jsonify({"error": "linkedin_accounts must be a list"}), 400
    if not alternative_accounts and not linkedin_accounts:
        return jsonify(
            {
                "error": "Provide at least one alternative account or one LinkedIn account"
            }
        ), 400

    try:
        result = add_alt_account_links(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            primary_raw_input=primary_account,
            alt_raw_lines=alternative_accounts,
            linkedin_raw_lines=linkedin_accounts,
            trigger_discovery=trigger_discovery,
            instagram_user=instagram_user,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result), 201


@bp.delete(
    "/alternative-account-links/<path:primary_identity_key>/<path:alt_identity_key>"
)
def delete_alt_account_link_entry(primary_identity_key: str, alt_identity_key: str):
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    removed = remove_alt_link(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_identity_key=primary_identity_key,
        alt_identity_key=alt_identity_key,
    )
    if not removed:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify(
        {
            "removed": True,
            "primary_identity_key": primary_identity_key,
            "alt_identity_key": alt_identity_key,
        }
    )
