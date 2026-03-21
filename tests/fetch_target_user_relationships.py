import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "tests" / "outputs"


def build_profile_from_env():
    from insta_interface import InstagramProfile

    csrf_token = os.environ["IG_CSRF_TOKEN"]
    session_id = os.environ["IG_SESSION_ID"]
    user_id = os.environ["IG_USER_ID"]
    return InstagramProfile(
        csrf_token=csrf_token,
        session_id=session_id,
        user_id=user_id,
    )


def resolve_target_user_id(profile) -> tuple[str, str | None]:
    from insta_interface import resolve_target_user_pk

    target_user_id = os.environ.get("IG_TARGET_USER_ID", "").strip() or None
    target_username = os.environ.get("IG_TARGET_USERNAME", "").strip() or None

    if target_user_id:
        return target_user_id, target_username

    if not target_username:
        raise ValueError(
            "Set IG_TARGET_USER_ID or IG_TARGET_USERNAME before running this script."
        )

    resolved_user_id = resolve_target_user_pk(target_username, profile)
    if not resolved_user_id:
        raise ValueError(f"Could not resolve target user id for {target_username}")

    return resolved_user_id, target_username


def sanitize_label(value: str | None, fallback: str) -> str:
    label = (value or fallback).strip()
    return "".join(
        char if char.isalnum() or char in {"-", "_"} else "_" for char in label
    )


def _serialize_users(users) -> list[dict]:
    return [
        {
            "pk_id": user.pk_id,
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "is_private": user.is_private,
            "is_verified": user.is_verified,
            "profile_pic_url": user.profile_pic_url,
            "profile_pic_id": user.profile_pic_id,
            "fbid_v2": user.fbid_v2,
        }
        for user in users
    ]


def write_relationship_outputs(profile) -> tuple[Path, Path, Path]:
    from insta_interface import (
        get_target_followers_v2,
        get_target_following_v2,
        get_target_user_data,
    )

    target_user_id, target_username = resolve_target_user_id(profile)
    metadata = get_target_user_data(profile, target_user_id)
    followers = get_target_followers_v2(profile, target_user_id)
    following = get_target_following_v2(profile, target_user_id)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    metadata_username = metadata.get("username")
    if not isinstance(metadata_username, str):
        metadata_username = target_username
    label = sanitize_label(metadata_username, target_user_id)

    followers_path = OUTPUT_DIR / f"target_followers_{label}_{timestamp}.json"
    following_path = OUTPUT_DIR / f"target_following_{label}_{timestamp}.json"
    summary_path = OUTPUT_DIR / f"target_relationship_summary_{label}_{timestamp}.txt"

    with followers_path.open("w", encoding="utf-8") as file_obj:
        json.dump(_serialize_users(followers), file_obj, indent=2, ensure_ascii=False)

    with following_path.open("w", encoding="utf-8") as file_obj:
        json.dump(_serialize_users(following), file_obj, indent=2, ensure_ascii=False)

    with summary_path.open("w", encoding="utf-8") as file_obj:
        file_obj.write(f"viewer_user_id={profile.user_id}\n")
        file_obj.write(f"target_user_id={target_user_id}\n")
        file_obj.write(
            f"target_username={metadata.get('username') or target_username or ''}\n"
        )
        file_obj.write(f"total_followers={len(followers)}\n")
        file_obj.write(f"total_following={len(following)}\n\n")

        file_obj.write("[metadata]\n")
        for key in sorted(metadata):
            file_obj.write(f"{key}={metadata[key]}\n")

    return followers_path, following_path, summary_path


def main() -> None:
    profile = build_profile_from_env()
    followers_path, following_path, summary_path = write_relationship_outputs(profile)
    print(f"Wrote target followers JSON to: {followers_path}")
    print(f"Wrote target following JSON to: {following_path}")
    print(f"Wrote relationship summary TXT to: {summary_path}")


if __name__ == "__main__":
    main()
