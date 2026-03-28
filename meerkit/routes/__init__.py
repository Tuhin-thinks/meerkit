from flask import session

from meerkit.services import auth_service


def get_active_context(
    instagram_user_id_override: str | None = None,
) -> tuple[str | None, dict | tuple[dict, int]]:
    """Return app user id and active instagram user, or an API error payload."""
    app_user_id = session.get("app_user_id")
    if not app_user_id:
        return None, ({"error": "Not logged in"}, 401)

    instagram_user_id = instagram_user_id_override or session.get(
        "active_instagram_user_id"
    )
    if not instagram_user_id:
        instagram_user_id = auth_service.get_active_instagram_user_id(app_user_id)
        session["active_instagram_user_id"] = instagram_user_id
    if not instagram_user_id:
        return None, ({"error": "No active instagram user selected"}, 400)

    instagram_user = auth_service.get_instagram_user(app_user_id, instagram_user_id)
    if not instagram_user:
        return None, ({"error": "Instagram user not found"}, 404)

    if instagram_user_id_override is None:
        session["active_instagram_user_id"] = instagram_user_id

    return app_user_id, instagram_user
