import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import meerkit.services.instagram_response_cache as response_cache
import meerkit.services.user_details_cache as user_cache


def _write_gateway_envelope(path: Path, age_hours: float, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "version": response_cache.CACHE_VERSION,
        "namespace": response_cache._CACHE_NAMESPACE,
        "cached_at": (datetime.now() - timedelta(hours=age_hours)).isoformat(),
        "app_user_id": "app_1",
        "instagram_user_id": "ig_1",
        "category": "user_data_fetch",
        "key_parts": {"operation": "get_target_user_data", "target_user_id": "t_1"},
        "payload": payload,
    }
    path.write_text(json.dumps(envelope), encoding="utf-8")


def test_gateway_response_cache_expires_after_max_age(monkeypatch, tmp_path):
    monkeypatch.setattr(response_cache, "_CACHE_ROOT", tmp_path)
    key_parts = {"operation": "get_target_user_data", "target_user_id": "t_1"}
    cache_path = response_cache._cache_file_path(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        category="user_data_fetch",
        key_parts=key_parts,
    )
    _write_gateway_envelope(cache_path, age_hours=25, payload={"follower_count": 42})

    hit, payload = response_cache.load_gateway_response(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        category="user_data_fetch",
        key_parts=key_parts,
        max_age_hours=24,
    )

    assert hit is False
    assert payload is None


def test_gateway_response_cache_hits_within_max_age(monkeypatch, tmp_path):
    monkeypatch.setattr(response_cache, "_CACHE_ROOT", tmp_path)
    key_parts = {"operation": "get_target_user_data", "target_user_id": "t_1"}
    cache_path = response_cache._cache_file_path(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        category="user_data_fetch",
        key_parts=key_parts,
    )
    _write_gateway_envelope(cache_path, age_hours=1, payload={"follower_count": 42})

    hit, payload = response_cache.load_gateway_response(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        category="user_data_fetch",
        key_parts=key_parts,
        max_age_hours=24,
    )

    assert hit is True
    assert payload == {"follower_count": 42}


def test_gateway_response_cache_keeps_forever_without_max_age(monkeypatch, tmp_path):
    monkeypatch.setattr(response_cache, "_CACHE_ROOT", tmp_path)
    key_parts = {"operation": "get_target_user_data", "target_user_id": "t_1"}
    cache_path = response_cache._cache_file_path(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        category="user_data_fetch",
        key_parts=key_parts,
    )
    _write_gateway_envelope(cache_path, age_hours=25, payload={"follower_count": 42})

    hit, payload = response_cache.load_gateway_response(
        app_user_id="app_1",
        instagram_user_id="ig_1",
        category="user_data_fetch",
        key_parts=key_parts,
        max_age_hours=None,
    )

    assert hit is True
    assert payload == {"follower_count": 42}


def test_user_details_cache_expires_after_ttl(monkeypatch, tmp_path):
    monkeypatch.setattr(user_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(user_cache, "USER_DETAILS_CACHE_TTL_HOURS", 24)
    target_path = user_cache._target_path("app_1", "ig_1", "t_1")
    user_cache._write(target_path, {"account_followers_count": 7})
    data = json.loads(target_path.read_text(encoding="utf-8"))
    data["cached_at"] = (datetime.now() - timedelta(hours=25)).isoformat()
    target_path.write_text(json.dumps(data), encoding="utf-8")

    assert user_cache.load_target("app_1", "ig_1", "t_1") is None


def test_user_details_cache_hits_within_ttl(monkeypatch, tmp_path):
    monkeypatch.setattr(user_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(user_cache, "USER_DETAILS_CACHE_TTL_HOURS", 24)
    target_path = user_cache._target_path("app_1", "ig_1", "t_1")
    user_cache._write(target_path, {"account_followers_count": 7})

    loaded = user_cache.load_target("app_1", "ig_1", "t_1")

    assert loaded is not None
    assert loaded["account_followers_count"] == 7
