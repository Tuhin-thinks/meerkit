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


def write_metadata_outputs(profile) -> tuple[Path, Path]:
    from insta_interface import get_target_user_data

    target_user_id, target_username = resolve_target_user_id(profile)
    metadata = get_target_user_data(profile, target_user_id)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = sanitize_label(target_username, target_user_id)

    json_path = OUTPUT_DIR / f"target_user_metadata_{label}_{timestamp}.json"
    txt_path = OUTPUT_DIR / f"target_user_metadata_{label}_{timestamp}.txt"

    with json_path.open("w", encoding="utf-8") as file_obj:
        json.dump(metadata, file_obj, indent=2, ensure_ascii=False)

    with txt_path.open("w", encoding="utf-8") as file_obj:
        file_obj.write(f"viewer_user_id={profile.user_id}\n")
        file_obj.write(f"target_user_id={target_user_id}\n")
        file_obj.write(
            f"target_username={metadata.get('username') or target_username or ''}\n\n"
        )
        for key in sorted(metadata):
            file_obj.write(f"{key}={metadata[key]}\n")

    return json_path, txt_path


def main() -> None:
    profile = build_profile_from_env()
    json_path, txt_path = write_metadata_outputs(profile)
    print(f"Wrote target metadata JSON to: {json_path}")
    print(f"Wrote target metadata TXT to: {txt_path}")


if __name__ == "__main__":
    main()
