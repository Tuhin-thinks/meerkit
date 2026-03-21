# Architecture

Overview of the meerkit system design, data flow, and component interactions.

## High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (Port 5173)                      │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Vue 3 Frontend (TailwindCSS)              │  │
│  │  • Dashboard (latest diff, scan status)             │  │
│  │  • Admin (manage Instagram accounts)                │  │
│  │  • History (scan timeline, detailed diffs)          │  │
│  └──────────────────────────────────────────────────────┘  │
│                     ↕ HTTP/HTTPS                            │
└─────────────────────────────────────────────────────────────┘
                      Vite Proxy (/api/*)
                           ↓
┌─────────────────────────────────────────────────────────────┐
│            Flask Backend (Port 5000)                        │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  API Routes                         │  │
│  │  • /api/auth/*      (login, user management)        │  │
│  │  • /api/scan/*      (scan operations)               │  │
│  │  • /api/diff/*      (diff retrieval)                │  │
│  │  • /api/history/*   (scan history)                  │  │
│  │  • /api/image/*     (cached images)                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Service Layer                          │  │
│  │  • Scan Runner (orchestration)                      │  │
│  │  • DB Service (persistence)                         │  │
│  │  • Auth Service (user management)                   │  │
│  │  • Image Service (cache management)                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Background Workers                        │  │
│  │  • Scan Worker (fetch followers, compute diffs)     │  │
│  │  • Download Worker (cache profile images)           │  │
│  └──────────────────────────────────────────────────────┘  │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            SQLite Database                          │  │
│  │  • Scan History (metadata)                          │  │
│  │  • Scanned Data (follower records)                  │  │
│  │  • Diff Records (new/unfollowers)                   │  │
│  │  • Image Cache (local file references)              │  │
│  └──────────────────────────────────────────────────────┘  │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Disk Storage (/data/)                    │  │
│  │  • Scan snapshots (JSONL format)                    │  │
│  │  • Diff files (JSON)                                │  │
│  │  • Cached images (PNG/JPG)                          │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
        ↓ Uses Instagram API (via insta_interface)
┌─────────────────────────────────────────────────────────────┐
│                 Instagram (External)                        │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow: Running a Scan

```
1. User clicks "Scan Now" on Dashboard
   ↓
2. Frontend POST /api/scan → Backend
   ↓
3. Backend validates user session
   ↓
4. Scan Runner starts background worker thread
   ↓
5. Scan Worker:
   a. Calls Instagram API to fetch current followers
   b. Stores raw follower data in scanned_data table
   c. Creates scan_history entry
   d. Computes diff against previous scan
   e. Stores diff results in diff_records table
   f. Downloads profile pictures and caches locally
   ↓
6. Frontend polls /api/scan/status until scan completes
   ↓
7. On completion, Frontend fetches /api/diff/latest
   ↓
8. Dashboard re-renders with new followers and unfollowers
```

## Component Overview

### Backend Structure

```
backend/
├── app.py                      # Flask app factory
├── config.py                   # Config (paths, env vars)
├── extensions.py               # Flask extensions (DB, etc)
│
├── routes/                     # API Blueprints
│   ├── auth.py                # Login, user management
│   ├── scan.py                # Scan endpoints
│   ├── history.py             # History and diffs
│   ├── images.py              # Image serving
│   └── __init__.py
│
├── services/                   # Business logic
│   ├── db_service.py          # Database operations
│   ├── scan_runner.py         # Scan orchestration
│   ├── auth_service.py        # User auth
│   ├── persistence.py         # Data persistence layer
│   ├── image_cache.py         # Image caching
│   ├── event_handler.py       # Event processing
│   └── ...
│
├── db/                         # Database layer
│   ├── db_handler.py          # SQLite wrapper
│   ├── schemas.py             # Table definitions
│   └── __init__.py
│
└── workers/                    # Background tasks
    ├── download_worker.py     # Image downloading
    ├── scan_worker.py         # Scan execution
    └── __init__.py
```

### Frontend Structure

```
frontend/src/
├── components/                 # Reusable Vue components
│   ├── FollowerCard.vue       # Single follower display
│   ├── ProfilePicture.vue     # Profile image viewer
│   ├── SkeletonCard.vue       # Loading placeholder
│   └── ...
│
├── views/                      # Page layouts
│   ├── Dashboard.vue          # Main scan view
│   ├── HistoryView.vue        # History timeline
│   ├── AdminView.vue          # Account management
│   └── ...
│
├── services/                   # API integration
│   └── api.ts                 # Axios client + endpoints
│
├── types/                      # TypeScript interfaces
│   └── follower.ts            # Data type definitions
│
└── main.ts                     # App entry point
```

### Database Schema

**scan_history** – Metadata for each scan

```
scan_id (PK)
app_user_id (FK)
reference_profile_id
scan_time
```

**scanned_data** – Individual follower records

```
scan_id (FK)
app_user_id (FK)
reference_profile_id
profile_id (unique per account)
username, full_name
profile_pic_url, profile_pic_id
is_private, is_verified
fbid_v2
```

**diff_records** – Summary of changes

```
diff_id (PK)
app_user_id (FK)
previous_scan_id, current_scan_id
follower_count (new followers)
unfollower_count
diff_file_path (JSON file location)
```

**image_cache** – Local file references

```
profile_id (FK)
image_id (unique hash)
url (Instagram URL)
local_path (disk path)
create_date
```

See [Database Schema](database.md) for full details.

## Key Design Decisions

### 1. Thread-Local Database Connections

Scan workers run in background threads. Each thread maintains its own SQLite connection via `threading.local()` to avoid connection conflicts:

```python
_thread_local = threading.local()

def get_worker_db():
    existing = getattr(_thread_local, "db", None)
    if existing:
        return existing
    _thread_local.db = SqliteDBHandler(db_path)
    return _thread_local.db
```

### 2. Diff Computation

Diffs are computed from the previous scan:

```
new_followers = current_scan - previous_scan
unfollowers = previous_scan - current_scan
```

On first scan, all followers are marked as "new".

### 3. Image Caching Strategy

- **Local Disk**: Primary cache (survives restarts)
- **In-Memory**: Optional hot cache for fast hits
- **URL Hash**: Unique ID per image to detect picture changes

### 4. Multi-User Architecture

Each app user can have multiple Instagram accounts:

```
app_user
├── instagram_account_1
│   └── scan_history
│       └── followers
├── instagram_account_2
│   └── scan_history
│       └── followers
```

Credentials are stored securely; scans are scoped per account.

### 5. Async/Background Processing

Scans run in daemon threads, not blocking HTTP requests:

```
POST /api/scan → Start thread → 202 Accepted
GET /api/scan/status → Poll for progress
```

Frontend polls every 2 seconds while scan is running.

## Request/Response Flow

### Example: Start a Scan

**Request:**

```http
POST /api/scan?profile_id=12345
```

**Response (202 Accepted):**

```json
{
    "message": "scan started"
}
```

**Behind the scenes:**

1. Validates user session and Instagram account
2. Acquires lock to prevent concurrent scans
3. Starts background thread
4. Returns immediately to client

### Example: Get Scan Status

**Request:**

```http
GET /api/scan/status?profile_id=12345
```

**Response (while running):**

```json
{
    "status": "running",
    "started_at": "2026-03-18T10:30:00",
    "last_scan_id": "scan_001",
    "last_scan_at": "2026-03-18T10:45:00",
    "error": null
}
```

**Response (complete):**

```json
{
    "status": "idle",
    "started_at": null,
    "last_scan_id": "scan_002",
    "last_scan_at": "2026-03-18T10:46:00",
    "error": null
}
```

## Performance Characteristics

| Operation       | Time    | Notes                     |
| --------------- | ------- | ------------------------- |
| Start scan      | < 100ms | Returns immediately       |
| Fetch followers | 5-30s   | Depends on follower count |
| Compute diff    | < 1s    | Database queries only     |
| Cache images    | 10-60s  | Parallel downloads        |
| Render diff     | < 500ms | Vue re-render             |

## Error Handling

```
Error Source → Caught Here → Response
├── Bad credentials → auth_service → 401 Unauthorized
├── Scan in progress → scan_runner → 409 Conflict
├── Missing data → persistence → 404 Not Found
├── DB connection error → db_handler → 500 Internal Server Error
└── Instagram API error → scan_worker → 500 + error message
```

Errors in background threads are captured and stored in scan status.

## Scaling Considerations

### Current Limits

- **SQLite**: Single process, file-based
- **Threads**: Browser sends 1 scan request; backend handles 1 background thread
- **Memory**: Follower list loaded into memory during scan

### Future Improvements

- PostgreSQL for concurrent writes
- Redis for session caching
- Celery for distributed task queues
- Elasticsearch for efficient follower search

---

Next: [Backend API Details](backend.md) or [Frontend Guide](frontend.md)
