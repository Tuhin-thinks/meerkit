ACCOUNTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    profile_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    create_date TEXT NOT NULL,
    is_private INTEGER NOT NULL,
    is_follower INTEGER NOT NULL,
    is_following INTEGER NOT NULL,
    reference_profile_id TEXT NOT NULL
);"""

SCAN_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_history (
    scan_id TEXT PRIMARY KEY,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    scan_time TEXT NOT NULL
);"""

SCANNED_DATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS scanned_data (
    scan_id TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    fbid_v2 TEXT,
    full_name TEXT,
    profile_id TEXT,
    is_private INTEGER,
    is_verified INTEGER,
    profile_pic_id TEXT,
    profile_pic_url TEXT,
    username TEXT
);"""

DIFF_RECORDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS diff_records (
    diff_id TEXT PRIMARY KEY,
    app_user_id TEXT NOT NULL,
    previous_scan_id TEXT NOT NULL,
    current_scan_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    follower_count INTEGER NOT NULL,
    unfollower_count INTEGER NOT NULL,
    diff_file_path TEXT NOT NULL,
    create_date TEXT NOT NULL
);"""

IMAGE_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS image_cache (
    profile_id TEXT NOT NULL,
    image_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    local_path TEXT NOT NULL,
    create_date TEXT NOT NULL
    );"""

PROFILE_AUDIENCE_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile_audience_events (
    profile_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    create_date TEXT NOT NULL,
    event_data TEXT
);"""


schema_collection = {
    "accounts": ACCOUNTS_SCHEMA,
    "image_cache": IMAGE_CACHE_SCHEMA,
    "scan_history": SCAN_HISTORY_SCHEMA,
    "scanned_data": SCANNED_DATA_SCHEMA,
    "diff_records": DIFF_RECORDS_SCHEMA,
    "profile_audience_events": PROFILE_AUDIENCE_EVENTS_SCHEMA,
}
