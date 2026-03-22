# Meerkit

Fast Instagram follower intelligence for builders who like clear signals, not noise.

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-brightgreen?logo=flask)](https://flask.palletsprojects.com/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

## Why Meerkit

Track who followed, who left, and what changed between scans. Everything runs in your own stack with a Vue frontend and Flask backend.

- Real-time scan status + history
- New followers and unfollowers diffing
- Profile image caching
- Multi-account management
- Follow-back prediction workflows
- Batch unfollow and task monitoring

## Quick Start

```bash
git clone <repo-url>
cd meerkit

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

cd frontend && npm install && cd ..

# terminal 1
flask --app backend.app run --debug --port 5000

# terminal 2
cd frontend && npm run dev
```

Open http://localhost:5173.

## Product Preview

| Login + Automation | Scan History + Analytics |
| --- | --- |
| ![Login](docs/images/meerkit-follower-login.png) | ![Automation](docs/images/meerkit-automation-dashboard.png) |
| ![History](docs/images/meerkit-scan-history.png) | ![Analytics](docs/images/meerkit-scan-history-analytics-graph.png) |

| Discovery + Prediction | Unfollow Flow |
| --- | --- |
| ![Discovery](docs/images/meerkit-discovery-page.png) | ![Unfollow Candidates](docs/images/meerkit-unfollow-candidates-who-dont-follow-back.png) |
| ![Prediction](docs/images/meerkit-intelligent-followback-prediction.png) | ![Unfollow Success](docs/images/meerkit-unfollow-successful.png) |

See the full visual walkthrough: [docs/showcase.md](docs/showcase.md)

## Docs

- Start here: [docs/index.md](docs/index.md)
- Setup: [docs/setup.md](docs/setup.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Prediction flow: [docs/prediction-algorithm.md](docs/prediction-algorithm.md)
- Probability model: [docs/probability-model.md](docs/probability-model.md)
- Backend API: [docs/backend.md](docs/backend.md)
- Frontend: [docs/frontend.md](docs/frontend.md)
- Database: [docs/database.md](docs/database.md)
- Full endpoint list: [docs/api-reference.md](docs/api-reference.md)

Run docs locally:

```bash
pip install mkdocs mkdocs-material
mkdocs serve
```

## Contributing

PRs are welcome. Keep changes focused, add tests where possible, and update docs with feature changes.

## License

MIT. See [LICENSE](LICENSE).
