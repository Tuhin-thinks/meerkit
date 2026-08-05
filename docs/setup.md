# Quick Start

Get meerkit up and running in minutes.

## Prerequisites

Before you start, ensure you have:

- **Python** ≥ 3.12
- **Node.js** ≥ 20 with npm
- **Git** (to clone the repository)
- A browser with an active **Instagram session** (you will capture `curl` commands from it)

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/Tuhin-thinks/meerkit.git
cd meerkit
```

### Step 2: Set Up Python Environment

```bash
# Create the project environment and install app + dev dependencies
uv sync --dev
```

### Step 3: Set Up Frontend

```bash
cd frontend
npm install
cd ..
```

### Step 4: Configure Environment

No `.env` file is required.

If you want to override Flask's default development secret, export `APP_SECRET_KEY` before starting the backend:

```bash
export APP_SECRET_KEY=dev-secret-key-change-in-production
```

Optional cache migration flag:

```bash
# Disable writes to legacy user_details cache files
export LEGACY_USER_DETAILS_CACHE_WRITE_ENABLED=0
```

#### Getting Instagram Credentials (Curl Patterns)

Meerkit talks to Instagram through a **curl-pattern API gateway**. Each Instagram operation (fetching your profile, your followers, your following list, follow/unfollow actions) is driven by a `curl` command that you paste into the app. The session credentials (`sessionid`, `csrftoken`, `ds_user_id`) are extracted from these stored commands automatically — you never paste individual credential fields into the gateway itself.

To capture a curl command from your browser:

1. Open Instagram in your browser and log in
2. Open **Developer Tools** (F12 or right-click → Inspect) → **Network** tab
3. Trigger the operation you want to configure (for example, open your profile page or click into your followers list)
4. Find the matching request — for profile data look for a `/api/graphql` request, for lists look for `/api/v1/friendships/...`
5. Right-click the request → **Copy** → **Copy as cURL (bash)**
6. In Meerkit, open **Admin → Account Details → API Scripts**, pick the operation, paste the command, and click **Parse**, review the selected fields, then **Save**

The gateway supports these operations:

| Operation | Used for |
|---|---|
| `fetch_user_profile_data` | Profile info (followers/following counts, bio, etc.) |
| `fetch_followers_list` | Follower list for scans, diffs, and predictions |
| `fetch_following_list` | Following list for scans, diffs, and predictions |
| `follow_user` | Follow actions in automation |
| `unfollow_user` | Unfollow actions in automation |

> **Note:** A pattern is only needed when the app actually uses that operation. A full scan needs `fetch_followers_list` and `fetch_following_list`; automation needs `follow_user` / `unfollow_user`. At least one configured pattern is required before a scan can start.

When you first **create the Instagram account**, the account form still asks for the three session values (`CSRF_TOKEN`, `SESSION_ID`, `USER_ID`) — these can be read straight from the cookies of any curl command you captured (`csrftoken`, `sessionid`, `ds_user_id`).

## Running the Application

### Start the Backend

Open Terminal 1:

```bash
uv run flask --app meerkit.app run --debug --port 5000
```

You should see:

```
 * Running on http://localhost:5000
 * Debug mode: on
```

### Start the Frontend

Open Terminal 2:

```bash
cd frontend
npm run dev
```

You should see:

```
  Local:   http://localhost:5173/
```

### Access the Application

Open your browser and navigate to: **[http://localhost:5173](http://localhost:5173)**

You should see the login page. Create an account or log in to get started!

## First Scan

!!! warning "⚠️ Instagram Rate Limit Warning"
    **Do not bulk follow or unfollow users on Instagram.** Doing so can trigger Instagram's spam detection and may lead to account restrictions.

    | Scenario | Safe daily limit |
    |---|---|
    | General / established accounts | 150 – 200 follow/unfollow actions |
    | New accounts (first few weeks) | Stay under 100 actions |

    - Spread your actions **gradually throughout the day** to avoid detection.
    - If you exceed the limit, Instagram may:
        - Temporarily block your actions (for hours or days)
        - Limit your reach (**shadowban**)
        - **Permanently disable** your account if abuse continues

    > **Note:** These limits are not officially confirmed by Instagram — they are based on extensive community testing and experience with Instagram automation tools.

    Monitor your live Instagram API call count in the in-app **Admin → Account Details → API Usage** tab. See also: [API Monitoring and Limits](showcase.md#5-api-monitoring-and-limits).

1. **Create/Login to Account** – Use any username/password
2. **Add Instagram Account** – Click "Create Instagram Account" and paste your session values (`csrf_token`, `session_id`, `user_id` from your curl command's cookies)
3. **Configure API Patterns** – Open the account's details page → **API Scripts** and save curl commands for `fetch_followers_list` and `fetch_following_list` (see "Getting Instagram Credentials" above)
4. **Run a Scan** – Click "Scan Now" to fetch your current followers
5. **View Results** – Once the scan completes, you'll see follower counts and changes

## Verify Installation

### Backend Health Check

```bash
curl http://localhost:5000/api/auth/me
# Should return: null (if not logged in)
```

### Backend Test Check

```bash
uv run pytest
```

If you prefer running through the interpreter directly, use `uv run python -m pytest`.

If you disabled legacy cache writes, run your test suite once before deploying to ensure your environment no longer depends on legacy cache files.

### Frontend Build Verification

```bash
cd frontend
npm run build
# Should output to frontend/dist/ without errors
```

## Common Setup Issues

### Python Version Mismatch

```bash
# Check your Python version
uv run python --version  # Should be ≥ 3.12

# If not, install Python 3.12+ from python.org
```

### Node Version Mismatch

```bash
# Check your Node version
node --version  # Should be ≥ 20

# If not, update Node from nodejs.org
```

### Port Already in Use

If port 5000 or 5173 is in use, change them:

```bash
# Backend on port 5001
flask --app meerkit.app run --port 5001

# Frontend – edit frontend/vite.config.ts:
# server: { port: 5174 }
```

### Permission Denied on .venv

```bash
# On Linux/Mac, fix permissions
chmod +x .venv/bin/activate
```

### Instagram Session Expired

Your Instagram session cookies (including `sessionid`, `csrftoken`, and the `fb_dtsg` form value) expire after some time. If you see auth errors or non-JSON responses from Instagram:

1. Log out and back into Instagram in your browser
2. Re-capture the affected curl commands (see "Getting Instagram Credentials" above)
3. Update the patterns in the **API Scripts** tab (or re-save the `fetch_user_profile_data` pattern, which is the default source of session values)
4. Run another scan

## Next Steps

- **Learn the Architecture** → [Architecture Guide](architecture.md)
- **Explore the API** → [API Reference](api-reference.md)
- **Development** → [Development Workflow](development.md)
- **Contributing** → [Contributing Guide](contributing.md)

## Need Help?

- 📖 Check the [Architecture](architecture.md) to understand how things work
- 🐛 Open an issue on GitHub
- 💬 Start a discussion for questions

---

**Stuck?** Run the diagnostic:

```bash
# Backend diagnostic
curl -v http://localhost:5000/api/auth/me

# Frontend build diagnostic
cd frontend && npm run build

# Check database
sqlite3 data/app.db ".tables"
```
