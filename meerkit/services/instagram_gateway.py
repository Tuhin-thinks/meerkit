from collections.abc import Callable
from typing import TypeVar

import insta_interface as ii
from meerkit.services import user_details_cache
from meerkit.services.instagram_api_usage import instagram_api_usage_tracker
from meerkit.services.instagram_response_cache import (
    load_gateway_response,
    store_gateway_response,
)

T = TypeVar("T")

_READ_CACHE_CATEGORIES = {
    "user_lookup",
    "user_data_fetch",
    "followers_discovery",
    "following_discovery",
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


class InstagramGateway:
    """Thin tracked wrapper around Instagram interface calls used by meerkit services."""

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
                # Cache writes must never break successful API flows.
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

        result: dict[str, object] = instagram_api_usage_tracker.track_call(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_data_fetch",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_user_data(profile=profile),
        )
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
        if not force_refresh:
            cached = user_details_cache.load_target(
                app_user_id, instagram_user_id, target_user_id
            )
            if cached is not None:
                instagram_api_usage_tracker.track_cache_hit(
                    app_user_id=app_user_id,
                    instagram_user_id=instagram_user_id,
                    category="user_data_fetch",
                    caller_service=caller_service,
                    caller_method=caller_method,
                )
                return cached

        result: dict[str, object] = instagram_api_usage_tracker.track_call(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_data_fetch",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_target_user_data(profile, target_user_id),
        )
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
    ) -> list[ii.FollowerUserRecord]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="followers_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_target_followers_v2(profile, target_user_id),
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
    ) -> list[ii.FollowerUserRecord]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="following_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_target_following_v2(profile, target_user_id),
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
    ) -> list[ii.FollowerUserRecord]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="followers_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_current_followers_v2(
                profile=profile,
                store_data=False,
            ),
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
    ) -> list[ii.FollowerUserRecord]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="following_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_current_following_v2(
                profile=profile, store_data=False
            ),
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
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="action_follow",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.follow_user_by_id(
                target_user_id, target_username, profile
            ),
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
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="action_unfollow",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.unfollow_user_by_id(
                target_user_id, target_username, profile
            ),
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
