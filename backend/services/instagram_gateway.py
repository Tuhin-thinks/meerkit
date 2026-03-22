from collections.abc import Callable
from typing import TypeVar

import insta_interface as ii
from backend.services.instagram_api_usage import instagram_api_usage_tracker

T = TypeVar("T")


class InstagramGateway:
    """Thin tracked wrapper around Instagram interface calls used by backend services."""

    def _tracked(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        category: str,
        caller_service: str,
        caller_method: str,
        execute: Callable[[], T],
    ) -> T:
        return instagram_api_usage_tracker.track_call(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category=category,
            caller_service=caller_service,
            caller_method=caller_method,
            execute=execute,
        )

    def resolve_target_user_pk(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        username: str,
        caller_service: str,
        caller_method: str,
    ) -> str | None:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_lookup",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.resolve_target_user_pk(username, profile),
        )

    def get_user_data(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        caller_service: str,
        caller_method: str,
    ) -> dict[str, object]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_data_fetch",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_user_data(profile=profile),
        )

    def get_target_user_data(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        target_user_id: str,
        caller_service: str,
        caller_method: str,
    ) -> dict[str, object]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_data_fetch",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_target_user_data(profile, target_user_id),
        )

    def get_target_followers_v2(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        target_user_id: str,
        caller_service: str,
        caller_method: str,
    ) -> list[ii.FollowerUserRecord]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="followers_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_target_followers_v2(profile, target_user_id),
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
    ) -> list[ii.FollowerUserRecord]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="following_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_target_following_v2(profile, target_user_id),
        )

    def get_current_followers_v2(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        caller_service: str,
        caller_method: str,
    ) -> list[ii.FollowerUserRecord]:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="followers_discovery",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.get_current_followers_v2(profile=profile, store_data=False),
        )

    def get_current_following_v2(
        self,
        *,
        app_user_id: str,
        instagram_user_id: str,
        profile: ii.InstagramProfile,
        caller_service: str,
        caller_method: str,
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
    ) -> str | None:
        return self._tracked(
            app_user_id=app_user_id,
            instagram_user_id=instagram_user_id,
            category="user_lookup",
            caller_service=caller_service,
            caller_method=caller_method,
            execute=lambda: ii.resolve_target_user_pk(username, profile),
        )


instagram_gateway = InstagramGateway()
