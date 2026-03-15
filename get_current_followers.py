import json
from datetime import datetime
from pathlib import Path

import insta_interface as ii


def store_followers(followers: list[ii.FollowerUserRecord]) -> None:
    with open("followers_data.txt", "w") as f:
        # first line as the current timestamp
        f.write(f"Timestamp: {datetime.now()}\n")

        for follower in followers:
            f.write(f"{follower}\n")


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


def create_backup():
    _existing_file = Path("followers_data.txt")
    if _existing_file.exists():
        _current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = Path(f"followers_data_backup_{_current_time}.txt")
        _existing_file.rename(backup_filename)
        print(f"Existing followers data backed up to {backup_filename}")

        return backup_filename

    return None


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
    data_dir: Path,
    csrf_token: str,
    session_id: str,
    target_user_id: str,
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

    # Fetch current followers without writing the legacy followers_data.txt
    profile = ii.InstagramProfile(
        csrf_token=csrf_token,
        session_id=session_id,
        user_id=target_user_id,
    )
    # followers = ii.get_current_followers(profile=profile, store_data=False)
    followers = ii.get_current_followers_v2(profile=profile, store_data=False)

    # Persist new snapshot (same format as followers_data.txt for read_followers_from_file compat)
    snapshot_path = scans_dir / f"{scan_id}.jsonl"
    with open(snapshot_path, "w") as f:
        f.write(f"Timestamp: {now}\n")
        for follower in followers:
            f.write(f"{follower}\n")

    # Compute and persist diff
    diff_id: str | None = None
    if prev_followers is not None:
        diff = compare_followers(prev_followers, followers)
        diff_id = f"diff_{now.strftime('%Y%m%d_%H%M%S')}"
        diff_path = diffs_dir / f"{diff_id}.json"
        with open(diff_path, "w") as f:
            json.dump(
                {
                    "diff_id": diff_id,
                    "scan_id": scan_id,
                    "timestamp": now.isoformat(),
                    "new_followers": [
                        json.loads(str(r)) for r in diff["new_followers"]
                    ],
                    "unfollowers": [json.loads(str(r)) for r in diff["unfollowers"]],
                    "new_count": len(diff["new_followers"]),
                    "unfollow_count": len(diff["unfollowers"]),
                },
                f,
                indent=2,
            )

    # Append entry to scan index (one JSON line per scan)
    index_path = data_dir / "scan_index.jsonl"
    with open(index_path, "a") as f:
        f.write(
            json.dumps(
                {
                    "scan_id": scan_id,
                    "timestamp": now.isoformat(),
                    "follower_count": len(followers),
                    "diff_id": diff_id,
                }
            )
            + "\n"
        )

    return {
        "scan_id": scan_id,
        "timestamp": now.isoformat(),
        "follower_count": len(followers),
        "diff_id": diff_id,
    }


if __name__ == "__main__":
    main()
