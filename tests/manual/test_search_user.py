#!/usr/bin/env python3
"""Manual test: Search for a user by username via Instagram topsearch API.

Usage:
    uv run python tests/manual/test_search_user.py

Update the config values below before running.
"""

import sys

sys.path.insert(0, ".")

from insta_interface import resolve_target_user_pk
from tests.manual.helpers import build_profile

# ============================================================
# CONFIG: Fill in your values before running
# ============================================================
APP_USER_ID = ""              # your app user ID (from app_users.json)
INSTAGRAM_USER_ID = ""        # your instagram user ID (ds_user_id from cookie)
TARGET_USERNAME = ""          # username to search for
# ============================================================


def main():
    if not all([APP_USER_ID, INSTAGRAM_USER_ID, TARGET_USERNAME]):
        print("Please fill in APP_USER_ID, INSTAGRAM_USER_ID, and TARGET_USERNAME")
        sys.exit(1)

    profile = build_profile(APP_USER_ID, INSTAGRAM_USER_ID)

    print(f"Searching for username: {TARGET_USERNAME}")
    user_pk = resolve_target_user_pk(TARGET_USERNAME, profile)

    if user_pk:
        print(f"\n{'='*50}")
        print(f"Username:  {TARGET_USERNAME}")
        print(f"User PK:   {user_pk}")
        print(f"{'='*50}")
    else:
        print(f"User '{TARGET_USERNAME}' not found")


if __name__ == "__main__":
    main()
