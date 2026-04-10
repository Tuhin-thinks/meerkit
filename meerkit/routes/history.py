from typing import Any, cast

from flask import Blueprint, jsonify, request

from meerkit.config import HISTORY_ALL_TIME_DAYS, HISTORY_DEFAULT_DAYS, HISTORY_MAX_DAYS
from meerkit.routes import get_active_context
from meerkit.services import account_handler, persistence
from meerkit.services import db_service as _db_service
from meerkit.services.db_service import get_scan_analytics, get_scan_history

bp = Blueprint("history", __name__, url_prefix="/api")

HISTORY_PAGE_SIZE_DEFAULT = 10
HISTORY_PAGE_SIZE_MAX = 200


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
            enriched_rows.append(
                {
                    **row,
                    "account_not_accessible": bool(
                        row.get("account_not_accessible", False)
                    ),
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
