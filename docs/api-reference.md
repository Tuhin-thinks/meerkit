# API Reference

Complete REST API endpoint documentation with request/response examples.

## Base URL

```
http://localhost:5000/api (development)
https://meerkit.your-domain.com/api (production)
```

## Authentication

All endpoints except `/auth/register` and `/auth/login` require a valid session (automatically managed via Flask sessions).

**Session Management:**

- Sessions are stored in browser cookies
- Session data is validated on each request
- Logout clears session

## Error Responses

All errors return JSON with status code:

```json
{
    "error": "Description of what went wrong"
}
```

**Common Status Codes:**

- `200 OK` – Success
- `201 Created` – Resource created
- `202 Accepted` – Async operation started
- `400 Bad Request` – Invalid input
- `401 Unauthorized` – Not authenticated
- `404 Not Found` – Resource not found
- `409 Conflict` – State conflict (e.g., scan already running)
- `500 Internal Server Error` – Server error

---

## Authentication Endpoints

### POST /auth/register

Register a new app user account.

**Request:**

```json
{
    "name": "username",
    "password": "password123"
}
```

**Response (201 Created):**

```json
{
    "app_user_id": "user_abc123",
    "name": "username",
    "instagram_users": [],
    "active_instagram_user": null
}
```

**Errors:**

- `400` – Missing name/password or user already exists

---

### POST /auth/login

Authenticate user and create session.

**Request:**

```json
{
    "name": "username",
    "password": "password123"
}
```

**Response (200 OK):**

```json
{
  "app_user_id": "user_abc123",
  "name": "username",
  "instagram_users": [{
    "instagram_user_id": "ig_001",
    "name": "My Instagram",
    "username": "@myusername",
    "user_id": "12345",
    ...
  }],
  "active_instagram_user": {
    "instagram_user_id": "ig_001",
    ...
  }
}
```

**Errors:**

- `401` – Invalid credentials

---

### POST /auth/logout

Clear session.

**Request:**

```bash
curl -X POST http://localhost:5000/api/auth/logout
```

**Response (200 OK):**

```json
{
    "ok": true
}
```

---

### GET /auth/me

Get current user context.

**Request:**

```bash
curl http://localhost:5000/api/auth/me
```

**Response (200 OK - Logged In):**

```json
{
  "app_user_id": "user_abc123",
  "name": "username",
  "instagram_users": [...],
  "active_instagram_user": {...}
}
```

**Response (200 OK - Not Logged In):**

```json
null
```

---

## Instagram User Endpoints

### GET /auth/instagram-users

List all Instagram accounts for current app user.

**Request:**

```bash
curl http://localhost:5000/api/auth/instagram-users
```

**Response (200 OK):**

```json
[
    {
        "instagram_user_id": "ig_001",
        "name": "My Instagram",
        "username": "@myusername",
        "user_id": "12345",
        "csrf_token": "...",
        "session_id": "...",
        "created_at": "2026-03-18T10:00:00",
        "csrf_token_added_at": "2026-03-18T10:00:00",
        "session_id_added_at": "2026-03-18T10:00:00"
    }
]
```

---

### POST /auth/instagram-users

Add a new Instagram account.

**Request:**

```json
{
    "name": "Display Name",
    "csrf_token": "...",
    "session_id": "...",
    "user_id": "12345"
}
```

**Response (201 Created):**

```json
{
  "instagram_user": {
    "instagram_user_id": "ig_NEW",
    ...
  },
  "me": {
    "app_user_id": "user_abc123",
    ...
  }
}
```

**Errors:**

- `401` – Not logged in
- `400` – Missing or invalid fields

---

### GET /auth/instagram-users/{instagram_user_id}

Get details for one Instagram account.

**Request:**

```bash
curl http://localhost:5000/api/auth/instagram-users/ig_001
```

**Response (200 OK):**

```json
{
  "instagram_user_id": "ig_001",
  "name": "My Instagram",
  ...
}
```

**Errors:**

- `401` – Not logged in
- `404` – Account not found

---

### PATCH /auth/instagram-users/{instagram_user_id}

Update Instagram account (display name and/or credentials).

**Request:**

```json
{
    "display_name": "New Name",
    "cookie_string": "sessionid=...; csrftoken=..."
}
```

**Response (200 OK):**

```json
{
  "instagram_user": {...},
  "me": {...},
  "message": "Instagram account updated"
}
```

---

### POST /auth/instagram-users/{instagram_user_id}/select

Set active Instagram account for subsequent scans.

**Request:**

```bash
curl -X POST http://localhost:5000/api/auth/instagram-users/ig_001/select
```

**Response (200 OK):**

```json
{
  "active_instagram_user": {...},
  "message": "Active account set to My Instagram",
  "me": {...}
}
```

---

### DELETE /auth/instagram-users/{instagram_user_id}

Delete one Instagram account.

**Request:**

```bash
curl -X DELETE http://localhost:5000/api/auth/instagram-users/ig_001
```

**Response (200 OK):**

```json
{
  "ok": true,
  "me": {...}
}
```

---

### DELETE /auth/instagram-users

Delete all Instagram accounts.

**Request:**

```bash
curl -X DELETE http://localhost:5000/api/auth/instagram-users
```

**Response (200 OK):**

```json
{
  "ok": true,
  "me": {...}
}
```

---

## Scan Endpoints

### POST /scan

Start a new follower scan.

**Query Parameters:**

- `profile_id` (required) – Instagram user ID to scan

**Request:**

```bash
curl -X POST http://localhost:5000/api/scan?profile_id=12345
```

**Response (202 Accepted - Started):**

```json
{
    "message": "scan started"
}
```

**Response (409 Conflict - Already Running):**

```json
{
    "error": "Scan already in progress"
}
```

---

### GET /scan/status

Get scan status and metadata.

**Query Parameters:**

- `profile_id` (required) – Instagram user ID

**Request:**

```bash
curl http://localhost:5000/api/scan/status?profile_id=12345
```

**Response (Running):**

```json
{
    "status": "running",
    "started_at": "2026-03-18T10:30:00",
    "last_scan_id": "scan_abc123",
    "last_scan_at": "2026-03-18T10:29:00",
    "error": null
}
```

**Response (Idle):**

```json
{
    "status": "idle",
    "started_at": null,
    "last_scan_id": "scan_abc123",
    "last_scan_at": "2026-03-18T10:29:00",
    "error": null
}
```

**Response (Error):**

```json
{
    "status": "error",
    "started_at": "2026-03-18T10:30:00",
    "last_scan_id": null,
    "last_scan_at": null,
    "error": "Instagram API returned 429: Rate limit exceeded"
}
```

**Polling Strategy:**

```javascript
// Poll every 2s while running, stop when idle/error
const pollStatus = async () => {
    const response = await fetch("/api/scan/status?profile_id=12345");
    const status = await response.json();

    if (status.status === "running") {
        setTimeout(pollStatus, 2000); // Poll again in 2s
    }
};
```

---

## Diff & Summary Endpoints

### GET /summary

Get latest scan summary with follower count and diff totals.

**Query Parameters:**

- `profile_id` (required) – Instagram user ID

**Request:**

```bash
curl http://localhost:5000/api/summary?profile_id=12345
```

**Response (200 OK):**

```json
{
    "scan_id": "scan_abc123",
    "timestamp": "2026-03-18T10:29:00",
    "follower_count": 5432,
    "diff_id": "diff_xyz789",
    "new_count": 42,
    "unfollow_count": 8
}
```

**Response (200 OK - No Scan Yet):**

```json
null
```

---

### GET /diff/latest

Get latest diff (new followers + unfollowers).

**Query Parameters:**

- `profile_id` (required) – Instagram user ID

**Request:**

```bash
curl http://localhost:5000/api/diff/latest?profile_id=12345
```

**Response (200 OK):**

```json
{
  "diff_id": "diff_xyz789",
  "scan_id": "scan_abc123",
  "timestamp": "2026-03-18T10:29:00",
  "new_followers": [
    {
      "pk_id": "user_1",
      "username": "newuser1",
      "full_name": "New User",
      "profile_pic_url": "https://...",
      "is_verified": false,
      "is_private": false
    }
  ],
  "unfollowers": [
    {
      "pk_id": "user_2",
      "username": "leftuser",
      "full_name": "Left User",
      ...
    }
  ],
  "new_count": 1,
  "unfollow_count": 1
}
```

---

### GET /diff/{diff_id}

Get specific diff by ID.

**Request:**

```bash
curl http://localhost:5000/api/diff/diff_xyz789?profile_id=12345
```

**Response (200 OK):**

```json
{
  "diff_id": "diff_xyz789",
  ...
}
```

**Errors:**

- `404` – Diff not found

---

### GET /history

Get full scan history.

**Query Parameters:**

- `profile_id` (required) – Instagram user ID

**Request:**

```bash
curl http://localhost:5000/api/history?profile_id=12345
```

**Response (200 OK):**

```json
[
    {
        "scan_id": "scan_abc123",
        "diff_id": "diff_xyz789",
        "timestamp": "2026-03-18T10:29:00",
        "follower_count": 42,
        "unfollower_count": 8
    },
    {
        "scan_id": "scan_abc122",
        "diff_id": "diff_xyz788",
        "timestamp": "2026-03-18T09:15:00",
        "follower_count": 35,
        "unfollower_count": 2
    }
]
```

---

## Image Endpoints

### GET /image/{pk_id}

Get cached profile picture for a follower.

**Path Parameters:**

- `pk_id` (required) – Follower's Instagram user ID

**Request:**

```bash
curl http://localhost:5000/api/image/user_12345 \
  -H "Range: bytes=0-1048575" \
  --output profile.jpg
```

**Response (200 OK):**

- Returns image file (PNG/JPG)
- Cache-Control: 7 days
- Content-Type: image/jpeg or image/png

**Response (404 Not Found):**

```
Image not cached yet
```

**Example HTML:**

```html
<img src="/api/image/user_12345" alt="Profile" />
```

---

## Rate Limiting

Currently no rate limiting implemented, but planned for production:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1234567890
```

---

## Headers

**Request Headers:**

```
Content-Type: application/json
Accept: application/json
```

**Response Headers:**

```
Content-Type: application/json
Cache-Control: max-age=300 (for images)
ETag: "abc123" (for caching)
```

---

## Examples

### Complete Scan Flow

```bash
# 1. Login
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"name": "user1", "password": "pass"}'

# 2. Add Instagram account
curl -X POST http://localhost:5000/api/auth/instagram-users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My IG",
    "csrf_token": "...",
    "session_id": "...",
    "user_id": "12345"
  }'

# 3. Select active account
curl -X POST http://localhost:5000/api/auth/instagram-users/ig_001/select

# 4. Start scan
curl -X POST http://localhost:5000/api/scan?profile_id=12345

# 5. Poll status (every 2 seconds)
curl http://localhost:5000/api/scan/status?profile_id=12345

# 6. Get results
curl http://localhost:5000/api/summary?profile_id=12345
curl http://localhost:5000/api/diff/latest?profile_id=12345
```

---

Next: [Backend Architecture](backend.md) or [Contributing](contributing.md)
