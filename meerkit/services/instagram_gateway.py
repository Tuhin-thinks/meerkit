import json
import logging
from collections.abc import Callable
from typing import TypeVar

import requests

import insta_interface as ii
from meerkit.config import LEGACY_USER_DETAILS_CACHE_WRITE_ENABLED
from meerkit.services import user_details_cache
from meerkit.services.curl_pattern_service import (
    build_request,
    get_pattern,
)
from meerkit.services.exceptions import MissingCurlPatternError
from meerkit.services.instagram_api_usage import instagram_api_usage_tracker
from meerkit.services.instagram_response_cache import (
    load_gateway_response,
    store_gateway_response,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")

_READ_CACHE_CATEGORIES = {
    "user_lookup",
    "user_data_fetch",
    "followers_discovery",
    "following_discovery",
}

_INTERNAL_NAME_MAP: dict[str, str] = {
    "get_user_data": "fetch_user_profile_data",
    "get_target_user_data": "fetch_user_profile_data",
    "get_target_followers_v2": "fetch_followers_list",
    "get_target_following_v2": "fetch_following_list",
    "get_current_followers_v2": "fetch_followers_list",
    "get_current_following_v2": "fetch_following_list",
    "follow_user_by_id": "follow_user",
    "unfollow_user_by_id": "unfollow_user",
}


def _serialize_summary(summary: dict[str, object]) -> object:
    return summary


def _deserialize_summary(payload: object) -> dict[str, object]:
    return payload if isinstance(payload, dict) else {}


def _serialize_user_pk(user_pk: str | None) -> object:
    return user_pk


def _deserialize_user_pk(payload: object) -> str | None:
    return payload if isinstance(payload, str) else None


def _serialize_follower_records(records: list[ii.FollowerUserRecord]) -> object:
    return [record.__dict__ for record in records]


def _deserialize_follower_records(payload: object) -> list[ii.FollowerUserRecord]:
    if not isinstance(payload, list):
        return []
    records: list[ii.FollowerUserRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            records.append(ii.FollowerUserRecord(**item))
        except TypeError:
            continue
    return records


def _parse_user_records(raw: dict, relationship_type: str) -> list[ii.FollowerUserRecord]:
    """Parse user records from either REST v1 or GraphQL response format.

    REST v1: {"users":[{"pk":"...","username":"...",...}]}
    GraphQL: {"data":{"user":{"edge_followed_by":{"edges":[{"node":{...}}]}}}}
    """
    users: list[dict] = []

    # REST v1 format: {"users": [...]}
    if "users" in raw and isinstance(raw["users"], list):
        users = raw["users"]
    else:
        # GraphQL format
        edge_key = "edge_followed_by" if relationship_type == "followers" else "edge_follow"
        edges = raw.get("data", {}).get("user", {}).get(edge_key, {}).get("edges", [])
        users = [edge.get("node", {}) for edge in edges]

    records: list[ii.FollowerUserRecord] = []
    for u in users:
        # REST v1 uses "pk", GraphQL uses "id"
        pk = u.get("pk") or u.get("id") or ""
        records.append(
            ii.FollowerUserRecord(
                pk_id=str(pk),
                id=str(u.get("id") or pk),
                username=u.get("username", ""),
                full_name=u.get("full_name", ""),
                is_private=bool(u.get("is_private", False)),
                profile_pic_url=u.get("profile_pic_url") or "",
                fbid_v2=str(u.get("fbid_v2")) if u.get("fbid_v2") else None,
                profile_pic_id=u.get("profile_pic_id") or None,
                is_verified=bool(u.get("is_verified", False)),
            )
        )
    return records


class InstagramGateway:
    """Thin tracked wrapper around Instagram interface calls used by meerkit services."""

    def _get_session_values(self, profile: ii.InstagramProfile) -> dict:
        return {
            "csrftoken": profile.csrf_token,
            "sessionid": profile.session_id,
            "ds_user_id": profile.user_id,
        }

    def _get_runtime_values(self, **kwargs) -> dict:
        return {k: v for k, v in kwargs.items() if v is not None}

    def _pattern_call(
        self,
        *,
        app_user_id: str,
        reference_profile_id: str,
        internal_name: str,
        profile: ii.InstagramProfile,
        runtime_values: dict | None = None,
    ) -> dict:
        pattern = get_pattern(app_user_id, reference_profile_id, internal_name)
        if not pattern:
            raise MissingCurlPatternError(
                internal_name=internal_name,
                display_name=internal_name.replace("_", " ").title(),
            )

        session_vals = self._get_session_values(profile)
        url, headers, cookies, data_string = build_request(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            internal_name=internal_name,
            session_values=session_vals,
            runtime_values=runtime_values or {},
        )
        http_method = str(pattern.get("http_method", "POST"))

        try:
            if http_method.upper() == "GET":
                resp = requests.get(url, headers=headers, cookies=cookies, timeout=30)
            else:
                resp = requests.post(
                    url, headers=headers, cookies=cookies, data=data_string, timeout=30
                )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.exception(
                "Pattern call failed for %s",
                internal_name,
                extra={
                    "internal_name": internal_name,
                    "status_code": getattr(exc.response, "status_code", None),
                    "response_text": getattr(exc.response, "text", "")[:200] if hasattr(exc.response, "text") else None,
                },
            )
            raise
        except json.JSONDecodeError as exc:
            logger.exception(
                "Pattern call returned non-JSON response for %s (status %s)",
                internal_name,
                resp.status_code,
                extra={
                    "internal_name": internal_name,
                    "status_code": resp.status_code,
                    "response_text": resp.text[:500],
                },
            )
            raise MissingCurlPatternError(
                internal_name=internal_name,
                display_name=internal_name.replace("_", " ").title(),
                message=f"Instagram returned {resp.status_code} with non-JSON body (session may be expired)",
            ) from exc

    def _pattern_call_paginated(
        self,
        *,
        app_user_id: str,
        reference_profile_id: str,
        internal_name: str,
        profile: ii.InstagramProfile,
        runtime_values: dict | None = None,
        max_pages: int = 50,
        page_delay: float = 0.3,
    ) -> dict:
        """Make a paginated request following next_max_id until exhausted.

        Uses the pagination cursor (max_id/next_max_id) returned by the response
        to fetch subsequent pages.

        Returns a merged dict with "users" list from all pages.
        """
        import time

        merged_users: list[dict] = []
        current_runtime = dict(runtime_values or {})
        last_raw: dict = {}

        for _ in range(max_pages):
            raw = self._pattern_call(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                internal_name=internal_name,
                profile=profile,
                runtime_values=current_runtime,
            )
            last_raw = raw

            page_users = raw.get("users", [])
            merged_users.extend(page_users)

            if not page_users:
                break

            next_max_id = raw.get("next_max_id") or raw.get("max_id")
            if not next_max_id:
                break
            current_runtime["max_id"] = next_max_id

            time.sleep(page_delay)

        # Deduplicate users by pk/id across pages
        seen: set[str] = set()
        unique_users: list[dict] = []
        for u in merged_users:
            key = str(u.get("pk") or u.get("id") or "")
            if key and key not in seen:
                seen.add(key)
                unique_users.append(u)

        result = dict(last_raw)
        result["users"] = unique_users
        return result

    def _tracked(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        category: str,
        caller_service: str,
        caller_method: str,
        execute: Callable[[], T],
        cache_key_parts: dict[str, object] | None = None,
        serialize_for_cache: Callable[[T], object] | None = None,
        deserialize_from_cache: Callable[[object], T] | None = None,
        force_refresh: bool = False,
    ) -> T:
        if (
            category in _READ_CACHE_CATEGORIES
            and cache_key_parts is not None
            and deserialize_from_cache is not None
            and not force_refresh
        ):
            cache_hit, payload = load_gateway_response(
                app_user_id=app_user_id,
                instagram_user_id=instagram_user_id,
                category=category,
                key_parts=cache_key_parts,
            )
            if cache_hit:
                instagram_api_usage_tracker.track_cache_hit(
                    app_user_id=app_user_id,
                    instagram_user_id=instagram_user_id,
                    category=category,
                    caller_service=caller_service,
                    caller_method=caller_method,
                )
                return deserialize_from_cache(payload)

        result = instagram_api_usage_tracker.track_call(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category=category,
            caller_service=caller_service,
            caller_method=caller_method,
            execute=execute,
        )

        if (
            category in _READ_CACHE_CATEGORIES
            and cache_key_parts is not None
            and serialize_for_cache is not None
        ):
            try:
                store_gateway_response(
                    app_user_id=app_user_id,
                    instagram_user_id=instagram_user_id,
                    category=category,
                    key_parts=cache_key_parts,
                    payload=serialize_for_cache(result),
                )
            except Exception:
                pass

        return result

    def _lookup_cache_key(self, *, operation: str, username: str) -> dict[str, object]:
        return {
            "operation": operation,
            "username": username.strip().lower(),
        }

    def _summary_cache_key(
        self, *, operation: str, target_user_id: str
    ) -> dict[str, object]:
        return {
            "operation": operation,
            "target_user_id": target_user_id,
        }

    def _relationship_cache_key(
        self,
        *,
        operation: str,
        target_user_id: str,
        relationship_type: str,
    ) -> dict[str, object]:
        return {
            "operation": operation,
            "target_user_id": target_user_id,
            "relationship_type": relationship_type,
        }

    def resolve_target_user_pk(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        username: str,
        caller_service: str,
        caller_method: str,
        force_refresh: bool = False,
    ) -> str | None:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_lookup",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.resolve_target_user_pk(username, profile),
            cache_key_parts=self._lookup_cache_key(
                operation="resolve_target_user_pk",
                username=username,
            ),
            serialize_for_cache=_serialize_user_pk,
            deserialize_from_cache=_deserialize_user_pk,
            force_refresh=force_refresh,
        )

    def get_user_data(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        caller_service: str,
        caller_method: str,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        if not force_refresh:
            cached = user_details_cache.load(app_user_id, instagram_user_id)
            if cached is not None:
                instagram_api_usage_tracker.track_cache_hit(
                    app_user_id=app_user_id,
                    instagram_user_id=instagram_user_id,
                    category="user_data_fetch",
                    caller_service=caller_service,
                    caller_method=caller_method,
                )
                return cached

        def _execute() -> dict[str, object]:
            raw = self._pattern_call(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user_id,
                internal_name="fetch_user_profile_data",
                profile=profile,
            )
            user_data = raw.get("data", {}).get("user") or raw.get("user") or raw
            if isinstance(user_data, dict):
                return user_data
            return raw

        result: dict[str, object] = instagram_api_usage_tracker.track_call(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_data_fetch",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=_execute,
        )
        if LEGACY_USER_DETAILS_CACHE_WRITE_ENABLED:
            try:
                user_details_cache.save(app_user_id, instagram_user_id, result)
            except Exception:
                pass
        return result

    def get_target_user_data(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        target_user_id: str,
        caller_service: str,
        caller_method: str,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        def _execute() -> dict[str, object]:
            raw = self._pattern_call(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user_id,
                internal_name="fetch_user_profile_data",
                profile=profile,
                runtime_values={"target_user_id": target_user_id},
            )
            user_data = raw.get("data", {}).get("user") or raw.get("user") or raw
            if isinstance(user_data, dict):
                return user_data
            return raw

        result: dict[str, object] = self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_data_fetch",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=_execute,
            cache_key_parts=self._summary_cache_key(
                operation="get_target_user_data",
                target_user_id=target_user_id,
            ),
            serialize_for_cache=_serialize_summary,
            deserialize_from_cache=_deserialize_summary,
            force_refresh=force_refresh,
        )
        if LEGACY_USER_DETAILS_CACHE_WRITE_ENABLED:
            try:
                user_details_cache.save_target(
                    app_user_id, instagram_user_id, target_user_id, result
                )
            except Exception:
                pass
        return result

    def get_target_followers_v2(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        target_user_id: str,
        caller_service: str,
        caller_method: str,
        force_refresh: bool = False,
        fetch_at_max: int | None = None,
    ) -> list[ii.FollowerUserRecord]:
        def _execute() -> list[ii.FollowerUserRecord]:
            raw = self._pattern_call_paginated(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user_id,
                internal_name="fetch_followers_list",
                profile=profile,
                runtime_values={
                    "target_user_id": target_user_id,
                    "first": fetch_at_max,
                },
            )
            return _parse_user_records(raw, "followers")

        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="followers_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=_execute,
            cache_key_parts=self._relationship_cache_key(
                operation="get_target_followers_v2",
                target_user_id=target_user_id,
                relationship_type="followers",
            ),
            serialize_for_cache=_serialize_follower_records,
            deserialize_from_cache=_deserialize_follower_records,
            force_refresh=force_refresh,
        )

    def get_target_following_v2(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        target_user_id: str,
        caller_service: str,
        caller_method: str,
        force_refresh: bool = False,
        fetch_at_max: int | None = None,
    ) -> list[ii.FollowerUserRecord]:
        def _execute() -> list[ii.FollowerUserRecord]:
            raw = self._pattern_call_paginated(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user_id,
                internal_name="fetch_following_list",
                profile=profile,
                runtime_values={
                    "target_user_id": target_user_id,
                    "first": fetch_at_max,
                },
            )
            return _parse_user_records(raw, "following")

        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="following_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=_execute,
            cache_key_parts=self._relationship_cache_key(
                operation="get_target_following_v2",
                target_user_id=target_user_id,
                relationship_type="following",
            ),
            serialize_for_cache=_serialize_follower_records,
            deserialize_from_cache=_deserialize_follower_records,
            force_refresh=force_refresh,
        )

    def get_current_followers_v2(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        caller_service: str,
        caller_method: str,
        force_refresh: bool = False,
        fetch_at_max: int | None = None,
    ) -> list[ii.FollowerUserRecord]:
        def _execute() -> list[ii.FollowerUserRecord]:
            raw = self._pattern_call_paginated(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user_id,
                internal_name="fetch_followers_list",
                profile=profile,
                runtime_values={
                    "target_user_id": profile.user_id,
                    "first": fetch_at_max,
                },
            )
            return _parse_user_records(raw, "followers")

        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="followers_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=_execute,
            cache_key_parts=self._relationship_cache_key(
                operation="get_current_followers_v2",
                target_user_id=profile.user_id,
                relationship_type="followers",
            ),
            serialize_for_cache=_serialize_follower_records,
            deserialize_from_cache=_deserialize_follower_records,
            force_refresh=force_refresh,
        )

    def get_current_following_v2(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        caller_service: str,
        caller_method: str,
        force_refresh: bool = False,
        fetch_at_max: int | None = None,
    ) -> list[ii.FollowerUserRecord]:
        def _execute() -> list[ii.FollowerUserRecord]:
            raw = self._pattern_call_paginated(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user_id,
                internal_name="fetch_following_list",
                profile=profile,
                runtime_values={
                    "target_user_id": profile.user_id,
                    "first": fetch_at_max,
                },
            )
            return _parse_user_records(raw, "following")

        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="following_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=_execute,
            cache_key_parts=self._relationship_cache_key(
                operation="get_current_following_v2",
                target_user_id=profile.user_id,
                relationship_type="following",
            ),
            serialize_for_cache=_serialize_follower_records,
            deserialize_from_cache=_deserialize_follower_records,
            force_refresh=force_refresh,
        )

    def follow_user_by_id(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        target_user_id: str,
        target_username: str,
        caller_service: str,
        caller_method: str,
    ) -> int:
        def _execute() -> int:
            raw = self._pattern_call(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user_id,
                internal_name="follow_user",
                profile=profile,
                runtime_values={
                    "target_user_id": target_user_id,
                    "username": target_username,
                },
            )
            if raw.get("status") == "ok":
                return 200
            return 400

        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="action_follow",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=_execute,
        )

    def unfollow_user_by_id(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        target_user_id: str,
        target_username: str,
        caller_service: str,
        caller_method: str,
    ) -> int:
        def _execute() -> int:
            raw = self._pattern_call(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user_id,
                internal_name="unfollow_user",
                profile=profile,
                runtime_values={
                    "target_user_id": target_user_id,
                    "username": target_username,
                },
            )
            if raw.get("status") == "ok":
                return 200
            return 400

        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="action_unfollow",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=_execute,
        )

    def resolve_target_user_pk_for_automation(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        username: str,
        caller_service: str,
        caller_method: str,
        force_refresh: bool = False,
    ) -> str | None:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_lookup",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.resolve_target_user_pk(username, profile),
            cache_key_parts=self._lookup_cache_key(
                operation="resolve_target_user_pk_for_automation",
                username=username,
            ),
            serialize_for_cache=_serialize_user_pk,
            deserialize_from_cache=_deserialize_user_pk,
            force_refresh=force_refresh,
        )


instagram_gateway = InstagramGateway()
