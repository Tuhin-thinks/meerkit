
# Meerkit – Instagram Unfollower Tracker & Growth Toolkit

👉🏻 Find out who doesn't follow you back on Instagram and generate a clean unfollower list.

👉🏻 **Meerkit** helps you compare followers vs following, track changes over time, and grow your account with data-driven insights.

👉🏻 Runs locally with full control over your data.

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-brightgreen?logo=flask)](https://flask.palletsprojects.com/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🚀 What Meerkit Does

- Find Instagram unfollowers (who doesn’t follow you back)
- Compare followers vs following
- Track follower changes over time
- Batch follow / unfollow with task monitoring
- Predict follow-back probability (growth insights)
- Manage multiple Instagram accounts

---

## 💡 Why Meerkit

Unlike typical Instagram unfollower tools, Meerkit is built for **analysis + automation + experimentation**:

- Real-time scan status + history
- Accurate follower/unfollower diffing
- Profile image caching for faster UI
- Follow-back prediction workflows
- Automation with visibility (not blind scripts)

---

## ⚠️ Important Note

Meerkit is intended for controlled usage and experimentation.

- Use responsibly to avoid platform restrictions  
- Automation features are optional and configurable  
- Runs locally on your system (no third-party service dependency)

---

## ⚡ Quick Start

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

Open [http://localhost:5173](http://localhost:5173).

---

## 📊 Product Preview

| Login + Automation                               | Scan History + Analytics                                           |
| ------------------------------------------------ | ------------------------------------------------------------------ |
| ![Login](docs/images/meerkit-follower-login.png) | ![Automation](docs/images/meerkit-automation-dashboard.png)        |
| ![History](docs/images/meerkit-scan-history.png) | ![Analytics](docs/images/meerkit-scan-history-analytics-graph.png) |

| Discovery + Prediction                                                   | Unfollow Flow                                                                            |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| ![Discovery](docs/images/meerkit-discovery-page.png)                     | ![Unfollow Candidates](docs/images/meerkit-unfollow-candidates-who-dont-follow-back.png) |
| ![Prediction](docs/images/meerkit-intelligent-followback-prediction.png) | ![Unfollow Success](docs/images/meerkit-unfollow-successful.png)                         |

See full walkthrough: [docs/showcase.md](docs/showcase.md)

---

## 📚 Documentation

* Start here: [docs/index.md](docs/index.md)
* Setup: [docs/setup.md](docs/setup.md)
* Architecture: [docs/architecture.md](docs/architecture.md)
* Prediction flow: [docs/prediction-algorithm.md](docs/prediction-algorithm.md)
* Probability model: [docs/probability-model.md](docs/probability-model.md)
* Backend API: [docs/backend.md](docs/backend.md)
* Frontend: [docs/frontend.md](docs/frontend.md)
* Database: [docs/database.md](docs/database.md)
* Full endpoint list: [docs/api-reference.md](docs/api-reference.md)

Run docs locally:

```bash
pip install mkdocs mkdocs-material
mkdocs serve
```

---

## 🤝 Contributing

PRs are welcome. Keep changes focused, add tests where possible, and update docs with feature changes.

---

## 📄 License

MIT. See [LICENSE](LICENSE).
