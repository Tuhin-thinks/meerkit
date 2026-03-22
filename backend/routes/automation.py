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
"""

from typing import cast

from flask import Blueprint, jsonify, request

from backend.routes import get_active_context
from backend.services import automation_runner, db_service
from backend.services.account_handler import _build_profile
from backend.services.automation_service import (
    add_safelist_entries,
    confirm_action,
    list_safelist,
    prepare_batch_follow,
    prepare_batch_unfollow,
    remove_safelist_entry,
)
from backend.services.instagram_gateway import instagram_gateway

bp = Blueprint("automation", __name__, url_prefix="/api/automation")

_VALID_LIST_TYPES = {"do_not_follow", "never_unfollow"}


def _active_scope() -> tuple[str | None, dict | tuple[dict, int]]:
    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    return get_active_context(instagram_user_id)


# ── Following users ────────────────────────────────────────────────────────────


@bp.get("/following-users")
def get_following_users():
    """Fetch the list of accounts the active Instagram profile currently follows.

    This makes a live call to the Instagram API and may take several seconds for
    large following lists. Results are not cached; the client should avoid
    hammering this endpoint rapidly.
    """
    app_user_id, context = _active_scope()
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    reference_profile_id: str = instagram_user["instagram_user_id"]

    try:
        profile = _build_profile(instagram_user)
        records = instagram_gateway.get_current_following_v2(
            app_user_id=app_user_id,
            instagram_user_id=reference_profile_id,
            profile=profile,
            caller_service="automation",
            caller_method="get_following_users",
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to fetch following list: {exc}"}), 502

    users = [
        {
            "user_id": r.pk_id,
            "username": r.username,
            "full_name": r.full_name,
            "is_private": r.is_private,
            "profile_pic_url": r.profile_pic_url,
        }
        for r in records
    ]
    return jsonify({"users": users, "total": len(users)})


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
