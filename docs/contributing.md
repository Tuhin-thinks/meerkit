# Contributing

Guidelines for contributing to meerkit.

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions.

## Getting Started

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/Tuhin-thinks/meerkit.git`
3. **Create a branch**: `git checkout -b feature/your-feature`
4. **Make changes** following the guidelines below
5. **Test** your changes thoroughly
6. **Push** to your fork
7. **Create a Pull Request** against `main`

See [Development Guide](development.md) for detailed setup instructions.

## Code Style

### Python

All Python code must pass:

```bash
# Format with Black
black backend/

# Type check with mypy
mypy backend/

# Lint with ruff
ruff check backend/ --fix
```

**Guidelines:**

- PEP 8 compliant (enforced by Black)
- Type hints required for public functions
- Docstrings for classes and functions
- Max line length: 100 characters

**Example:**

```python
def get_follower_count(profile_id: str) -> int:
    """Get total follower count for a profile.

    Args:
        profile_id: Instagram profile ID

    Returns:
        Total follower count

    Raises:
        ValueError: If profile not found
    """
    count = db.query_follower_count(profile_id)
    if count is None:
        raise ValueError(f"Profile {profile_id} not found")
    return count
```

### TypeScript/Vue

All frontend code must pass:

```bash
# Type check
npm run type-check

# Lint
npm run lint

# Format
npm run format
```

**Guidelines:**

- TypeScript strict mode enabled
- Vue 3 Composition API (not Options API)
- Props with full types
- Named slots where appropriate

**Example:**

```vue
<script setup lang="ts">
interface Props {
    follower: FollowerRecord;
    isSelected?: boolean;
}

defineProps<Props>();
defineEmits<{ select: [id: string] }>();
</script>

<template>
    <div class="card">
        {{ follower.username }}
    </div>
</template>
```

## Commit Messages

Use conventional commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `style:` Formatting (no logic change)
- `refactor:` Code restructuring
- `perf:` Performance improvement
- `test:` Tests
- `chore:` Tooling, dependencies

**Examples:**

```
feat(scan): add image caching to scan results

- Store profile images locally
- Serve via /api/image/<pk_id> endpoint
- 7-day cache expiration

Closes #42

fix(frontend): prevent undefined.toLocaleString crash

Adds follower_count to summary API response

docs: update API reference with new endpoints
```

## Pull Request Process

1. **Update** the README if needed
2. **Update** docs in `docs/` if adding features
3. **Add tests** for new functionality
4. **Ensure** all tests pass: `pytest` and `npm test`
5. **Request review** from maintainers

**PR Template:**

```markdown
## Description

Brief description of changes

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update

## Related Issues

Closes #123

## Testing

- [ ] Unit tested
- [ ] Tested locally
- [ ] No regressions

## Checklist

- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No new warnings generated
```

## Issues

### Reporting Bugs

Include:

- Steps to reproduce
- Expected behavior
- Actual behavior
- Screenshots/logs if applicable
- System info (OS, Python/Node version)

### Feature Requests

Describe:

- Use case
- Expected behavior
- Why it's useful
- Any alternatives considered

## Testing

### Adding Tests

All new features should include tests.

**Backend:**

```python
# tests/test_scan_runner.py
import pytest
from backend.services import scan_runner

def test_start_scan_success(mock_instagram_api):
    """Test starting a scan successfully."""
    started = scan_runner.start_scan(
        app_user_id="user1",
        profile_id="12345",
        data_dir=Path("data"),
        credentials={...},
        target_user_id="12345"
    )
    assert started is True

def test_start_scan_conflict():
    """Test that concurrent scans return False."""
    # Implementation
```

**Frontend:**

```typescript
// src/__tests__/Dashboard.spec.ts
import { render, screen } from "@testing-library/vue";
import Dashboard from "@/views/Dashboard.vue";

describe("Dashboard.vue", () => {
    it("displays follower count", () => {
        render(Dashboard, {
            props: { profileId: "12345" },
        });
        expect(screen.getByText(/followers/)).toBeInTheDocument();
    });
});
```

Run tests:

```bash
# Backend
pytest

# Frontend
npm run test
```

## Documentation

### Update Docs for Changes

If you're adding/changing features, update relevant docs:

- `README.md` – For overview changes
- `docs/api-reference.md` – For API changes
- `docs/architecture.md` – For architecture changes
- `docs/backend.md` / `docs/frontend.md` – For module changes

Docs are built with MkDocs:

```bash
pip install mkdocs mkdocs-material
mkdocs serve  # Check locally at http://localhost:8000
```

## Performance Considerations

- Batch database queries when possible
- Cache frequently accessed data
- Use indexes for common queries
- Profile before optimizing (use py-spy, browser DevTools)

## Security

- Never commit credentials or secrets
- Use environment variables for sensitive data
- Validate/sanitize all user input
- Use parameterized SQL queries (already done)
- Keep dependencies updated

## Licensing

By contributing, you agree to license your work under the MIT License.

## Questions?

- Check [Architecture](architecture.md)
- Read [Development Guide](development.md)
- Open an issue for discussion
- Reach out to maintainers

## Review Criteria

Pull requests should:

- ✅ Pass all tests
- ✅ Follow code style guidelines
- ✅ Include meaningful commit messages
- ✅ Have clear, descriptive PR description
- ✅ Update documentation if needed
- ✅ Not introduce new warnings/errors
- ✅ Have reasonable test coverage

## Recognition

Contributors will be recognized in:

- `CONTRIBUTORS.md` file
- GitHub contributors graph
- Release notes

Thank you for contributing! 🚀
