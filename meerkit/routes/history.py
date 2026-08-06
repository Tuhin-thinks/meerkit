from datetime import datetime, timedelta
from typing import Any, cast

from flask import Blueprint, jsonify, request

from meerkit.config import (
    ACCESSIBILITY_DB_STATUS_MAX_AGE_HOURS,
    HISTORY_ALL_TIME_DAYS,
    HISTORY_DEFAULT_DAYS,
    HISTORY_MAX_DAYS,
)
from meerkit.routes import get_active_context
from meerkit.services import account_handler, persistence
from meerkit.services import db_service as _db_service
from meerkit.services.db_service import get_scan_analytics, get_scan_history
from meerkit.services.diff_accessibility import (
    live_deactivated_map,
    seed_target_profiles_from_diff_payload,
    write_diff_payload,
)

bp = Blueprint("history", __name__, url_prefix="/api")

HISTORY_PAGE_SIZE_DEFAULT = 10
HISTORY_PAGE_SIZE_MAX = 200


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


def _fresh_db_is_deactivated(target_profile: dict[str, Any]) -> bool | None:
    if not target_profile:
        return None
    status_value = target_profile.get("is_deactivated")
    if status_value is None:
        return None

    updated_at = _parse_iso_timestamp(
        target_profile.get("updated_at") or target_profile.get("update_date")
    )
    if not updated_at:
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


from meerkit.services.account_handler import _build_profile


def _collect_target_profile_ids(diff: dict[str, Any], list_keys: set[str]) -> set[str]:
    target_profile_ids: set[str] = set()
    for key in list_keys:
        rows = diff.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            target_profile_id = str(row.get("pk_id") or "").strip()
            if target_profile_id:
                target_profile_ids.add(target_profile_id)
    return target_profile_ids


def _apply_accessibility_to_rows(
    diff: dict[str, Any],
    deactivated_map: dict[str, bool],
    *,
    list_keys: set[str],
) -> int:
    updated_rows = 0
    for key in list_keys:
        rows = diff.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            target_profile_id = str(row.get("pk_id") or "").strip()
            if not target_profile_id:
                continue
            if target_profile_id not in deactivated_map:
                continue
            new_value = bool(deactivated_map[target_profile_id])
            if row.get("account_not_accessible") != new_value:
                updated_rows += 1
            row["account_not_accessible"] = new_value
    return updated_rows


def _enrich_diff_with_alt_followback(
    diff: dict[str, Any] | None,
    *,
    app_user_id: str,
    reference_profile_id: str,
) -> dict[str, Any] | None:
    if not diff:
        return diff

    # Fetch the reference profile's last-scanned followers ONCE so we don't
    # issue a separate DB query for every row in the diff.
    reference_follower_ids: set[str] = _db_service.get_latest_scanned_profile_ids(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
    )

    enriched = dict(diff)
    for key in ("new_followers", "unfollowers"):
        rows = enriched.get(key)
        if not isinstance(rows, list):
            continue
        enriched_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            target_profile_id = str(row.get("pk_id") or "").strip()
            target_username = row.get("username")
            if not target_profile_id:
                enriched_rows.append(dict(row))
                continue
            target_profile = (
                _db_service.get_target_profile(
                    app_user_id=app_user_id,
                    reference_profile_id=reference_profile_id,
                    target_profile_id=target_profile_id,
                )
                or {}
            )
            latest_task = (
                _db_service.get_latest_prediction_task(
                    app_user_id=app_user_id,
                    reference_profile_id=reference_profile_id,
                    target_profile_id=target_profile_id,
                )
                or {}
            )
            db_is_deactivated = _fresh_db_is_deactivated(target_profile)
            if db_is_deactivated is None:
                account_not_accessible = bool(row.get("account_not_accessible", False))
                account_not_accessible = account_not_accessible or bool(
                    target_profile.get("last_error")
                )
                account_not_accessible = account_not_accessible or (
                    latest_task.get("status") == "error"
                    and bool(latest_task.get("error"))
                )
            else:
                account_not_accessible = db_is_deactivated
            enriched_rows.append(
                {
                    **row,
                    "account_not_accessible": account_not_accessible,
                    "alt_followback_assessment": account_handler.get_alt_followback_assessment_for_target(
                        app_user_id=app_user_id,
                        reference_profile_id=reference_profile_id,
                        target_profile_id=target_profile_id,
                        target_username=target_username
                        if isinstance(target_username, str)
                        else None,
                        reference_follower_ids=reference_follower_ids,
                    ),
                }
            )
        enriched[key] = enriched_rows
    return enriched


@bp.get("/history")
def history():
    app_user_id, context = get_active_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    history_range = (request.args.get("range") or "recent").strip().lower()

    try:
        requested_days = int(request.args.get("days", HISTORY_DEFAULT_DAYS))
    except (TypeError, ValueError):
        requested_days = HISTORY_DEFAULT_DAYS

    if history_range == "all_time":
        days = max(1, HISTORY_ALL_TIME_DAYS)
    else:
        max_days = max(1, HISTORY_MAX_DAYS)
        days = min(max(1, requested_days), max_days)

    try:
        requested_limit = int(request.args.get("limit", HISTORY_PAGE_SIZE_DEFAULT))
    except (TypeError, ValueError):
        requested_limit = HISTORY_PAGE_SIZE_DEFAULT
    limit = max(1, min(requested_limit, HISTORY_PAGE_SIZE_MAX))

    try:
        requested_offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        requested_offset = 0
    offset = max(0, requested_offset)

    return jsonify(
        get_scan_history(
            instagram_user["instagram_user_id"],
            days,
            limit,
            offset,
        )
    )


@bp.get("/scan-analytics")
def scan_analytics():
    app_user_id, context = get_active_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    try:
        days = int(request.args.get("days", 30))
    except (ValueError, TypeError):
        days = 30

    return jsonify(get_scan_analytics(instagram_user["instagram_user_id"], days=days))


@bp.get("/diff/latest")
def latest_diff():
    app_user_id, context = get_active_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)

    diff = persistence.get_latest_diff(
        reference_profile_id=instagram_user["instagram_user_id"]
    )

    return jsonify(
        _enrich_diff_with_alt_followback(
            diff,
            app_user_id=app_user_id,
            reference_profile_id=instagram_user["instagram_user_id"],
        )
    )


@bp.get("/diff/<diff_id>")
def get_diff(diff_id: str):
    app_user_id, context = get_active_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    diff = persistence.get_diff(diff_id=diff_id)
    if not diff:
        return jsonify({"error": "Diff not found"}), 404
    return jsonify(
        _enrich_diff_with_alt_followback(
            diff,
            app_user_id=app_user_id,
            reference_profile_id=instagram_user["instagram_user_id"],
        )
    )


@bp.post("/diff/<diff_id>/accessibility/refresh")
def refresh_diff_accessibility(diff_id: str):
    app_user_id, context = get_active_context()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict[str, Any], context)
    payload = request.get_json(silent=True) or {}
    list_name = str(payload.get("list_name") or "unfollowers").strip().lower()

    key_map = {
        "followers": {"new_followers"},
        "new_followers": {"new_followers"},
        "unfollowers": {"unfollowers"},
        "all": {"new_followers", "unfollowers"},
    }
    list_keys = key_map.get(list_name)
    if list_keys is None:
        return (
            jsonify(
                {
                    "error": "Invalid list_name. Expected one of: followers, new_followers, unfollowers, all.",
                }
            ),
            400,
        )

    diff = persistence.get_diff(diff_id=diff_id)
    if not diff:
        return jsonify({"error": "Diff not found"}), 404

    reference_profile_id = str(instagram_user["instagram_user_id"])
    seed_target_profiles_from_diff_payload(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        payload=diff,
    )

    target_profile_ids = _collect_target_profile_ids(diff, list_keys)
    if target_profile_ids:
        profile = _build_profile(app_user_id, reference_profile_id)
        deactivated_map = live_deactivated_map(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            profile=profile,
            target_profile_ids=target_profile_ids,
            fetch_at_max=2,
            caller_service="history_api",
            caller_method="refresh_diff_accessibility",
        )
    else:
        deactivated_map = {}

    _apply_accessibility_to_rows(diff, deactivated_map, list_keys=list_keys)
    write_diff_payload(diff_id, diff)

    return jsonify(
        _enrich_diff_with_alt_followback(
            diff,
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
        )
    )
