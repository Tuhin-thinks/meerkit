"""
Automation API routes.

Endpoints:
  GET    /api/automation/following-users            — Fetch accounts the active profile follows
  POST   /api/automation/batch-follow/prepare       — Stage a batch follow action
  POST   /api/automation/batch-unfollow/prepare     — Stage a batch unfollow action
    POST   /api/automation/left-right-compare/prepare — Stage a left-right comparison action
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

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import local
from typing import cast

from flask import Blueprint, jsonify, request

from meerkit import config as backend_config
from meerkit.config import CACHE_DIR
from meerkit.routes import get_active_context
from meerkit.routes.error_mapping import map_exception_to_response
from meerkit.services import automation_runner, db_service
from meerkit.services.account_handler import _build_profile
from meerkit.services.automation_service import (
    add_alt_account_links,
    add_safelist_entries,
    confirm_action,
    list_alt_links,
    list_safelist,
    prepare_batch_follow,
    prepare_batch_unfollow,
    prepare_left_right_compare,
    remove_alt_link,
    remove_safelist_entry,
)
from meerkit.services.instagram_gateway import instagram_gateway
from meerkit.services.downloader import enqueue_image_download

bp = Blueprint("automation", __name__, url_prefix="/api/automation")
logger = logging.getLogger(__name__)


def _error_response(exc: Exception):
    body, status = map_exception_to_response(exc)
    return jsonify(body), status

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

    # Each category now has pre-separated api call and cache hit counts
    counts_by_base_category: dict[str, dict] = {
        str(cat.get("category") or ""): cat for cat in categories
    }

    per_category: list[dict[str, object]] = []
    all_time_hits_total = 0
    all_time_api_total = 0
    last_24h_hits_total = 0
    last_24h_api_total = 0

    for category in sorted(_READ_USAGE_CATEGORIES):
        cat_entry = counts_by_base_category.get(category, {})

        api_all_time = int(cat_entry.get("all_time_count") or 0)
        api_last_24h = int(cat_entry.get("last_24h_count") or 0)
        hit_all_time = int(cat_entry.get("cache_hits_all_time") or 0)
        hit_last_24h = int(cat_entry.get("cache_hits_last_24h") or 0)

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
        logger.exception("Failed to fetch following list from Instagram gateway")
        return _error_response(exc)

    follower_ids = {record.pk_id for record in follower_records}
    prefetch_metrics = _enqueue_following_profile_image_downloads(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        following_records=following_records,
    )
    logger.info(
        "Automation image prefetch queued=%s eligible=%s skipped_missing_pk=%s skipped_missing_url=%s app_user_id=%s profile_id=%s",
        prefetch_metrics["enqueued_count"],
        prefetch_metrics["eligible_count"],
        prefetch_metrics["skipped_missing_pk"],
        prefetch_metrics["skipped_missing_url"],
        app_user_id,
        reference_profile_id,
    )
    user_count_map = _load_following_user_counts_bulk(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        instagram_user=instagram_user,
        user_ids=[r.pk_id for r in following_records],
        force_refresh=force_refresh,
    )

    users = []
    for record in following_records:
        summary = user_count_map.get(
            record.pk_id,
            {
                "follower_count": None,
                "following_count": None,
                "being_followed_by_account": None,
            },
        )
        follows_you_signal = summary.get("being_followed_by_account")
        follows_you = (
            follows_you_signal
            if isinstance(follows_you_signal, bool)
            else record.pk_id in follower_ids
        )
        users.append(
            {
                "user_id": record.pk_id,
                "username": record.username,
                "full_name": record.full_name,
                "is_private": record.is_private,
                "profile_pic_url": record.profile_pic_url,
                "follows_you": follows_you,
                **summary,
            }
        )
    return jsonify(
        {
            "users": users,
            "total": len(users),
            "followers_total": len(follower_records),
            "following_total": len(following_records),
        }
    )


def _enqueue_following_profile_image_downloads(
    *,
    app_user_id: str,
    reference_profile_id: str,
    following_records: list,
) -> dict[str, int]:
    metrics = {
        "eligible_count": 0,
        "enqueued_count": 0,
        "skipped_missing_pk": 0,
        "skipped_missing_url": 0,
    }
    for record in following_records:
        metrics["eligible_count"] += 1
        pk_id = str(getattr(record, "pk_id", "") or "").strip()
        profile_pic_url = str(getattr(record, "profile_pic_url", "") or "").strip()
        if not pk_id:
            metrics["skipped_missing_pk"] += 1
            continue
        if not profile_pic_url:
            metrics["skipped_missing_url"] += 1
            continue
        enqueue_image_download(
            app_user_id,
            reference_profile_id,
            pk_id,
            profile_pic_url,
        )
        metrics["enqueued_count"] += 1
    return metrics


def _load_following_user_counts(
    *,
    app_user_id: str,
    reference_profile_id: str,
    profile,
    user_id: str,
    force_refresh: bool,
) -> dict[str, int | bool | None]:
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
        return {
            "follower_count": None,
            "following_count": None,
            "being_followed_by_account": None,
        }

    follower_count = summary.get("account_followers_count")
    following_count = summary.get("account_following_count")
    being_followed_by_account = summary.get("being_followed_by_account")
    return {
        "follower_count": follower_count if isinstance(follower_count, int) else None,
        "following_count": following_count
        if isinstance(following_count, int)
        else None,
        "being_followed_by_account": being_followed_by_account
        if isinstance(being_followed_by_account, bool)
        else None,
    }


def _load_following_user_counts_bulk(
    *,
    app_user_id: str,
    reference_profile_id: str,
    instagram_user: dict,
    user_ids: list[str],
    force_refresh: bool,
) -> dict[str, dict[str, int | bool | None]]:
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

    def _fetch_counts(user_id: str) -> tuple[str, dict[str, int | bool | None]]:
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

    counts_by_user: dict[str, dict[str, int | bool | None]] = {}
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
                    "being_followed_by_account": None,
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
    except Exception as exc:
        return _error_response(exc)

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
    except Exception as exc:
        return _error_response(exc)

    return jsonify(result), 201


@bp.post("/left-right-compare/prepare")
def prepare_left_right_follow_compare():
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    payload = request.get_json(silent=True) or {}
    left_lines: list[str] = payload.get("left_targets") or []
    right_lines: list[str] = payload.get("right_targets") or []
    config: dict = {
        "max_left_count": int(payload.get("max_left_count") or 50),
        "max_right_count": int(payload.get("max_right_count") or 500),
    }

    if not left_lines:
        return jsonify({"error": "left_targets list is required"}), 400
    if not right_lines:
        return jsonify({"error": "right_targets list is required"}), 400

    if config["max_left_count"] > 50:
        return jsonify({"error": "max_left_count cannot exceed 50"}), 400
    if config["max_right_count"] > 500:
        return jsonify({"error": "max_right_count cannot exceed 500"}), 400

    try:
        result = prepare_left_right_compare(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            instagram_user=instagram_user,
            left_lines=left_lines,
            right_lines=right_lines,
            config=config,
        )
    except Exception as exc:
        return _error_response(exc)

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
    except Exception as exc:
        return _error_response(exc)

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
                "normalized_username": item.get("normalized_username"),
                "normalized_user_id": item.get("normalized_user_id"),
                "raw_input": item.get("raw_input"),
                "status": s,
                "exclusion_reason": item.get("exclusion_reason"),
                "error": item.get("error"),
                "executed_at": item.get("executed_at"),
                "result": item.get("result"),
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

    action_type = request.args.get("action_type", type=str)
    requested_limit = request.args.get("limit", default=20, type=int)
    limit = min(max(requested_limit or 20, 1), 500)

    actions = automation_runner.list_active_actions(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        action_type=action_type,
        limit=limit,
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
    except Exception as exc:
        return _error_response(exc)

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
    except Exception as exc:
        return _error_response(exc)

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
