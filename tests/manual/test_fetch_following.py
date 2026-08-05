#!/usr/bin/env python3
"""Manual test: Fetch a target user's following via Instagram GraphQL API.

Usage:
    uv run python tests/manual/test_fetch_following.py

Update the config values below before running.
"""

import sys

sys.path.insert(0, ".")

from insta_interface import get_target_following_v2
from tests.manual.helpers import build_profile

# ============================================================
# CONFIG: Fill in your values before running
# ============================================================
APP_USER_ID = ""              # your app user ID (from app_users.json)
INSTAGRAM_USER_ID = ""        # your instagram user ID (ds_user_id from cookie)
TARGET_USER_ID = ""           # numeric ID of the user whose following to fetch
FETCH_MAX = 20                # max following to fetch (None = all)
# ============================================================


def main():
    if not all([APP_USER_ID, INSTAGRAM_USER_ID, TARGET_USER_ID]):
        print("Please fill in APP_USER_ID, INSTAGRAM_USER_ID, and TARGET_USER_ID")
        sys.exit(1)

    profile = build_profile(APP_USER_ID, INSTAGRAM_USER_ID)

    print(f"Fetching following for user ID: {TARGET_USER_ID} (max: {FETCH_MAX})")
    following = get_target_following_v2(
        profile,
        target_user_id=TARGET_USER_ID,
        store_data=False,
        fetch_at_max=FETCH_MAX,
    )

    print(f"\n{'='*50}")
    print(f"Total following fetched: {len(following)}")
    print(f"{'='*50}")
    for i, f in enumerate(following[:50], 1):
        print(f"  {i:3d}. {f.username} (ID: {f.pk})")

    if len(following) > 50:
        print(f"  ... and {len(following) - 50} more")


if __name__ == "__main__":
    main()
