from typing import Any, cast

from flask import Blueprint, jsonify, request

from meerkit.config import HISTORY_DEFAULT_DAYS, HISTORY_MAX_DAYS
from meerkit.routes import get_active_context
from meerkit.services import account_handler, persistence
from meerkit.services import db_service as _db_service
from meerkit.services.db_service import get_scan_analytics, get_scan_history

bp = Blueprint("history", __name__, url_prefix="/api")


def _to_lower(value: str | None) -> str:
    return (value or "").strip().lower()


def _is_profile_inaccessible_message(message: str) -> bool:
    return any(
        token in message
        for token in (
            "could not load this target",
            "could not load target",
            "unable to load",
            "failed to load",
            "inaccessible",
            "private",
            "not authorized",
            "forbidden",
            "'nonetype' object is not subscriptable",
            '"nonetype" object is not subscriptable',
            "nonetype object is not subscriptable",
        )
    )


def _target_is_not_accessible(error_message: str | None) -> bool:
    normalized = _to_lower(error_message)
    if not normalized:
        return False
    return _is_profile_inaccessible_message(normalized)


def _collect_inaccessible_target_ids(
    *,
    app_user_id: str,
    reference_profile_id: str,
    target_profile_ids: set[str],
) -> set[str]:
    inaccessible: set[str] = set()
    for target_profile_id in target_profile_ids:
        target_profile = _db_service.get_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
        )
        if _target_is_not_accessible(
            target_profile.get("last_error")
            if isinstance(target_profile, dict)
            else None
        ):
            inaccessible.add(target_profile_id)
            continue

        latest_task = _db_service.get_latest_prediction_task(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
        )
        if not isinstance(latest_task, dict):
            continue
        if latest_task.get("status") != "error":
            continue
        if _target_is_not_accessible(
            latest_task.get("error")
            if isinstance(latest_task.get("error"), str)
            else None
        ):
            inaccessible.add(target_profile_id)
    return inaccessible


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

    target_profile_ids: set[str] = set()
    for key in ("new_followers", "unfollowers"):
        rows = diff.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            target_profile_id = str(row.get("pk_id") or "").strip()
            if target_profile_id:
                target_profile_ids.add(target_profile_id)

    inaccessible_target_ids = _collect_inaccessible_target_ids(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_ids=target_profile_ids,
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
                    "account_not_accessible": target_profile_id
                    in inaccessible_target_ids,
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
    try:
        requested_days = int(request.args.get("days", HISTORY_DEFAULT_DAYS))
    except (TypeError, ValueError):
        requested_days = HISTORY_DEFAULT_DAYS

    max_days = max(1, HISTORY_MAX_DAYS)
    days = min(max(1, requested_days), max_days)

    return jsonify(get_scan_history(instagram_user["instagram_user_id"], days))


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
