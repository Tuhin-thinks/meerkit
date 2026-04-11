---
description: "Rules for writing Python code"
applyTo: "**/*.py"
---

# Python Code Standards

## Core Mindset

- Think before you type. Every boundary — function, class, module — must justify its existence.
- Optimize for readability and long-term maintainability, not cleverness.
- First-principles over patterns: solve the actual problem, not a hypothetical one.
- YAGNI: don't abstract until the duplication or pain is real.

---

## Architecture & Design

- Each module, class, and function has **one clear responsibility**.
- Business logic never leaks into I/O layers (DB, HTTP, files) and vice versa.
- Inject dependencies; never instantiate concrete dependencies deep inside logic.
- Side effects must be explicit — never hidden inside pure-looking functions.
- Minimize mutable shared state. Pass data explicitly rather than storing in instance variables or globals.
- Module-level singletons only for stateless utilities (loggers, config). Never for stateful services.

**Before adding a new abstraction:** Does this simplify call sites or just add indirection? Is this solving a real problem or a hypothetical one?

**Before adding a new dependency:** What's the blast radius if it breaks? Can stdlib solve this instead?

---

## Typing (Python 3.12+)

Use the modern syntax — no legacy imports unless maintaining old code.

```python
# unions and optionals
def get_user(id: int) -> User | None: ...

# type aliases — only when the alias genuinely aids readability
type UserID = int
type Matrix = list[list[float]]

# generics — only when the function is truly generic, not just to look fancy
def first[T](items: list[T]) -> T | None:
    return items[0] if items else None

# TypeVar still valid for constrained generics
from typing import TypeVar
Numeric = TypeVar("Numeric", int, float)

# cast — use sparingly, only at trust boundaries (e.g., parsing external data)
from typing import cast
user = cast(User, raw_data)

# TypedDict for structured dicts crossing boundaries
from typing import TypedDict
class EventPayload(TypedDict):
    user_id: int
    action: str
```

Rules:

- All public function signatures must have type annotations.
- Prefer `X | None` over `Optional[X]`. Never import `Optional` in new code.
- Use Pydantic or dataclasses for structured data, not raw dicts across module boundaries.
- Don't reach for generics, `cast`, or `TypeAlias` unless there's a concrete reason — plain annotations cover 90% of cases.

---

## Functions & Classes

- Functions do **one thing**. ~20–30 lines max; extract if longer.
- Avoid boolean flag parameters — use two functions or an enum.
- Prefer returning values over mutating arguments.
- `__init__` only assigns. No logic, I/O, or heavy computation inside it.
- Use dataclasses for data containers; regular classes for behavior.
- If a class has 6+ public methods, question whether it's doing too much.

---

## Error Handling & Logging

- Raise specific exceptions. Create custom domain exceptions for business errors.
- Catch the narrowest exception possible. Never `except: pass`.
- Errors from external systems (DB, HTTP) must be caught at the boundary and re-raised as domain errors.
- Use `logging`, never `print` in production. Log at the right level: `debug` for internals, `info` for lifecycle events, `warning` for recoverable issues, `error` for failures.

---

## Code Quality Defaults

- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants. Booleans read as predicates: `is_active`, `has_permission`. No vague suffixes like `manager`, `handler`, `data` alone.
- **Imports**: absolute only, no wildcards, ordered stdlib → third-party → local (`isort`).
- **Async**: only when genuinely doing I/O. No blocking calls inside `async def` — use `asyncio.to_thread`. Use `asyncio.gather` for concurrent independent tasks.
- **Config**: no hardcoded env-specific values. Use env vars or a settings object.
- **Formatting**: `black` + `ruff`. Must pass both before review.
- **Docstrings**: one-line summary for public functions/classes. Add Args/Returns/Raises only for non-obvious behavior.

---

## Hard No's

| Anti-pattern                          | Fix                              |
| ------------------------------------- | -------------------------------- |
| Mutable default args `def f(x=[])`    | Use `None`, assign inside        |
| Catching broad `Exception` silently   | Catch specific, log, re-raise    |
| Deep nesting (3+ levels)              | Early returns, extract functions |
| Logic in `__init__`                   | Factory methods or service layer |
| `global` in business logic            | Pass state explicitly            |
| Magic numbers/strings inline          | Named constants or enums         |
| Returning `None` to signal failure    | Raise an exception               |
| Abstractions with no current use case | Delete it, add when needed       |
