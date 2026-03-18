import hashlib
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import insta_interface as ii
from backend.config import DIFFS_DIR, app_user_db
from backend.db.db_handler import SqliteDBHandler

_thread_local = threading.local()


def get_worker_db(db_path: Path | None = None) -> SqliteDBHandler:
    if db_path is None:
        db_path = app_user_db()
    existing = getattr(_thread_local, "db", None)
    if existing and existing.db_path == db_path:
        return existing
    if existing:
        existing.close()
    _thread_local.db = SqliteDBHandler(db_path=db_path)
    print(
        f"[DB Service] Initialized DB handler for thread {threading.current_thread().name} with db path: {db_path}"
    )
    return _thread_local.db


def init_worker_db() -> SqliteDBHandler:
    """Initialize the worker thread's database handler for the given app user id."""
    db_path = app_user_db()
    return get_worker_db(db_path=db_path)


def close_worker_db() -> None:
    db_handler = getattr(_thread_local, "db", None)
    if db_handler:
        db_handler.close()
        delattr(_thread_local, "db")


def retrieve_img_path_by_pk_id(pk_id: str) -> str | None:
    """Convenience method to retrieve cached image path by pk_id for current app user."""
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT local_path FROM image_cache WHERE profile_id = ?", (pk_id,)
        )
        row = cursor.fetchone()
        return row["local_path"] if row else None


def get_latest_profile_pic_url(
    app_user_id: str, reference_profile_id: str, pk_id: str
) -> str | None:
    """Return the most recent stored profile image URL for a follower in one scan scope."""
    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT scanned_data.profile_pic_url
            FROM scanned_data
            JOIN scan_history ON scan_history.scan_id = scanned_data.scan_id
            WHERE scanned_data.app_user_id = ?
                AND scanned_data.reference_profile_id = ?
                AND scanned_data.profile_id = ?
                AND scanned_data.profile_pic_url IS NOT NULL
                AND scanned_data.profile_pic_url != ''
            ORDER BY scan_history.scan_time DESC
            LIMIT 1
            """,
            (app_user_id, reference_profile_id, pk_id),
        )
        row = cursor.fetchone()
        return row["profile_pic_url"] if row else None


def cache_image_path(to_insert_data: list[tuple[str, str, str]]) -> None:
    """creates an entry in the image_cache table for the current app user with the local path of a cached image"""
    if not to_insert_data:
        return

    db_handler = get_worker_db()
    with db_handler as conn:
        cursor = conn.cursor()
        # Why I am creating a separate img_id instead of using pk_id ?
        # It will enable me to track someone changing their profile picture (same pk_id but different img_url) and caching it as a new entry, without losing the old cached image until it's eventually cleaned up.
        bulk_insert_data = []
        for pk_id, img_url, local_path in to_insert_data:
            img_hash = hashlib.sha256(img_url.encode()).hexdigest()[:16]
            img_id = f"{pk_id}_{img_hash}"
            # cursor.execute(
            #     "INSERT INTO image_cache (profile_id, image_id, url, local_path, create_date) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            #     (pk_id, img_id, img_url, local_path),
            # )
            bulk_insert_data.append((pk_id, img_id, img_url, local_path))
        cursor.executemany(
            "INSERT OR REPLACE INTO image_cache (profile_id, image_id, url, local_path, create_date) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            bulk_insert_data,
        )
        conn.commit()
        print(
            f"[DB Service] Cached {len(to_insert_data)} image paths in DB for thread {threading.current_thread().name}."
        )


def store_scan_info(
    scan_id: str,
    reference_profile_id: str,
    app_user_id: str,
    profile_list: list[ii.FollowerUserRecord],
):
    _current_time = datetime.now().isoformat()
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scan_history (scan_id, app_user_id, reference_profile_id, scan_time) VALUES (?, ?, ?, ?)",
            (scan_id, app_user_id, reference_profile_id, _current_time),
        )
        conn.commit()
        print(
            f"[DB Service] Stored scan info for app_user_id: {app_user_id} at {_current_time} in DB for thread {threading.current_thread().name}."
        )

        # store scanned data
        scanned_data_bulk_insert = []
        for follower in profile_list:
            scanned_data_bulk_insert.append(
                (
                    scan_id,
                    app_user_id,
                    reference_profile_id,
                    follower.fbid_v2,
                    follower.full_name,
                    follower.id,  # profile id
                    int(follower.is_private),
                    int(follower.is_verified or False),
                    follower.profile_pic_id,
                    follower.profile_pic_url,
                    follower.username,
                )
            )

        cursor.executemany(
            "INSERT INTO scanned_data (scan_id, app_user_id, reference_profile_id, fbid_v2, "
            "full_name, profile_id, is_private, is_verified, "
            "profile_pic_id, profile_pic_url, username) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            scanned_data_bulk_insert,
        )
        conn.commit()
        print(
            f"[DB Service] Stored scanned data for {len(profile_list)} followers for app_user_id: {app_user_id} at {_current_time} in DB for thread {threading.current_thread().name}."
        )
        return scan_id


def _batch_retrieve_scanned_data(
    cursor, scan_id: str, profile_ids: set, batch_size: int = 100
) -> list:
    """Batch retrieve scanned data for given profile_ids from a specific scan."""
    scanned_data = []
    to_fetch_profiles = set()

    for profile_id in profile_ids:
        to_fetch_profiles.add(profile_id)
        if len(to_fetch_profiles) >= batch_size:
            _placeholders = ",".join("?" for _ in to_fetch_profiles)
            _query = f"SELECT * FROM scanned_data WHERE scan_id = ? AND profile_id IN ({_placeholders})"
            cursor.execute(_query, (scan_id, *to_fetch_profiles))
            scanned_data.extend(cursor.fetchall())
            to_fetch_profiles.clear()

    if to_fetch_profiles:
        _placeholders = ",".join("?" for _ in to_fetch_profiles)
        _query = f"SELECT * FROM scanned_data WHERE scan_id = ? AND profile_id IN ({_placeholders})"
        cursor.execute(_query, (scan_id, *to_fetch_profiles))
        scanned_data.extend(cursor.fetchall())
        to_fetch_profiles.clear()

    return scanned_data


def store_diff_locally(
    scan_id: str, diff_data: dict[str, list[ii.FollowerUserRecord]], diff_id: str
) -> str:
    """Store the generated diff data as a local JSON file and return the file path."""
    import json

    diff_file_path = DIFFS_DIR / f"{diff_id}.json"
    with open(diff_file_path, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "scan_id": scan_id,
                "diff_id": diff_id,
                "new_count": len(diff_data["new_followers"]),
                "unfollow_count": len(diff_data["unfollowers"]),
                "new_followers": [
                    asdict(follower) for follower in diff_data["new_followers"]
                ],
                "unfollowers": [
                    asdict(unfollower) for unfollower in diff_data["unfollowers"]
                ],
            },
            f,
            indent=4,
        )
    print(f"[DB Service] Stored diff data locally at {diff_file_path}.")
    return str(diff_file_path)


# diff_id = f"{app_user_id}_{latest_scan_id}_diff"
def store_diff_record(
    diff_id: str,
    app_user_id: str,
    previous_scan_id: str,
    latest_scan_id: str,
    reference_profile_id: str,
    follower_count: int,
    unfollower_count: int,
) -> str:
    """Store the generated diff data in the DB and return the diff record id."""
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        diff_file_path = DIFFS_DIR / f"{diff_id}.json"
        cursor.execute(
            (
                "INSERT INTO diff_records ("
                "diff_id, app_user_id, previous_scan_id, "
                "current_scan_id, reference_profile_id, "
                "follower_count, unfollower_count, "
                "diff_file_path, create_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
            ),
            (
                diff_id,
                app_user_id,
                previous_scan_id,
                latest_scan_id,
                reference_profile_id,
                follower_count,
                unfollower_count,
                str(diff_file_path),
            ),
        )
        conn.commit()
        print(
            f"[DB Service] Stored diff record with id {diff_id} for app_user_id: {app_user_id} in DB for thread {threading.current_thread().name}."
        )
        return diff_id


def generate_scan_diff(
    latest_scan_id: str, reference_profile_id: str, app_user_id: str
):
    """Finds the previous scan for the same user and store the computed diff in the DB."""

    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        # find the previous scan for the same user
        cursor.execute(
            "SELECT scan_id FROM scan_history WHERE app_user_id = ? AND reference_profile_id = ? AND scan_id != ? ORDER BY scan_time DESC LIMIT 1",
            (app_user_id, reference_profile_id, latest_scan_id),
        )
        diff_data: dict[str, list[ii.FollowerUserRecord]] = {
            "unfollowers": [],
            "new_followers": [],
        }

        result = cursor.fetchone()
        if not result:
            print(
                f"[DB Service] No previous scan found for user {reference_profile_id} to compute diff against."
            )
            # TODO: Generate diff against an empty dataset and return it, marking all current followers as new followers.
            # This will enable the frontend to show the follower list even on the first scan, instead of showing an empty list until the second scan is done.

            cursor.execute(
                "SELECT * FROM scanned_data WHERE scan_id = ?", (latest_scan_id,)
            )
            for row in cursor.fetchall():
                record = ii.FollowerUserRecord(
                    fbid_v2=row["fbid_v2"],
                    full_name=row["full_name"],
                    id=row["profile_id"],
                    pk_id=row["profile_id"],
                    is_private=bool(row["is_private"]),
                    is_verified=bool(row["is_verified"]),
                    profile_pic_id=row["profile_pic_id"],
                    profile_pic_url=row["profile_pic_url"],
                    username=row["username"],
                )
                diff_data["new_followers"].append(record)
            print(
                f"{len(diff_data['new_followers'])} new followers found for user {reference_profile_id} in the first scan."
            )
            diff_id = f"{reference_profile_id}_{latest_scan_id}_diff"
            store_diff_locally(latest_scan_id, diff_data, diff_id)
            store_diff_record(
                diff_id=diff_id,
                app_user_id=app_user_id,
                previous_scan_id="",
                latest_scan_id=latest_scan_id,
                reference_profile_id=reference_profile_id,
                follower_count=len(diff_data["new_followers"]),
                unfollower_count=0,
            )
            return diff_data
        # ------------------------ If previously scanned data is available ------------------------------------------------
        previous_scan_id = result["scan_id"]
        print(
            f"[DB Service] Found previous scan {previous_scan_id} for user {reference_profile_id} to compute diff against."
        )
        # find new_followers = now - prev
        cursor.execute(
            "SELECT profile_id FROM scanned_data WHERE scan_id = ?",
            (latest_scan_id,),
        )
        latest_profiles = {row["profile_id"] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT profile_id FROM scanned_data WHERE scan_id = ?",
            (previous_scan_id,),
        )
        previous_profiles = {row["profile_id"] for row in cursor.fetchall()}
        new_followers = latest_profiles - previous_profiles

        # batch retrieve new followers data
        new_followers_data = _batch_retrieve_scanned_data(
            cursor, latest_scan_id, new_followers
        )

        # generate new followers diff data
        _diff_records = []
        for row in new_followers_data:
            record = ii.FollowerUserRecord(
                fbid_v2=row["fbid_v2"],
                full_name=row["full_name"],
                id=row["profile_id"],
                pk_id=row["profile_id"],
                is_private=bool(row["is_private"]),
                is_verified=bool(row["is_verified"]),
                profile_pic_id=row["profile_pic_id"],
                profile_pic_url=row["profile_pic_url"],
                username=row["username"],
            )
            _diff_records.append(record)

        diff_data["new_followers"].extend(_diff_records)
        print(
            f"{len(diff_data['new_followers'])} new followers found for user {reference_profile_id}."
        )

        # find unfollowers = prev - now
        unfollowers = previous_profiles - latest_profiles
        unfollowers_data = _batch_retrieve_scanned_data(
            cursor, previous_scan_id, unfollowers
        )
        _diff_records = []
        for row in unfollowers_data:
            record = ii.FollowerUserRecord(
                fbid_v2=row["fbid_v2"],
                full_name=row["full_name"],
                id=row["profile_id"],
                pk_id=row["profile_id"],
                is_private=bool(row["is_private"]),
                is_verified=bool(row["is_verified"]),
                profile_pic_id=row["profile_pic_id"],
                profile_pic_url=row["profile_pic_url"],
                username=row["username"],
            )
            _diff_records.append(record)

        diff_data["unfollowers"].extend(_diff_records)
        print(
            f"{len(diff_data['unfollowers'])} unfollowers found for user {reference_profile_id}."
        )
        diff_id = f"{reference_profile_id}_{latest_scan_id}_diff"
        store_diff_locally(latest_scan_id, diff_data, diff_id)
        store_diff_record(
            diff_id=diff_id,
            app_user_id=app_user_id,
            previous_scan_id=previous_scan_id,
            latest_scan_id=latest_scan_id,
            reference_profile_id=reference_profile_id,
            follower_count=len(diff_data["new_followers"]),
            unfollower_count=len(diff_data["unfollowers"]),
        )

        return diff_id


def get_latest_scan_id(reference_profile_id: str) -> str | None:
    """Return the latest scan ID for a given reference profile, or None if none exist."""
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scan_id FROM scan_history WHERE reference_profile_id = ? ORDER BY scan_time DESC LIMIT 1",
            (reference_profile_id,),
        )
        result = cursor.fetchone()
        return result["scan_id"] if result else None


def get_latest_scan_record(reference_profile_id: str) -> dict | None:
    """Return the latest scan record for a given reference profile."""
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scan_id, scan_time FROM scan_history WHERE reference_profile_id = ? ORDER BY scan_time DESC LIMIT 1",
            (reference_profile_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_latest_diff_id(reference_profile_id: str) -> str | None:
    """Return the latest diff ID for a given reference profile, or None if none exist."""
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT diff_id FROM diff_records WHERE reference_profile_id = ? ORDER BY create_date DESC LIMIT 1",
            (reference_profile_id,),
        )
        result = cursor.fetchone()
        return result["diff_id"] if result else None


def get_diff_by_id(diff_id: str) -> dict | None:
    """Return the diff data for a given diff ID, or None if not found."""
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT diff_file_path FROM diff_records WHERE diff_id = ?",
            (diff_id,),
        )
        result = cursor.fetchone()
        if not result:
            return None
        diff_file_path = result["diff_file_path"]
        try:
            with open(diff_file_path) as f:
                import json

                return json.load(f)
        except FileNotFoundError:
            print(f"[DB Service] Diff file not found at path: {diff_file_path}")
            return None


def get_scan_history(reference_profile_id: str) -> list[dict]:
    # [
    #     scan_id, diff_id, timestamp, follower_count, unfollower_count
    # ]
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sh.scan_id, dr.diff_id, sh.scan_time, dr.follower_count, dr.unfollower_count
            FROM scan_history sh
            LEFT JOIN diff_records dr ON sh.scan_id = dr.current_scan_id
            WHERE sh.reference_profile_id = ?
            ORDER BY sh.scan_time DESC
            """,
            (reference_profile_id,),
        )
        results = cursor.fetchall()
        history = []
        for row in results:
            history.append(
                {
                    "scan_id": row["scan_id"],
                    "diff_id": row["diff_id"],
                    "timestamp": row["scan_time"],
                    "follower_count": row["follower_count"],
                    "unfollower_count": row["unfollower_count"],
                }
            )
        return history
