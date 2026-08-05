#!/usr/bin/env python3
"""Manual test: Fetch a target user's profile data via Instagram GraphQL API.

Usage:
    uv run python tests/manual/test_fetch_profile.py

Update the config values below before running.
"""

import sys

sys.path.insert(0, ".")

from insta_interface import _fetch_profile_query_data
from tests.manual.helpers import build_profile

# ============================================================
# CONFIG: Fill in your values before running
# ============================================================
APP_USER_ID = ""              # your app user ID (from app_users.json)
INSTAGRAM_USER_ID = ""        # your instagram user ID (ds_user_id from cookie)
TARGET_USER_ID = ""           # numeric ID of the user to fetch
# ============================================================


def main():
    if not all([APP_USER_ID, INSTAGRAM_USER_ID, TARGET_USER_ID]):
        print("Please fill in APP_USER_ID, INSTAGRAM_USER_ID, and TARGET_USER_ID")
        sys.exit(1)

    profile = build_profile(APP_USER_ID, INSTAGRAM_USER_ID)

    print(f"Fetching profile for target user ID: {TARGET_USER_ID}")
    result = _fetch_profile_query_data(profile, target_user_id=TARGET_USER_ID)
    user_data = result.get("data", {}).get("user", {})

    if not user_data:
        print("No user data returned")
        print("Full response:", result)
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"Username:      {user_data.get('username')}")
    print(f"Full Name:     {user_data.get('full_name')}")
    print(f"Followers:     {user_data.get('follower_count')}")
    print(f"Following:     {user_data.get('following_count')}")
    print(f"Posts:         {user_data.get('media_count')}")
    print(f"Bio:           {user_data.get('biography')}")
    print(f"Is Private:    {user_data.get('is_private')}")
    print(f"Is Verified:   {user_data.get('is_verified')}")
    print(f"Category:      {user_data.get('category_name')}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
