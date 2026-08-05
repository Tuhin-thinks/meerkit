#!/usr/bin/env python3
"""Manual test: Follow a user via Instagram GraphQL API.

Usage:
    uv run python tests/manual/test_follow_user.py

Update the config values below before running.
WARNING: This actually follows the user. Use with caution.
"""

import sys

sys.path.insert(0, ".")

from insta_interface import follow_user_by_id
from tests.manual.helpers import build_profile

# ============================================================
# CONFIG: Fill in your values before running
# ============================================================
APP_USER_ID = ""              # your app user ID (from app_users.json)
INSTAGRAM_USER_ID = ""        # your instagram user ID (ds_user_id from cookie)
TARGET_USER_ID = ""           # numeric ID of the user to follow
TARGET_USERNAME = ""          # username of the user to follow (for display)
# ============================================================


def main():
    if not all([APP_USER_ID, INSTAGRAM_USER_ID, TARGET_USER_ID, TARGET_USERNAME]):
        print("Please fill in all config values")
        sys.exit(1)

    profile = build_profile(APP_USER_ID, INSTAGRAM_USER_ID)

    print(f"Following user: {TARGET_USERNAME} (ID: {TARGET_USER_ID})")
    result = follow_user_by_id(TARGET_USER_ID, TARGET_USERNAME, profile)

    if result == 1:
        print(f"Successfully followed {TARGET_USERNAME}")
    else:
        print(f"Failed to follow {TARGET_USERNAME}")


if __name__ == "__main__":
    main()
