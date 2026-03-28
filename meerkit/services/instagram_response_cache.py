import hashlib
import json
from datetime import datetime
from pathlib import Path
from re import sub
from typing import Any

from meerkit.config import CACHE_DIR

CACHE_VERSION = 1
_CACHE_NAMESPACE = "instagram_gateway"
_CACHE_ROOT = CACHE_DIR


def _safe_fragment(value: str) -> str:
    normalized = value.strip().lower()
    normalized = sub(r"[^a-z0-9_-]+", "_", normalized)
    normalized = sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown"


def _stringify_key_parts(key_parts: dict[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in key_parts.items():
        normalized[str(key)] = str(value)
    return normalized


def _cache_file_path(
    *,
    app_user_id: str,
    instagram_user_id: str,
    category: str,
    key_parts: dict[str, object],
) -> Path:
    normalized_parts = _stringify_key_parts(key_parts)
    raw_key = json.dumps(normalized_parts, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:20]
    op_name = _safe_fragment(normalized_parts.get("operation", "entry"))
    filename = f"{op_name}_{digest}.json"
    return (
        _CACHE_ROOT
        / app_user_id
        / instagram_user_id
        / _CACHE_NAMESPACE
        / _safe_fragment(category)
        / filename
    )


def load_gateway_response(
    *,
    app_user_id: str,
    instagram_user_id: str,
    category: str,
    key_parts: dict[str, object],
) -> tuple[bool, Any]:
    """Load a cached gateway payload. Returns (hit, payload)."""
    cache_path = _cache_file_path(
        app_user_id=app_user_id,
        instagram_user_id=instagram_user_id,
        category=category,
        key_parts=key_parts,
    )
    if not cache_path.exists():
        return False, None

    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            envelope = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False, None

    if not isinstance(envelope, dict):
        return False, None

    expected_parts = _stringify_key_parts(key_parts)
    if (
        envelope.get("version") != CACHE_VERSION
        or envelope.get("namespace") != _CACHE_NAMESPACE
        or envelope.get("app_user_id") != app_user_id
        or envelope.get("instagram_user_id") != instagram_user_id
        or envelope.get("category") != category
        or envelope.get("key_parts") != expected_parts
    ):
        return False, None

    return True, envelope.get("payload")


def store_gateway_response(
    *,
    app_user_id: str,
    instagram_user_id: str,
    category: str,
    key_parts: dict[str, object],
    payload: Any,
) -> str:
    cache_path = _cache_file_path(
        app_user_id=app_user_id,
        instagram_user_id=instagram_user_id,
        category=category,
        key_parts=key_parts,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    envelope = {
        "version": CACHE_VERSION,
        "namespace": _CACHE_NAMESPACE,
        "cached_at": datetime.now().isoformat(),
        "app_user_id": app_user_id,
        "instagram_user_id": instagram_user_id,
        "category": category,
        "key_parts": _stringify_key_parts(key_parts),
        "payload": payload,
    }

    temp_path = cache_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2)
    temp_path.replace(cache_path)
    return str(cache_path)
