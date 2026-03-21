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

TARGET_PROFILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS target_profiles (
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    target_profile_id TEXT NOT NULL,
    username TEXT,
    full_name TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    is_private INTEGER,
    is_verified INTEGER,
    me_following_account INTEGER,
    being_followed_by_account INTEGER,
    fetch_status TEXT NOT NULL DEFAULT 'pending',
    metadata_fetched_at TEXT,
    relationships_fetched_at TEXT,
    last_error TEXT,
    create_date TEXT NOT NULL,
    update_date TEXT NOT NULL,
    PRIMARY KEY (app_user_id, reference_profile_id, target_profile_id)
);"""

TARGET_PROFILE_RELATIONSHIPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS target_profile_relationships (
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    target_profile_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    related_profile_id TEXT NOT NULL,
    related_username TEXT,
    related_full_name TEXT,
    related_is_private INTEGER,
    related_is_verified INTEGER,
    profile_pic_url TEXT,
    fetched_at TEXT NOT NULL,
    create_date TEXT NOT NULL,
    PRIMARY KEY (
        app_user_id,
        reference_profile_id,
        target_profile_id,
        relationship_type,
        related_profile_id
    )
);"""

PREDICTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    prediction_type TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    target_profile_id TEXT NOT NULL,
    target_username TEXT,
    probability REAL,
    confidence REAL,
    status TEXT NOT NULL,
    outcome_status TEXT NOT NULL DEFAULT 'pending',
    result_payload_json TEXT,
    feature_breakdown_json TEXT,
    requested_at TEXT NOT NULL,
    computed_at TEXT,
    data_as_of TEXT,
    expires_at TEXT,
    task_id TEXT,
    create_date TEXT NOT NULL,
    update_date TEXT NOT NULL
);"""

PREDICTION_TASKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS prediction_tasks (
    task_id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    target_profile_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    refresh_requested INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    queued_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    create_date TEXT NOT NULL,
    update_date TEXT NOT NULL
);"""

PREDICTION_ASSESSMENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS prediction_assessments (
    assessment_id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL,
    assessment_status TEXT NOT NULL,
    source TEXT NOT NULL,
    notes TEXT,
    evidence_json TEXT,
    observed_at TEXT,
    recorded_at TEXT NOT NULL,
    create_date TEXT NOT NULL
);"""

TARGET_PROFILE_RELATIONSHIPS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_target_profile_relationship_scope
ON target_profile_relationships (
    app_user_id,
    reference_profile_id,
    target_profile_id,
    relationship_type
);"""

PREDICTIONS_SCOPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_predictions_scope
ON predictions (app_user_id, reference_profile_id, target_profile_id, prediction_type, requested_at);
"""

PREDICTION_TASKS_SCOPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_prediction_tasks_scope
ON prediction_tasks (app_user_id, reference_profile_id, target_profile_id, queued_at);
"""

PREDICTION_ASSESSMENTS_PREDICTION_INDEX = """
CREATE INDEX IF NOT EXISTS idx_prediction_assessments_prediction
ON prediction_assessments (prediction_id, recorded_at);
"""


schema_collection = {
    "accounts": ACCOUNTS_SCHEMA,
    "image_cache": IMAGE_CACHE_SCHEMA,
    "scan_history": SCAN_HISTORY_SCHEMA,
    "scanned_data": SCANNED_DATA_SCHEMA,
    "diff_records": DIFF_RECORDS_SCHEMA,
    "profile_audience_events": PROFILE_AUDIENCE_EVENTS_SCHEMA,
    "target_profiles": TARGET_PROFILES_SCHEMA,
    "target_profile_relationships": TARGET_PROFILE_RELATIONSHIPS_SCHEMA,
    "predictions": PREDICTIONS_SCHEMA,
    "prediction_tasks": PREDICTION_TASKS_SCHEMA,
    "prediction_assessments": PREDICTION_ASSESSMENTS_SCHEMA,
    "idx_target_profile_relationship_scope": TARGET_PROFILE_RELATIONSHIPS_INDEX,
    "idx_predictions_scope": PREDICTIONS_SCOPE_INDEX,
    "idx_prediction_tasks_scope": PREDICTION_TASKS_SCOPE_INDEX,
    "idx_prediction_assessments_prediction": PREDICTION_ASSESSMENTS_PREDICTION_INDEX,
}
