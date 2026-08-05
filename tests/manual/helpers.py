"""Shared helpers for manual testing scripts.

All manual test scripts import `build_profile()` from here to avoid
duplicating credential-loading and profile-construction logic.
"""

import sys

from insta_interface import InstagramProfile
from meerkit.services.auth_service import get_instagram_user


def build_profile(
    app_user_id: str,
    instagram_user_id: str,
) -> InstagramProfile:
    """Load credentials from instagram_users.json and build an InstagramProfile."""
    user = get_instagram_user(app_user_id, instagram_user_id)
    if user is None:
        print(
            f"Instagram user {instagram_user_id} not found "
            f"for app user {app_user_id}"
        )
        sys.exit(1)

    return InstagramProfile(
        csrf_token=user["csrf_token"],
        session_id=user["session_id"],
        user_id=user["user_id"],
        fb_dtsg=user.get("fb_dtsg", ""),
        jazoest=user.get("jazoest", ""),
        av=user.get("av", ""),
        extra_cookies=user.get("extra_cookies"),
        extra_headers=user.get("extra_headers"),
    )
