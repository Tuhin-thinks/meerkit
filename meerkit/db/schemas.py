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
    is_deactivated INTEGER,
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

TARGET_PROFILE_LIST_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS target_profile_list_cache_entries (
    cache_entry_id TEXT PRIMARY KEY,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    target_profile_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    cache_file_path TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    source_count_at_fetch INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    invalidated_at TEXT,
    invalidation_reason TEXT,
    create_date TEXT NOT NULL,
    update_date TEXT NOT NULL
);"""

PREDICTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    prediction_session_id TEXT,
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

INSTAGRAM_API_USAGE_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS instagram_api_usage_events (
    event_id TEXT PRIMARY KEY,
    app_user_id TEXT NOT NULL,
    instagram_user_id TEXT NOT NULL,
    category TEXT NOT NULL,
    caller_service TEXT NOT NULL,
    caller_method TEXT NOT NULL,
    success INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    called_at TEXT NOT NULL,
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

TARGET_PROFILE_LIST_CACHE_ACTIVE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_target_profile_list_cache_active
ON target_profile_list_cache_entries (
    app_user_id,
    reference_profile_id,
    target_profile_id,
    relationship_type,
    is_active
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

INSTAGRAM_API_USAGE_SCOPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_instagram_api_usage_scope
ON instagram_api_usage_events (app_user_id, instagram_user_id, category, called_at);
"""

INSTAGRAM_API_USAGE_CALLER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_instagram_api_usage_caller
ON instagram_api_usage_events (app_user_id, caller_service, caller_method, called_at);
"""

# ── Automation ─────────────────────────────────────────────────────────────────

AUTOMATION_ACTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_actions (
    action_id TEXT PRIMARY KEY,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    config_json TEXT,
    total_items INTEGER NOT NULL DEFAULT 0,
    completed_items INTEGER NOT NULL DEFAULT 0,
    failed_items INTEGER NOT NULL DEFAULT 0,
    skipped_items INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    queued_at TEXT,
    started_at TEXT,
    last_heartbeat_at TEXT,
    completed_at TEXT,
    create_date TEXT NOT NULL,
    update_date TEXT NOT NULL
);"""

AUTOMATION_ACTION_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_action_items (
    item_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    normalized_username TEXT,
    normalized_user_id TEXT,
    display_username TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    exclusion_reason TEXT,
    result_json TEXT,
    executed_at TEXT,
    error TEXT,
    create_date TEXT NOT NULL,
    update_date TEXT NOT NULL
);"""

AUTOMATION_SAFELISTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_safelists (
    safelist_id TEXT PRIMARY KEY,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    list_type TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    normalized_username TEXT,
    normalized_user_id TEXT,
    identity_key TEXT NOT NULL,
    create_date TEXT NOT NULL,
    UNIQUE (app_user_id, reference_profile_id, list_type, identity_key)
);"""

AUTOMATION_ALT_ACCOUNT_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_alt_account_links (
    link_id TEXT PRIMARY KEY,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    primary_raw_input TEXT NOT NULL,
    primary_normalized_username TEXT,
    primary_normalized_user_id TEXT,
    primary_identity_key TEXT NOT NULL,
    alt_raw_input TEXT NOT NULL,
    alt_normalized_username TEXT,
    alt_normalized_user_id TEXT,
    alt_identity_key TEXT NOT NULL,
    create_date TEXT NOT NULL,
    UNIQUE (
        app_user_id,
        reference_profile_id,
        primary_identity_key,
        alt_identity_key
    )
);"""

AUTOMATION_PRIMARY_ACCOUNTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_primary_accounts (
    primary_id TEXT PRIMARY KEY,
    app_user_id TEXT NOT NULL,
    reference_profile_id TEXT NOT NULL,
    primary_raw_input TEXT NOT NULL,
    primary_normalized_username TEXT,
    primary_normalized_user_id TEXT,
    primary_identity_key TEXT NOT NULL,
    linkedin_accounts_json TEXT NOT NULL DEFAULT '[]',
    create_date TEXT NOT NULL,
    update_date TEXT NOT NULL,
    UNIQUE (app_user_id, reference_profile_id, primary_identity_key)
);"""

AUTOMATION_ACTIONS_SCOPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_automation_actions_scope
ON automation_actions (app_user_id, reference_profile_id, status, create_date);
"""

AUTOMATION_ACTION_ITEMS_ACTION_INDEX = """
CREATE INDEX IF NOT EXISTS idx_automation_action_items_action
ON automation_action_items (action_id, status);
"""

AUTOMATION_SAFELISTS_SCOPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_automation_safelists_scope
ON automation_safelists (app_user_id, reference_profile_id, list_type);
"""

AUTOMATION_ALT_ACCOUNT_LINKS_SCOPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_automation_alt_account_links_scope
ON automation_alt_account_links (
    app_user_id,
    reference_profile_id,
    primary_identity_key,
    alt_identity_key
);
"""

AUTOMATION_PRIMARY_ACCOUNTS_SCOPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_automation_primary_accounts_scope
ON automation_primary_accounts (
    app_user_id,
    reference_profile_id,
    primary_identity_key
);
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
    "target_profile_list_cache_entries": TARGET_PROFILE_LIST_CACHE_SCHEMA,
    "predictions": PREDICTIONS_SCHEMA,
    "prediction_tasks": PREDICTION_TASKS_SCHEMA,
    "prediction_assessments": PREDICTION_ASSESSMENTS_SCHEMA,
    "instagram_api_usage_events": INSTAGRAM_API_USAGE_EVENTS_SCHEMA,
    "idx_target_profile_relationship_scope": TARGET_PROFILE_RELATIONSHIPS_INDEX,
    "idx_target_profile_list_cache_active": TARGET_PROFILE_LIST_CACHE_ACTIVE_INDEX,
    "idx_predictions_scope": PREDICTIONS_SCOPE_INDEX,
    "idx_prediction_tasks_scope": PREDICTION_TASKS_SCOPE_INDEX,
    "idx_prediction_assessments_prediction": PREDICTION_ASSESSMENTS_PREDICTION_INDEX,
    "idx_instagram_api_usage_scope": INSTAGRAM_API_USAGE_SCOPE_INDEX,
    "idx_instagram_api_usage_caller": INSTAGRAM_API_USAGE_CALLER_INDEX,
    "automation_actions": AUTOMATION_ACTIONS_SCHEMA,
    "automation_action_items": AUTOMATION_ACTION_ITEMS_SCHEMA,
    "automation_safelists": AUTOMATION_SAFELISTS_SCHEMA,
    "automation_alt_account_links": AUTOMATION_ALT_ACCOUNT_LINKS_SCHEMA,
    "automation_primary_accounts": AUTOMATION_PRIMARY_ACCOUNTS_SCHEMA,
    "idx_automation_actions_scope": AUTOMATION_ACTIONS_SCOPE_INDEX,
    "idx_automation_action_items_action": AUTOMATION_ACTION_ITEMS_ACTION_INDEX,
    "idx_automation_safelists_scope": AUTOMATION_SAFELISTS_SCOPE_INDEX,
    "idx_automation_alt_account_links_scope": AUTOMATION_ALT_ACCOUNT_LINKS_SCOPE_INDEX,
    "idx_automation_primary_accounts_scope": AUTOMATION_PRIMARY_ACCOUNTS_SCOPE_INDEX,
}
