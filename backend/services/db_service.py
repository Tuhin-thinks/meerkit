import hashlib
import json
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import insta_interface as ii
from backend.config import DIFFS_DIR, app_user_db
from backend.db.db_handler import SqliteDBHandler

_thread_local = threading.local()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _json_dumps(payload: dict | list | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload)


def _json_loads(payload: str | None) -> dict | list | None:
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _normalize_prediction_row(row) -> dict | None:
    if not row:
        return None
    result = dict(row)
    result["result_payload"] = _json_loads(result.pop("result_payload_json", None))
    result["feature_breakdown"] = _json_loads(
        result.pop("feature_breakdown_json", None)
    )
    return result


def _normalize_assessment_row(row) -> dict | None:
    if not row:
        return None
    result = dict(row)
    result["evidence"] = _json_loads(result.pop("evidence_json", None))
    return result


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


def get_latest_scanned_profile_ids(
    app_user_id: str, reference_profile_id: str
) -> set[str]:
    """Return the latest known follower ids for one active profile scope."""
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT scan_id
            FROM scan_history
            WHERE app_user_id = ? AND reference_profile_id = ?
            ORDER BY scan_time DESC
            LIMIT 1
            """,
            (app_user_id, reference_profile_id),
        )
        latest_scan = cursor.fetchone()
        if not latest_scan:
            return set()

        cursor.execute(
            "SELECT profile_id FROM scanned_data WHERE scan_id = ?",
            (latest_scan["scan_id"],),
        )
        return {row["profile_id"] for row in cursor.fetchall() if row["profile_id"]}


def upsert_target_profile(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    username: str | None = None,
    full_name: str | None = None,
    follower_count: int | None = None,
    following_count: int | None = None,
    is_private: bool | None = None,
    is_verified: bool | None = None,
    me_following_account: bool | None = None,
    being_followed_by_account: bool | None = None,
    fetch_status: str = "pending",
    metadata_fetched_at: str | None = None,
    relationships_fetched_at: str | None = None,
    last_error: str | None = None,
) -> dict:
    db = get_worker_db()
    current_time = _now_iso()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO target_profiles (
                app_user_id,
                reference_profile_id,
                target_profile_id,
                username,
                full_name,
                follower_count,
                following_count,
                is_private,
                is_verified,
                me_following_account,
                being_followed_by_account,
                fetch_status,
                metadata_fetched_at,
                relationships_fetched_at,
                last_error,
                create_date,
                update_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_user_id, reference_profile_id, target_profile_id)
            DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                follower_count = excluded.follower_count,
                following_count = excluded.following_count,
                is_private = excluded.is_private,
                is_verified = excluded.is_verified,
                me_following_account = excluded.me_following_account,
                being_followed_by_account = excluded.being_followed_by_account,
                fetch_status = excluded.fetch_status,
                metadata_fetched_at = excluded.metadata_fetched_at,
                relationships_fetched_at = excluded.relationships_fetched_at,
                last_error = excluded.last_error,
                update_date = excluded.update_date
            """,
            (
                app_user_id,
                reference_profile_id,
                target_profile_id,
                username,
                full_name,
                follower_count,
                following_count,
                int(is_private) if is_private is not None else None,
                int(is_verified) if is_verified is not None else None,
                int(me_following_account) if me_following_account is not None else None,
                int(being_followed_by_account)
                if being_followed_by_account is not None
                else None,
                fetch_status,
                metadata_fetched_at,
                relationships_fetched_at,
                last_error,
                current_time,
                current_time,
            ),
        )
        conn.commit()
    return (
        get_target_profile(app_user_id, reference_profile_id, target_profile_id) or {}
    )


def get_target_profile(
    app_user_id: str, reference_profile_id: str, target_profile_id: str
) -> dict | None:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM target_profiles
            WHERE app_user_id = ? AND reference_profile_id = ? AND target_profile_id = ?
            """,
            (app_user_id, reference_profile_id, target_profile_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        for key in (
            "is_private",
            "is_verified",
            "me_following_account",
            "being_followed_by_account",
        ):
            if result.get(key) is not None:
                result[key] = bool(result[key])
        return result


def create_target_profile_list_cache_entry(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
    cache_file_path: str,
    fetched_at: str,
    source_count_at_fetch: int | None,
) -> dict:
    cache_entry_id = f"cache_{uuid4().hex}"
    current_time = _now_iso()
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO target_profile_list_cache_entries (
                cache_entry_id,
                app_user_id,
                reference_profile_id,
                target_profile_id,
                relationship_type,
                cache_file_path,
                fetched_at,
                source_count_at_fetch,
                is_active,
                invalidated_at,
                invalidation_reason,
                create_date,
                update_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_entry_id,
                app_user_id,
                reference_profile_id,
                target_profile_id,
                relationship_type,
                cache_file_path,
                fetched_at,
                source_count_at_fetch,
                1,
                None,
                None,
                current_time,
                current_time,
            ),
        )
        conn.commit()
    return (
        get_active_target_profile_list_cache_entry(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            relationship_type=relationship_type,
        )
        or {}
    )


def get_active_target_profile_list_cache_entry(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
) -> dict | None:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM target_profile_list_cache_entries
            WHERE app_user_id = ?
              AND reference_profile_id = ?
              AND target_profile_id = ?
              AND relationship_type = ?
              AND is_active = 1
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            (app_user_id, reference_profile_id, target_profile_id, relationship_type),
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        result["is_active"] = bool(result.get("is_active"))
        return result


def invalidate_target_profile_list_cache_entry(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
    reason: str,
    invalidated_at: str | None = None,
) -> int:
    invalidated_at = invalidated_at or _now_iso()
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE target_profile_list_cache_entries
            SET is_active = 0,
                invalidated_at = ?,
                invalidation_reason = ?,
                update_date = ?
            WHERE app_user_id = ?
              AND reference_profile_id = ?
              AND target_profile_id = ?
              AND relationship_type = ?
              AND is_active = 1
            """,
            (
                invalidated_at,
                reason,
                _now_iso(),
                app_user_id,
                reference_profile_id,
                target_profile_id,
                relationship_type,
            ),
        )
        conn.commit()
        return cursor.rowcount or 0


def get_target_profile_relationship_cache_summary(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
) -> dict[str, dict[str, object]]:
    target_profile = (
        get_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
        )
        or {}
    )
    now = datetime.now()
    result: dict[str, dict[str, object]] = {}

    for relationship_type in ("followers", "following"):
        active_entry = get_active_target_profile_list_cache_entry(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            relationship_type=relationship_type,
        )
        fetched_at = active_entry.get("fetched_at") if active_entry else None
        days_since_fetch: int | None = None
        if isinstance(fetched_at, str):
            try:
                days_since_fetch = max(
                    0, (now - datetime.fromisoformat(fetched_at)).days
                )
            except ValueError:
                days_since_fetch = None

        current_count_key = (
            "follower_count" if relationship_type == "followers" else "following_count"
        )
        current_count = target_profile.get(current_count_key)
        source_count = (
            active_entry.get("source_count_at_fetch") if active_entry else None
        )
        count_changed = (
            isinstance(current_count, int)
            and isinstance(source_count, int)
            and current_count != source_count
        )

        result[relationship_type] = {
            "relationship_type": relationship_type,
            "fetched_at": fetched_at,
            "days_since_fetch": days_since_fetch,
            "is_outdated": bool(count_changed),
            "active_file_present": bool(active_entry),
            "active_cache_file_path": active_entry.get("cache_file_path")
            if active_entry
            else None,
            "last_known_count": source_count,
            "current_count": current_count,
        }
    return result


def replace_target_profile_relationships(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
    profiles: list[ii.FollowerUserRecord],
    fetched_at: str | None = None,
) -> int:
    db = get_worker_db()
    fetched_at = fetched_at or _now_iso()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM target_profile_relationships
            WHERE app_user_id = ?
              AND reference_profile_id = ?
              AND target_profile_id = ?
              AND relationship_type = ?
            """,
            (app_user_id, reference_profile_id, target_profile_id, relationship_type),
        )
        if profiles:
            cursor.executemany(
                """
                INSERT INTO target_profile_relationships (
                    app_user_id,
                    reference_profile_id,
                    target_profile_id,
                    relationship_type,
                    related_profile_id,
                    related_username,
                    related_full_name,
                    related_is_private,
                    related_is_verified,
                    profile_pic_url,
                    fetched_at,
                    create_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        app_user_id,
                        reference_profile_id,
                        target_profile_id,
                        relationship_type,
                        profile.pk_id,
                        profile.username,
                        profile.full_name,
                        int(profile.is_private),
                        int(profile.is_verified or False),
                        profile.profile_pic_url,
                        fetched_at,
                        fetched_at,
                    )
                    for profile in profiles
                ],
            )
        conn.commit()

    cached_profile = get_target_profile(
        app_user_id, reference_profile_id, target_profile_id
    )
    if cached_profile:
        upsert_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            username=cached_profile.get("username"),
            full_name=cached_profile.get("full_name"),
            follower_count=cached_profile.get("follower_count"),
            following_count=cached_profile.get("following_count"),
            is_private=cached_profile.get("is_private"),
            is_verified=cached_profile.get("is_verified"),
            me_following_account=cached_profile.get("me_following_account"),
            being_followed_by_account=cached_profile.get("being_followed_by_account"),
            fetch_status="ready",
            metadata_fetched_at=cached_profile.get("metadata_fetched_at"),
            relationships_fetched_at=fetched_at,
            last_error=None,
        )
    return len(profiles)


def get_target_profile_relationships(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
) -> list[dict]:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM target_profile_relationships
            WHERE app_user_id = ?
              AND reference_profile_id = ?
              AND target_profile_id = ?
              AND relationship_type = ?
            ORDER BY related_username ASC, related_profile_id ASC
            """,
            (app_user_id, reference_profile_id, target_profile_id, relationship_type),
        )
        rows = cursor.fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["related_is_private"] = bool(item["related_is_private"])
            item["related_is_verified"] = bool(item["related_is_verified"])
            results.append(item)
        return results


def get_target_profile_relationship_ids(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
) -> set[str]:
    rows = get_target_profile_relationships(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        relationship_type=relationship_type,
    )
    return {row["related_profile_id"] for row in rows}


def create_prediction(
    prediction_type: str,
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    target_username: str | None,
    status: str,
    probability: float | None = None,
    confidence: float | None = None,
    result_payload: dict | None = None,
    feature_breakdown: dict | None = None,
    requested_at: str | None = None,
    computed_at: str | None = None,
    data_as_of: str | None = None,
    expires_at: str | None = None,
    outcome_status: str = "pending",
    task_id: str | None = None,
) -> dict:
    prediction_id = f"pred_{uuid4().hex}"
    current_time = _now_iso()
    requested_at = requested_at or current_time
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO predictions (
                prediction_id,
                prediction_type,
                app_user_id,
                reference_profile_id,
                target_profile_id,
                target_username,
                probability,
                confidence,
                status,
                outcome_status,
                result_payload_json,
                feature_breakdown_json,
                requested_at,
                computed_at,
                data_as_of,
                expires_at,
                task_id,
                create_date,
                update_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction_id,
                prediction_type,
                app_user_id,
                reference_profile_id,
                target_profile_id,
                target_username,
                probability,
                confidence,
                status,
                outcome_status,
                _json_dumps(result_payload),
                _json_dumps(feature_breakdown),
                requested_at,
                computed_at,
                data_as_of,
                expires_at,
                task_id,
                current_time,
                current_time,
            ),
        )
        conn.commit()
    return get_prediction(prediction_id) or {}


def update_prediction(
    prediction_id: str,
    *,
    target_username: str | None = None,
    probability: float | None = None,
    confidence: float | None = None,
    status: str | None = None,
    outcome_status: str | None = None,
    result_payload: dict | None = None,
    feature_breakdown: dict | None = None,
    computed_at: str | None = None,
    data_as_of: str | None = None,
    expires_at: str | None = None,
    task_id: str | None = None,
) -> dict | None:
    existing = get_prediction(prediction_id)
    if not existing:
        return None

    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE predictions
            SET target_username = ?,
                probability = ?,
                confidence = ?,
                status = ?,
                outcome_status = ?,
                result_payload_json = ?,
                feature_breakdown_json = ?,
                computed_at = ?,
                data_as_of = ?,
                expires_at = ?,
                task_id = ?,
                update_date = ?
            WHERE prediction_id = ?
            """,
            (
                target_username
                if target_username is not None
                else existing.get("target_username"),
                probability if probability is not None else existing.get("probability"),
                confidence if confidence is not None else existing.get("confidence"),
                status or existing.get("status"),
                outcome_status or existing.get("outcome_status"),
                _json_dumps(result_payload)
                if result_payload is not None
                else _json_dumps(existing.get("result_payload")),
                _json_dumps(feature_breakdown)
                if feature_breakdown is not None
                else _json_dumps(existing.get("feature_breakdown")),
                computed_at if computed_at is not None else existing.get("computed_at"),
                data_as_of if data_as_of is not None else existing.get("data_as_of"),
                expires_at if expires_at is not None else existing.get("expires_at"),
                task_id if task_id is not None else existing.get("task_id"),
                _now_iso(),
                prediction_id,
            ),
        )
        conn.commit()
    return get_prediction(prediction_id)


def get_prediction(prediction_id: str) -> dict | None:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM predictions WHERE prediction_id = ?", (prediction_id,)
        )
        return _normalize_prediction_row(cursor.fetchone())


def list_predictions(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    db = get_worker_db()
    query = """
        SELECT *
        FROM predictions
        WHERE app_user_id = ? AND reference_profile_id = ?
    """
    params: list[str | int] = [app_user_id, reference_profile_id]
    if target_profile_id:
        query += " AND target_profile_id = ?"
        params.append(target_profile_id)
    query += " ORDER BY requested_at DESC LIMIT ?"
    params.append(limit)
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        results: list[dict] = []
        for row in cursor.fetchall():
            normalized = _normalize_prediction_row(row)
            if normalized is not None:
                results.append(normalized)
        return results


def get_latest_prediction_for_target(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    prediction_type: str = "follow_back",
) -> dict | None:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM predictions
            WHERE app_user_id = ?
              AND reference_profile_id = ?
              AND target_profile_id = ?
              AND prediction_type = ?
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (app_user_id, reference_profile_id, target_profile_id, prediction_type),
        )
        return _normalize_prediction_row(cursor.fetchone())


def create_prediction_task(
    prediction_id: str,
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    task_type: str,
    refresh_requested: bool,
    status: str = "queued",
) -> dict:
    task_id = f"task_{uuid4().hex}"
    current_time = _now_iso()
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO prediction_tasks (
                task_id,
                prediction_id,
                app_user_id,
                reference_profile_id,
                target_profile_id,
                task_type,
                status,
                progress,
                refresh_requested,
                error,
                queued_at,
                started_at,
                completed_at,
                create_date,
                update_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                prediction_id,
                app_user_id,
                reference_profile_id,
                target_profile_id,
                task_type,
                status,
                0.0,
                int(refresh_requested),
                None,
                current_time,
                None,
                None,
                current_time,
                current_time,
            ),
        )
        conn.commit()
    return get_prediction_task(task_id) or {}


def update_prediction_task(
    task_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    error: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> dict | None:
    existing = get_prediction_task(task_id)
    if not existing:
        return None
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE prediction_tasks
            SET status = ?,
                progress = ?,
                error = ?,
                started_at = ?,
                completed_at = ?,
                update_date = ?
            WHERE task_id = ?
            """,
            (
                status or existing.get("status"),
                progress if progress is not None else existing.get("progress", 0.0),
                error,
                started_at if started_at is not None else existing.get("started_at"),
                completed_at
                if completed_at is not None
                else existing.get("completed_at"),
                _now_iso(),
                task_id,
            ),
        )
        conn.commit()
    return get_prediction_task(task_id)


def get_prediction_task(task_id: str) -> dict | None:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prediction_tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_latest_prediction_task(
    app_user_id: str, reference_profile_id: str, target_profile_id: str | None = None
) -> dict | None:
    db = get_worker_db()
    query = """
        SELECT *
        FROM prediction_tasks
        WHERE app_user_id = ? AND reference_profile_id = ?
    """
    params: list[str] = [app_user_id, reference_profile_id]
    if target_profile_id:
        query += " AND target_profile_id = ?"
        params.append(target_profile_id)
    query += " ORDER BY queued_at DESC LIMIT 1"
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_latest_active_prediction_task(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    statuses: tuple[str, ...] = ("queued", "running"),
) -> dict | None:
    if not statuses:
        return None

    db = get_worker_db()
    placeholders = ", ".join("?" for _ in statuses)
    query = f"""
        SELECT *
        FROM prediction_tasks
        WHERE app_user_id = ?
          AND reference_profile_id = ?
          AND target_profile_id = ?
          AND status IN ({placeholders})
        ORDER BY queued_at DESC
        LIMIT 1
    """
    params: list[str] = [
        app_user_id,
        reference_profile_id,
        target_profile_id,
        *statuses,
    ]
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_active_prediction_tasks(
    app_user_id: str,
    reference_profile_id: str,
    statuses: tuple[str, ...] = ("queued", "running", "cancelled"),
    limit: int = 100,
) -> list[dict]:
    if not statuses:
        return []

    db = get_worker_db()
    placeholders = ", ".join("?" for _ in statuses)
    query = f"""
        SELECT *
        FROM prediction_tasks
        WHERE app_user_id = ?
          AND reference_profile_id = ?
          AND status IN ({placeholders})
        ORDER BY queued_at DESC
        LIMIT ?
    """
    params: list[str | int] = [app_user_id, reference_profile_id, *statuses, limit]
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def create_prediction_assessment(
    prediction_id: str,
    assessment_status: str,
    source: str,
    notes: str | None = None,
    evidence: dict | None = None,
    observed_at: str | None = None,
) -> dict:
    assessment_id = f"assess_{uuid4().hex}"
    recorded_at = _now_iso()
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO prediction_assessments (
                assessment_id,
                prediction_id,
                assessment_status,
                source,
                notes,
                evidence_json,
                observed_at,
                recorded_at,
                create_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment_id,
                prediction_id,
                assessment_status,
                source,
                notes,
                _json_dumps(evidence),
                observed_at,
                recorded_at,
                recorded_at,
            ),
        )
        conn.commit()
    return get_prediction_assessment(assessment_id) or {}


def get_prediction_assessment(assessment_id: str) -> dict | None:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM prediction_assessments WHERE assessment_id = ?",
            (assessment_id,),
        )
        return _normalize_assessment_row(cursor.fetchone())


def list_prediction_assessments(prediction_id: str) -> list[dict]:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM prediction_assessments
            WHERE prediction_id = ?
            ORDER BY recorded_at DESC
            """,
            (prediction_id,),
        )
        results: list[dict] = []
        for row in cursor.fetchall():
            normalized = _normalize_assessment_row(row)
            if normalized is not None:
                results.append(normalized)
        return results


def list_active_followback_predictions(
    app_user_id: str, reference_profile_id: str
) -> list[dict]:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM predictions
            WHERE app_user_id = ?
              AND reference_profile_id = ?
              AND prediction_type = 'follow_back'
              AND outcome_status IN ('pending', 'unresolved')
            ORDER BY requested_at DESC
            """,
            (app_user_id, reference_profile_id),
        )
        results: list[dict] = []
        for row in cursor.fetchall():
            normalized = _normalize_prediction_row(row)
            if normalized is not None:
                results.append(normalized)
        return results


def list_labeled_followback_predictions(
    app_user_id: str,
    reference_profile_id: str,
    limit: int = 500,
) -> list[dict]:
    db = get_worker_db()
    with db as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM predictions
            WHERE app_user_id = ?
              AND reference_profile_id = ?
              AND prediction_type = 'follow_back'
              AND outcome_status IN ('correct', 'wrong')
              AND feature_breakdown_json IS NOT NULL
            ORDER BY requested_at DESC
            LIMIT ?
            """,
            (app_user_id, reference_profile_id, limit),
        )
        results: list[dict] = []
        for row in cursor.fetchall():
            normalized = _normalize_prediction_row(row)
            if normalized is not None:
                results.append(normalized)
        return results
