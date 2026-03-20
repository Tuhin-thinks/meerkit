# Development

Guidelines for developing, testing, and deploying insta-followers-tracker.

## Local Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Git
- SQLite3 (usually pre-installed)

### Installation

```bash
# Clone repo
git clone https://github.com/tuhin-thinks/insta-followers-tracker.git
cd insta-followers-tracker

# Python setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"

# Node setup
cd frontend
npm install
cd ..
```

### Environment

No `.env` file is required for local development.

If you want a non-default Flask secret in your current shell, export it before starting the backend:

```bash
export APP_SECRET_KEY=dev-secret
export FLASK_DEBUG=1
export FLASK_ENV=development
```

Instagram credentials are added through the authenticated app UI, not from environment variables.

## Running Locally

### Terminal 1: Backend

```bash
source .venv/bin/activate
flask --app backend.app run --debug --port 5000
```

### Terminal 2: Frontend

```bash
cd frontend
npm run dev
```

### Terminal 3: Optional - Watch Backend Changes

```bash
source .venv/bin/activate
watchmedo auto-restart -d backend -p '*.py' -- \
  flask --app backend.app run --debug --port 5000
```

## Code Style & Linting

### Python

```bash
# Format code
black backend/

# Check types
mypy backend/

# Lint
ruff check backend/
ruff check --fix backend/  # Auto-fix issues

# All at once
black backend/ && mypy backend/ && ruff check backend/
```

### Frontend (TypeScript/Vue)

```bash
# Lint
npm run lint

# Format
npm run format

# Type check
npm run type-check
```

## Testing

### Backend Tests

```bash
# Run all tests
pytest

# Run specific file
pytest backend/tests/test_auth_service.py

# Run with coverage
pytest --cov=backend --cov-report=html

# Watch mode (auto-rerun on changes)
pytest-watch
```

### Frontend Tests

```bash
# Run all tests
npm run test

# Watch mode
npm run test:watch

# Coverage
npm run test:coverage
```

## Building for Production

### Frontend Build

```bash
cd frontend
npm run build
# Output: frontend/dist/
```

Features:

- Minification
- Code splitting
- Source maps
- Tree-shaking

Verify build:

```bash
npm run build
# Check dist/ folder size and contents
```

### Backend Production

No build needed, but optimize running:

```bash
# Using Gunicorn (recommended for production)
pip install gunicorn

# Run with 4 worker processes
gunicorn -w 4 -b 0.0.0.0:5000 "backend.app:create_app()"
```

Configuration options:

```bash
gunicorn \
  -w 4 \
  -b 0.0.0.0:5000 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  "backend.app:create_app()"
```

## Debugging

### Python Debugging

With `debugpy` installed:

```bash
# Run Flask with debugger
python -m debugpy --listen 5678 -m flask --app backend.app run --port 5000
```

Then attach your IDE debugger to port 5678.

### Frontend Debugging

Open browser DevTools (F12):

- **Console** – Logs and errors
- **Network** – API requests
- **Vue DevTools** – Component state
- **Performance** – Profiling

### Database Debugging

```bash
# Open interactive SQLite shell
sqlite3 data/app.db

# List tables
.tables

# Schema
.schema scanned_data

# Query
SELECT COUNT(*) FROM scanned_data WHERE scan_id = 'scan_001';

# Export
.mode csv
.output followers.csv
SELECT * FROM scanned_data;

# Import
.read backup.sql
```

### Logs

```bash
# Check Flask logs
tail -f logs.txt

# Backend errors in terminal
# Frontend errors in browser console (F12)
```

## Adding Features

### Adding a Backend Route

1. Create endpoint in `backend/routes/`:

```python
# backend/routes/new_feature.py
from flask import Blueprint, jsonify

bp = Blueprint("new_feature", __name__, url_prefix="/api")

@bp.get("/new-endpoint")
def my_endpoint():
    """Get some data."""
    return jsonify({"data": "value"})
```

2. Register in `backend/app.py`:

```python
from backend.routes.new_feature import bp as new_feature_bp

app.register_blueprint(new_feature_bp)
```

3. Test via:

```bash
curl http://localhost:5000/api/new-endpoint
```

### Adding a Vue Component

1. Create `frontend/src/components/NewComponent.vue`:

```vue
<template>
    <div class="component">
        {{ message }}
    </div>
</template>

<script setup lang="ts">
defineProps<{ message: string }>();
</script>

<style scoped>
.component {
    /* styles */
}
</style>
```

2. Use in parent:

```vue
<script setup>
import NewComponent from "../components/NewComponent.vue";
</script>

<template>
    <NewComponent message="Hello" />
</template>
```

### Adding a New Query

1. Add to `frontend/src/services/api.ts`:

```typescript
export const getNewData = (id: string) =>
    http.get(`/new-endpoint/${id}`).then((r) => r.data);
```

2. Use in component:

```typescript
const { data, isLoading } = useQuery({
    queryKey: ["newData", id],
    queryFn: () => api.getNewData(id),
});
```

## Git Workflow

### Branch Strategy

```bash
# Create feature branch
git checkout -b feature/amazing-feature

# Commit changes
git add backend/routes/new.py
git commit -m "feat: add new endpoint /api/feature"

# Push to branch
git push origin feature/amazing-feature

# Create Pull Request on GitHub
```

### Commit Message Format

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `style:` Formatting (no functional change)
- `refactor:` Code restructuring
- `perf:` Performance improvement
- `test:` Test additions/updates
- `chore:` Dependency updates, tooling

Examples:

```
feat: add image caching endpoint
fix: prevent scan crashes on 404 image
docs: update API reference
test: add tests for diff computation
```

## Documentation

### Updating Docs

Docs are in `docs/` using MkDocs + Material theme:

```bash
# Install mkdocs
pip install mkdocs mkdocs-material

# Serve locally
mkdocs serve
# Navigate to http://localhost:8000

# Build static site
mkdocs build
# Output: site/
```

Add new doc page:

1. Create `docs/new_page.md`
2. Update `mkdocs.yml` navigation

### Code Comments

```python
def complex_calculation(x: int) -> int:
    """Calculate something complex.

    Args:
        x: Input value

    Returns:
        Computed result

    Raises:
        ValueError: If x is negative
    """
    if x < 0:
        raise ValueError("x must be non-negative")
    return x ** 2
```

## Troubleshooting Development Issues

### "ModuleNotFoundError: No module named 'backend'"

```bash
# Ensure backend/ is in sys.path
python -c "import sys; print(sys.path)"

# Install package in dev mode
pip install -e .
```

### "Port 5000 already in use"

```bash
# Find process using port 5000
lsof -i :5000  # On macOS/Linux
# Or change port:
flask --app backend.app run --port 5001
```

### Frontend proxy errors (ECONNREFUSED)

1. Ensure Flask backend is running first
2. Check `frontend/vite.config.ts` has correct proxy target
3. Try 127.0.0.1 instead of localhost

### Database locked error

```bash
# SQLite file is locked (another process using it)
# Solution: Ensure only one Flask instance is running
ps aux | grep flask
```

### Node modules not found

```bash
cd frontend
npm install
npm run dev
```

## Performance Profiling

### Backend

```bash
# Profile with cProfile
python -m cProfile -s cumtime -m flask --app backend.app run

# Use py-spy for sampling
pip install py-spy
py-spy record -o profile.svg -- \
  flask --app backend.app run --port 5000
```

### Frontend

Browser DevTools → Performance tab:

1. Click Record
2. Interact with app
3. Click Stop
4. Analyze flame chart

---

## Deployment

For production deployment options, refer to your infrastructure requirements:

- **Heroku** – Simple cloud deployment with automatic scaling
- **DigitalOcean App Platform** – Managed platform with easy configuration
- **Docker + Docker Compose** – Containerized deployment for any environment
- **Traditional VPS** – Full control with manual server setup (AWS EC2, Linode, Digital Ocean Droplets, etc.)

---

## Contributing

See [Contributing Guide](contributing.md) for full guidelines.

---

Next: [API Reference](api-reference.md) or [Contributing](contributing.md)
