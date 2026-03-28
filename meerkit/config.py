import os
import random
from pathlib import Path

# Workspace root is the parent of this meerkit/ package
WORKSPACE_ROOT = Path(__file__).parent.parent

DATA_DIR = WORKSPACE_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
USERS_DIR = DATA_DIR / "users"
SCANS_DIR = DATA_DIR / "scans"
DIFFS_DIR = DATA_DIR / "diffs"
# TODO: this is not used, remove the references
IMAGE_CACHE_DIR = DATA_DIR / "image_cache"
SCAN_INDEX_FILE = DATA_DIR / "scan_index.jsonl"


# random delay range for image downloads to avoid overwhelming Instagram's servers
def IMAGE_DOWNLOAD_DELAY_SECONDS() -> int:
    return random.randint(1, 3)


# Maximum worker threads per queue consumer.
MAX_IMAGE_DOWNLOAD_WORKERS = 10
MAX_PREDICTION_REFRESH_WORKERS = 3
MAX_AUTOMATION_WORKERS = 3
MAX_USER_DETAILS_FETCH_THREADS = 8

# Instagram API interaction
# Number of times to retry a follow/unfollow call before giving up on that action.
INSTA_ACTION_RETRY_COUNT = int(os.environ.get("INSTA_ACTION_RETRY_COUNT", "3"))
# How many follower/following entries Instagram returns per paginated fetch request.
INSTA_FOLLOWERS_FETCH_PAGE_SIZE = int(
    os.environ.get("INSTA_FOLLOWERS_FETCH_PAGE_SIZE", "24")
)
# Sleep duration (seconds) between consecutive follower-list page fetches to avoid rate-limiting.
INSTA_FOLLOWERS_LOOP_DELAY_SECONDS = float(
    os.environ.get("INSTA_FOLLOWERS_LOOP_DELAY_SECONDS", "0.3")
)

# Automation
# Base wait time (seconds) inserted between executing two consecutive automation items.
AUTOMATION_INTER_ACTION_DELAY_SECONDS = float(
    os.environ.get("AUTOMATION_INTER_ACTION_DELAY_SECONDS", "3.0")
)
# Max extra random seconds added on top of the base inter-action delay to prevent detectable patterns.
AUTOMATION_INTER_ACTION_JITTER_SECONDS = float(
    os.environ.get("AUTOMATION_INTER_ACTION_JITTER_SECONDS", "4.0")
)
# Minutes without a heartbeat before a running automation action is considered stale and marked as error.
AUTOMATION_STALE_TIMEOUT_MINUTES = int(
    os.environ.get("AUTOMATION_STALE_TIMEOUT_MINUTES", "10")
)

# Predictions
# How many days a computed prediction result remains valid before it must be recalculated.
PREDICTION_TTL_DAYS = int(os.environ.get("PREDICTION_TTL_DAYS", "7"))
# How many hours a cached prediction is considered fresh enough to serve without re-fetching profile data.
PREDICTION_CACHE_FRESHNESS_HOURS = int(
    os.environ.get("PREDICTION_CACHE_FRESHNESS_HOURS", "6")
)
# Maximum number of historical scan records fed into the prediction model per user, to cap memory and compute.
PREDICTION_HISTORICAL_REFERENCE_LIMIT = int(
    os.environ.get("PREDICTION_HISTORICAL_REFERENCE_LIMIT", "400")
)
# Minutes without progress before a running prediction task is considered stale and marked as error.
PREDICTION_STALE_TIMEOUT_MINUTES = int(
    os.environ.get("PREDICTION_STALE_TIMEOUT_MINUTES", "5")
)

# Scans
# Seconds after a scan is queued during which it is still allowed to be starting up before being flagged as stale.
SCAN_STALE_STARTUP_GRACE_SECONDS = int(
    os.environ.get("SCAN_STALE_STARTUP_GRACE_SECONDS", "5")
)
# Default and maximum day-window for /history responses.
HISTORY_DEFAULT_DAYS = int(os.environ.get("HISTORY_DEFAULT_DAYS", "7"))
HISTORY_MAX_DAYS = int(os.environ.get("HISTORY_MAX_DAYS", "7"))

# Downloads
# HTTP request timeout (seconds) when downloading a user's profile picture.
IMAGE_DOWNLOAD_REQUEST_TIMEOUT = int(
    os.environ.get("IMAGE_DOWNLOAD_REQUEST_TIMEOUT", "10")
)

# Database
# Seconds SQLite waits to acquire a busy lock before raising an OperationalError.
SQLITE_CONNECTION_TIMEOUT = float(os.environ.get("SQLITE_CONNECTION_TIMEOUT", "10.0"))

# Tasks endpoint
# Maximum number of recent tasks returned by the /tasks API response.
TASKS_MAX_RECENT_COUNT = int(os.environ.get("TASKS_MAX_RECENT_COUNT", "10"))
# Seconds after cancellation before a cancelled task is pruned from the recent-tasks list.
TASKS_CANCELLED_EXPIRY_SECONDS = int(
    os.environ.get("TASKS_CANCELLED_EXPIRY_SECONDS", "300")
)

# Create directories on import so nothing needs to worry about them not existing
for _d in [DATA_DIR, CACHE_DIR, USERS_DIR, SCANS_DIR, DIFFS_DIR, IMAGE_CACHE_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


def user_dir(app_user_id: str) -> Path:
    """Return the root directory for one app user's persisted data."""
    return USERS_DIR / app_user_id


def profile_dir(app_user_id: str, profile_id: str) -> Path:
    """Return the directory for one user's trackable target profile."""
    return user_dir(app_user_id) / "profiles" / profile_id


def profile_data_dir(app_user_id: str, profile_id: str) -> Path:
    """Return the data directory that holds scans, diffs, and cache for a profile."""
    return profile_dir(app_user_id, profile_id) / "data"


def profile_scan_index_file(app_user_id: str, profile_id: str) -> Path:
    """Return the file path for the scan index of a profile."""
    return profile_dir(app_user_id, profile_id) / "scan_index.jsonl"


def app_user_db() -> Path:
    """Return the file path for the database of an app user."""
    return DATA_DIR / "app_user_db.sqlite"
