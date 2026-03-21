# Home

Welcome to **Meerkit** – an Instagram follower tracker web application with real-time scanning, diff tracking, and image caching.

## What is Meerkit?

Meerkit helps you track changes in your Instagram followers over time. It:

- **Scans** your current followers using Instagram session credentials
- **Computes diffs** to identify new followers and unfollowers
- **Caches** profile pictures locally for fast UI rendering
- **Persists data** in a SQLite database with full scan history
- **Provides a modern UI** built with Vue 3 and TailwindCSS

## Key Features

✨ **Real-time Follower Scanning**
: Fetch your current follower list directly from Instagram

📊 **Automatic Diff Computation**
: See who followed and unfollowed since the last scan

🖼️ **Profile Picture Caching**
: Avoid repeated downloads; serve cached images from your server

💾 **Persistent History**
: Store all scans and diffs in a local SQLite database

🔐 **Multi-Account Support**
: Manage multiple Instagram accounts per app user

⚡ **Responsive UI**
: Fast, keyboard-friendly Vue 3 dashboard with real-time status updates

## Dashboard Preview

![Dashboard](images/img-dashboard.png)

See your follower changes at a glance with our modern, responsive interface.

## Quick Navigation

- **New to the project?** → Start with [Quick Start](setup.md)
- **Want to understand the system?** → See [Architecture](architecture.md)
- **Building or extending it?** → Check [Development](development.md)
- **Looking for API details?** → Read [API Reference](api-reference.md)

## Getting Started in 5 Minutes

### 1. Clone and Install

```bash
git clone <repo-url>
cd meerkit
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cd frontend && npm install && cd ..
```

### 2. Configure

No `.env` file is required. If you want a custom Flask secret for local development, export it before starting the backend:

```bash
export APP_SECRET_KEY=dev-secret
```

After logging in to the app, add your Instagram account from the UI using `session_id`, `csrf_token`, and `user_id`.

### 3. Run

**Backend** (Terminal 1):

```bash
source .venv/bin/activate
flask --app backend.app run --debug --port 5000
```

**Frontend** (Terminal 2):

```bash
cd frontend
npm run dev
```

Visit [http://localhost:5173](http://localhost:5173) and start scanning! 🚀

## Architecture Overview

The application consists of:

- **Backend (Flask)** – REST API with scan logic, diff computation, and image caching
- **Frontend (Vue 3)** – Responsive dashboard with real-time status and diff visualization
- **Database (SQLite)** – Scan history, follower data, diffs, and image metadata
- **Workers** – Background threads for concurrent scans and image downloads

[Learn more →](architecture.md)

## Common Tasks

| Task                      | Documentation                     |
| ------------------------- | --------------------------------- |
| Run locally               | [Setup Guide](setup.md)           |
| Understand code structure | [Architecture](architecture.md)   |
| Use the API               | [API Reference](api-reference.md) |
| Deploy to production      | [Development](development.md)     |
| Add a new feature         | [Contributing](contributing.md)   |

## Troubleshooting

**Q: I'm getting ECONNREFUSED errors**  
A: The Flask backend isn't running. Start it first, then the frontend.

**Q: The dashboard shows an error about follower_count**  
A: Update to the latest version – this is a known issue that's been fixed.

**Q: How do I get my Instagram session credentials?**  
A: See the [Setup Guide](setup.md#getting-instagram-credentials) for step-by-step instructions.

## Support

- 📖 Full documentation: See the sidebar navigation
- 🐛 Report issues: [GitHub Issues](https://github.com/Tuhin-thinks/meerkit/issues)
- 💬 Discuss: [GitHub Discussions](https://github.com/Tuhin-thinks/meerkit/discussions)
- 📧 Contact: [Tuhin-thinks/meerkit](https://github.com/Tuhin-thinks/meerkit)

---

Ready to dive in? [Start with the Setup Guide →](setup.md)
