# Quick Start

Get meerkit up and running in minutes.

## Prerequisites

Before you start, ensure you have:

- **Python** ≥ 3.12
- **Node.js** ≥ 20 with npm
- **Git** (to clone the repository)
- Valid **Instagram session credentials**

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/Tuhin-thinks/meerkit.git
cd meerkit
```

### Step 2: Set Up Python Environment

```bash
# Create a virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
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

#### Getting Instagram Credentials

To obtain the credentials you will later paste into the app:

1. Open Instagram in your browser and log in
2. Open **Developer Tools** (F12 or right-click → Inspect)
3. Go to **Application** → **Cookies** → select **instagram.com**
4. Find and copy the following values:
  - **sessionid** → use as `session_id`
  - **csrftoken** → use as `csrf_token`
  - Your numeric user ID can be found in **Account** → **Settings** → **About this account**

These credentials are stored through the app's account management flow, not through an environment file.

## Running the Application

### Start the Backend

Open Terminal 1:

```bash
source .venv/bin/activate
flask --app backend.app run --debug --port 5000
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

1. **Create/Login to Account** – Use any username/password
2. **Add Instagram Account** – Click "Create Instagram Account" and paste your session credentials
3. **Run a Scan** – Click "Scan Now" to fetch your current followers
4. **View Results** – Once the scan completes, you'll see follower counts and changes

## Verify Installation

### Backend Health Check

```bash
curl http://localhost:5000/api/auth/me
# Should return: null (if not logged in)
```

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
python3 --version  # Should be ≥ 3.12

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
flask --app backend.app run --port 5001

# Frontend – edit frontend/vite.config.ts:
# server: { port: 5174 }
```

### Permission Denied on .venv

```bash
# On Linux/Mac, fix permissions
chmod +x .venv/bin/activate
```

### Instagram Session Expired

Your Instagram `session_id` and `csrf_token` expire after some time. If you see auth errors:

1. Log out and back into Instagram in your browser
2. Get fresh credentials (see "Getting Instagram Credentials" above)
3. Update the Instagram account credentials in the app
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
