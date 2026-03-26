from typing import Any, cast

from flask import Blueprint, jsonify, request

from backend.routes import get_active_context
from backend.services import account_handler, persistence
from backend.services import db_service as _db_service
from backend.services.db_service import get_scan_analytics, get_scan_history

bp = Blueprint("history", __name__, url_prefix="/api")


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

    return jsonify(get_scan_history(instagram_user["instagram_user_id"]))


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
