import json
from datetime import datetime
from pathlib import Path

import insta_interface as ii
from backend.services.db_service import generate_scan_diff, store_scan_info
from backend.services.instagram_gateway import instagram_gateway


def compare_followers(
    old_followers: list[ii.FollowerUserRecord],
    new_followers: list[ii.FollowerUserRecord],
) -> dict[str, set[ii.FollowerUserRecord]]:
    old_set = set(old_followers)
    new_set = set(new_followers)

    new_followers_only = new_set - old_set
    unfollowers_only = old_set - new_set

    return {"new_followers": new_followers_only, "unfollowers": unfollowers_only}


def read_followers_from_file(filename: str | Path) -> list[ii.FollowerUserRecord]:
    followers = []
    with open(filename, "r") as f:
        lines = f.readlines()
        for line in lines[1:]:  # skip the first line (timestamp)
            line = line.strip()
            if line:
                followers.append(ii.FollowerUserRecord.from_string(line))
    return followers


def store_report(report: dict[str, set[ii.FollowerUserRecord]]) -> None:
    _current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"scan_report_{_current_time}.txt", "w") as f:
        f.write(f"Report generated on: {datetime.now()}\n")
        f.write(f"New followers: {len(report['new_followers'])}\n")
        f.write(f"Unfollowers: {len(report['unfollowers'])}\n")

        f.write("\nNew Followers:\n")
        for follower in report["new_followers"]:
            f.write(f"{follower}\n")

        f.write("\nUnfollowers:\n")
        for unfollower in report["unfollowers"]:
            f.write(f"{unfollower}\n")


def main():
    raise RuntimeError(
        "Use run_scan_for_api with explicit credentials, or pass InstagramProfile explicitly."
    )


def add_to_downloader_queue(
    app_user_id: str,
    instagram_user_id: str,
    profile: list[ii.FollowerUserRecord],
) -> None:
    """Add a follower's profile image URL to the downloader queue for async caching."""
    from backend.services.downloader import enqueue_image_download

    print(f"Enqueuing image download for {len(profile)} followers...")
    for follower in profile:
        enqueue_image_download(
            app_user_id,
            instagram_user_id,
            follower.pk_id,
            follower.profile_pic_url,
        )


# ---------------------------------------------------------------------------
# API-facing helpers (used by the Flask backend; do not call from CLI main())
# ---------------------------------------------------------------------------


def _load_latest_snapshot(data_dir: Path) -> list[ii.FollowerUserRecord] | None:
    """Return followers from the most recent scan snapshot, or None if none exist."""
    scans_dir = data_dir / "scans"
    if not scans_dir.exists():
        return None
    snapshots = sorted(scans_dir.glob("scan_*.jsonl"))
    if not snapshots:
        return None
    return read_followers_from_file(snapshots[-1])


def run_scan_for_api(
    app_user_id: str,
    data_dir: Path,
    csrf_token: str,
    session_id: str,
    reference_profile_id: str,
) -> dict:
    """
    Fetch current followers, persist a timestamped snapshot, compute a diff
    against the previous snapshot, and return scan metadata.

    Called by the Flask backend – never modifies insta_interface.py.
    """
    scans_dir = data_dir / "scans"
    diffs_dir = data_dir / "diffs"
    scans_dir.mkdir(parents=True, exist_ok=True)
    diffs_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    scan_id = f"scan_{now.strftime('%Y%m%d_%H%M%S')}"

    # Load the previous snapshot before overwriting anything
    prev_followers = _load_latest_snapshot(data_dir)

    profile = ii.InstagramProfile(
        csrf_token=csrf_token,
        session_id=session_id,
        user_id=reference_profile_id,
    )
    # followers = ii.get_current_followers(profile=profile, store_data=False)
    followers = instagram_gateway.get_current_followers_v2(
        app_user_id=app_user_id,
        instagram_user_id=reference_profile_id,
        profile=profile,
        caller_service="scan_flow",
        caller_method="run_scan_for_api",
    )

    add_to_downloader_queue(app_user_id, reference_profile_id, followers)
    latest_scan_id = store_scan_info(
        scan_id, reference_profile_id, app_user_id, followers
    )

    # Compute and persist diff
    diff_id = generate_scan_diff(latest_scan_id, reference_profile_id, app_user_id)

    from backend.services import account_handler

    account_handler.reconcile_followback_predictions(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        follower_ids={follower.pk_id for follower in followers if follower.pk_id},
        observed_at=now.isoformat(),
    )

    # TODO: We may not need this in future.
    if prev_followers is not None:
        add_to_downloader_queue(app_user_id, reference_profile_id, prev_followers)

    return {
        "scan_id": scan_id,
        "timestamp": now.isoformat(),
        "follower_count": len(followers),
        "unfollower_count": len(prev_followers) if prev_followers else 0,
        "diff_id": diff_id,
    }


if __name__ == "__main__":
    main()
