import csv
import json
import pprint
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
import tqdm

from meerkit.config import (
    INSTA_ACTION_RETRY_COUNT,
    INSTA_FOLLOWERS_FETCH_PAGE_SIZE,
    INSTA_FOLLOWERS_LOOP_DELAY_SECONDS,
)

url = "https://www.instagram.com/graphql/query"
_topsearch_url = "https://www.instagram.com/web/search/topsearch/"
_follow_doc_id = "9740159112729312"
_follow_lsd = "vfndR6YI1o9Mb1SorLFoGO"


@dataclass(frozen=True)
class InstagramProfile:
    """Holds the credential context for one Instagram account/session."""

    csrf_token: str
    session_id: str
    user_id: str


def _headers(profile: InstagramProfile) -> dict[str, str]:
    """Build request headers for a profile-scoped Instagram request."""
    return {
        # "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "x-csrftoken": profile.csrf_token,
        "x-ig-app-id": "936619743392459",
    }


def _profile_query_headers(profile: InstagramProfile) -> dict[str, str]:
    """Build the smaller header set needed by the profile page GraphQL POST."""
    return _headers(profile) | {
        "content-type": "application/x-www-form-urlencoded",
        "x-fb-friendly-name": "PolarisProfilePageContentQuery",
    }


def _cookies(profile: InstagramProfile) -> dict[str, str]:
    """Build request cookies for a profile-scoped Instagram request."""
    return {
        "csrftoken": profile.csrf_token,
        "sessionid": profile.session_id,
    }


profile_query_data_path = Path("profile_query")
profile_query_data_path.mkdir(exist_ok=True)


def load_non_followers_csv():
    if not Path("all_non_followers.csv").exists():
        return set()
    with open("all_non_followers.csv", "r") as f:
        reader = csv.DictReader(f)
        return {row["username"] for row in reader if row["unfollow_signal"] == "True"}


def append_unfollowed_user(user_id: str, user_name: str, user_profile_url: str):
    with open(profile_query_data_path / "unfollowed_users.csv", "a", newline="") as f:
        if f.tell() == 0:
            writer = csv.writer(f)
            writer.writerow(["user_id", "username", "user_profile_url"])
        writer = csv.writer(f)
        writer.writerow([user_id, user_name, user_profile_url])


def load_unfollowed_users():
    if not (profile_query_data_path / "unfollowed_users.csv").exists():
        return set()
    with open(profile_query_data_path / "unfollowed_users.csv", "r") as f:
        reader = csv.DictReader(f)
        return {row["username"] for row in reader}


def load_user_pk_from_saved_data(username: str):
    search_path = profile_query_data_path / f"profile_query_{username}.json"
    if not search_path.exists():
        return None
    with open(search_path, "r") as f:
        data = json.load(f)
        try:
            return data["data"]["user"]["pk"]
        except (KeyError, IndexError):
            return None


def _extract_username_from_profile_link(instagram_profile_link: str) -> str:
    """Extract username from Instagram profile links like https://www.instagram.com/username/."""
    parsed = urlparse(instagram_profile_link.strip())
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        raise ValueError(
            f"Could not extract username from profile link: {instagram_profile_link}"
        )

    username = path_parts[0].strip()
    if not username:
        raise ValueError(
            f"Could not extract username from profile link: {instagram_profile_link}"
        )
    return username


def _resolve_user_pk(username: str, profile: InstagramProfile) -> str | None:
    """Resolve Instagram user pk either from saved profile data or topsearch endpoint."""
    user_pk = load_user_pk_from_saved_data(username)
    if isinstance(user_pk, str) and user_pk:
        return user_pk

    params = {"query": username}
    response = requests.get(
        _topsearch_url,
        headers=_headers(profile),
        cookies=_cookies(profile),
        params=params,
    )
    if not response.ok:
        return None

    try:
        users = response.json().get("users", [])
        if not users:
            return None
        candidate = users[0].get("user", {}).get("pk")
        return str(candidate) if candidate is not None else None
    except (KeyError, ValueError, TypeError):
        return None


def resolve_target_user_pk(username: str, profile: InstagramProfile) -> str | None:
    """Public wrapper for resolving a target username to a pk id."""
    normalized = username.strip()
    if not normalized:
        return None
    return _resolve_user_pk(normalized, profile)


# NOTE: not used in this project.
# already_unfollowed_users = load_unfollowed_users()


def unfollow_user(
    username: str,
    profile: InstagramProfile,
    retry_count: int = INSTA_ACTION_RETRY_COUNT,
):
    if retry_count < 3:
        print(f"Retrying unfollow for {username}, attempts left: {retry_count}")

    user_id = load_user_pk_from_saved_data(username)

    assert isinstance(user_id, str), (
        f"User ID for {username} not found or invalid. Cannot proceed with unfollowing."
    )

    print(f"{user_id=}")

    variables = {
        "target_user_id": user_id,
        "container_module": "profile",
        "nav_chain": "PolarisProfilePostsTabRoot:profilePage:1:via_cold_start",
    }

    data = {
        "variables": json.dumps(variables),
        "doc_id": "9846833695423773",
    }

    response = requests.post(
        url,
        headers=_headers(profile),
        cookies=_cookies(profile),
        data=data,
    )
    print(response.status_code)
    print(response.json())

    if response.status_code == 200:
        # NOTE: Append to file for safe-keeping is not used in this project.
        # append_unfollowed_user(
        #     user_id, username, f"https://www.instagram.com/{username}/"
        # )
        return 1
    else:
        print(f"Failed to unfollow {username}. Status code: {response.status_code}")
        return -1


def follow_user(
    instagram_profile_link: str,
    profile: InstagramProfile,
    retry_count: int = INSTA_ACTION_RETRY_COUNT,
) -> int:
    """Follow an Instagram user by profile link using GraphQL mutation."""
    if retry_count < 3:
        print(
            "Retrying follow for "
            f"{instagram_profile_link}, attempts left: {retry_count}"
        )

    username = _extract_username_from_profile_link(instagram_profile_link)
    # Resolve the *target* user's pk — not the logged-in account's own id.
    user_id = resolve_target_user_pk(username, profile)

    if not isinstance(user_id, str) or not user_id:
        print(
            "User ID for "
            f"{instagram_profile_link} not found or invalid. Cannot proceed with following."
        )
        return -1

    return follow_user_by_id(user_id, username, profile)


def follow_user_by_id(
    target_user_id: str,
    target_username: str,
    profile: InstagramProfile,
) -> int:
    """Follow an Instagram user by their numeric user ID using GraphQL mutation."""
    print(f"Following user: {target_username} ({target_user_id})")

    variables = {
        "target_user_id": target_user_id,
        "container_module": "profile",
        "nav_chain": "PolarisProfilePostsTabRoot:profilePage:1:via_cold_start",
    }

    follow_headers = {
        **_headers(profile),
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.instagram.com",
        "referer": f"https://www.instagram.com/{target_username}/",
        "x-fb-friendly-name": "usePolarisFollowMutation",
        "x-fb-lsd": _follow_lsd,
        "x-root-field-name": "xdt_create_friendship",
    }

    payload = {
        "fb_api_req_friendly_name": "usePolarisFollowMutation",
        "server_timestamps": "true",
        "lsd": _follow_lsd,
        "variables": json.dumps(variables),
        "doc_id": _follow_doc_id,
    }

    response = requests.post(
        url,
        headers=follow_headers,
        cookies=_cookies(profile),
        data=payload,
    )

    print(response.status_code)
    try:
        print(response.json())
    except ValueError:
        print(response.text)

    if response.status_code == 200:
        return 1

    print(
        "Failed to follow "
        f"{target_username} ({target_user_id}). Status code: {response.status_code}"
    )
    return -1


def unfollow_user_by_id(
    target_user_id: str,
    target_username: str,
    profile: InstagramProfile,
) -> int:
    """Unfollow an Instagram user by their numeric user ID using GraphQL mutation."""
    print(f"Unfollowing user: {target_username} ({target_user_id})")

    variables = {
        "target_user_id": target_user_id,
        "container_module": "profile",
        "nav_chain": "PolarisProfilePostsTabRoot:profilePage:1:via_cold_start",
    }

    data = {
        "variables": json.dumps(variables),
        "doc_id": "9846833695423773",
    }

    response = requests.post(
        url,
        headers=_headers(profile),
        cookies=_cookies(profile),
        data=data,
    )
    print(response.status_code)
    try:
        print(response.json())
    except ValueError:
        print(response.text)

    if response.status_code == 200:
        return 1

    print(
        f"Failed to unfollow {target_username} ({target_user_id}). Status code: {response.status_code}"
    )
    return -1


def _fetch_profile_query_data(
    profile: InstagramProfile,
    target_user_id: str | None = None,
) -> dict:
    target_user_id = target_user_id or profile.user_id

    print(f"Fetching profile data for {target_user_id=}")

    variables = {
        "enable_integrity_filters": True,
        "id": target_user_id,
        "render_surface": "PROFILE",
        "__relay_internal__pv__PolarisCannesGuardianExperienceEnabledrelayprovider": False,
        "__relay_internal__pv__PolarisCASB976ProfileEnabledrelayprovider": False,
        "__relay_internal__pv__PolarisWebSchoolsEnabledrelayprovider": True,
        "__relay_internal__pv__PolarisRepostsConsumptionEnabledrelayprovider": True,
    }

    data = {
        "variables": json.dumps(variables),
        "doc_id": "34272012165747896",
    }

    response = requests.post(
        url,
        headers=_profile_query_headers(profile),
        cookies=_cookies(profile),
        data=data,
    )
    if not response.ok:
        with open(
            profile_query_data_path / f"profile_query_error_{target_user_id}.html", "w"
        ) as f:
            f.write(response.text)
        print("Fetching user profile data:", response.status_code)
    response.raise_for_status()

    return response.json()


def _extract_user_summary(
    response_payload: dict,
    unfollow_signal_followers_threshold: int = 10000,
) -> dict[str, object]:
    profile_query_data = response_payload["data"]
    user_data = profile_query_data["user"]
    friendship_status = user_data.get("friendship_status") or {}
    me_following_account = friendship_status.get("following", False)
    being_followed_by_account = friendship_status.get("followed_by", False)
    account_followers_count = user_data.get("follower_count")
    mutual_followers_count = user_data.get("mutual_followers_count")
    media_count = user_data.get("media_count")
    username = user_data.get("username")
    category = user_data.get("category_name") or user_data.get("category")
    biography = user_data.get("biography")
    account_type = user_data.get("account_type")
    if account_type is not None:
        account_type = str(account_type)

    bio_links = user_data.get("bio_links")
    bio_links_count = len(bio_links) if isinstance(bio_links, list) else 0

    has_highlight_reels = bool(user_data.get("has_highlight_reels"))
    is_professional_account = bool(
        user_data.get("is_professional_account") or user_data.get("is_business_account")
    )

    if username:
        with open(profile_query_data_path / f"profile_query_{username}.json", "w") as f:
            json.dump(response_payload, f, indent=4)

    result = {
        "username": username,
        "full_name": user_data.get("full_name"),
        "me_following_account": me_following_account,
        "being_followed_by_account": being_followed_by_account,
        "account_followers_count": account_followers_count,
        "account_following_count": user_data.get("following_count"),
        "mutual_followers_count": mutual_followers_count,
        "media_count": media_count,
        "is_private": bool(user_data.get("is_private", False)),
        "is_verified": bool(user_data.get("is_verified", False)),
        "is_professional_account": is_professional_account,
        "has_highlight_reels": has_highlight_reels,
        "profile_pic_id": user_data.get("profile_pic_id"),
        "profile_pic_url": user_data.get("profile_pic_url"),
        "user_id": str(user_data.get("id") or user_data.get("pk") or ""),
        "category": category,
        "biography": biography,
        "account_type": account_type,
        "bio_links_count": bio_links_count,
    }

    if me_following_account and not being_followed_by_account:
        result["unfollow_signal"] = bool(
            isinstance(account_followers_count, int)
            and account_followers_count < unfollow_signal_followers_threshold
        )
    else:
        result["unfollow_signal"] = False

    return result


def get_user_data(
    profile: InstagramProfile,
    unfollow_signal_followers_threshold: int = 10000,
) -> dict[str, object]:
    response_payload = _fetch_profile_query_data(profile=profile)
    return _extract_user_summary(
        response_payload=response_payload,
        unfollow_signal_followers_threshold=unfollow_signal_followers_threshold,
    )


def get_target_user_data(
    profile: InstagramProfile,
    target_user_id: str,
    unfollow_signal_followers_threshold: int = 10000,
) -> dict[str, object]:
    """Fetch target profile metadata using the authenticated account session."""
    response_payload = _fetch_profile_query_data(
        profile=profile,
        target_user_id=target_user_id,
    )
    return _extract_user_summary(
        response_payload=response_payload,
        unfollow_signal_followers_threshold=unfollow_signal_followers_threshold,
    )


@dataclass
class FollowerUserRecord:
    pk_id: str
    id: str
    profile_pic_url: str
    username: str
    full_name: str
    is_private: bool
    # optional fields
    fbid_v2: str | None
    profile_pic_id: str | None
    is_verified: bool | None = None

    @staticmethod
    def from_string(record_str: str) -> "FollowerUserRecord":
        record_data = json.loads(record_str)
        return FollowerUserRecord(**record_data)

    def __hash__(self) -> int:
        return hash(self.pk_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FollowerUserRecord):
            return NotImplemented
        return self.pk_id == other.pk_id

    def __str__(self) -> str:
        return json.dumps(self.__dict__)


def _get_relationship_records_v2(
    profile: InstagramProfile,
    target_user_id: str,
    edge_name: str,
    query_hash: str,
    fetch_at_max: int | None = None,
) -> list[FollowerUserRecord]:
    records: list[FollowerUserRecord] = []
    normalized_fetch_at_max: int | None = None
    if fetch_at_max is not None:
        normalized_fetch_at_max = max(1, int(fetch_at_max))

    with requests.Session() as session:
        session.headers.update(_headers(profile))
        session.cookies.update(_cookies(profile))

        _after = None
        has_next = True

        while has_next:
            if (
                normalized_fetch_at_max is not None
                and len(records) >= normalized_fetch_at_max
            ):
                break

            page_size = 50
            if normalized_fetch_at_max is not None:
                remaining = normalized_fetch_at_max - len(records)
                page_size = max(1, min(50, remaining))

            variables = {
                "id": target_user_id,
                "include_reel": False,
                "fetch_mutual": False,
                "first": page_size,
                "after": _after,
            }
            _url = f"{url}?query_hash={query_hash}&variables={quote(json.dumps(variables))}"
            response = session.get(_url)
            if not response.ok:
                print(
                    f"Error fetching {edge_name}: {response.status_code} - {response.text}"
                )
                break

            data = response.json()
            edge = data["data"]["user"][edge_name]

            for item in edge["edges"]:
                node = item["node"]
                records.append(
                    FollowerUserRecord(
                        pk_id=node.get("id", ""),
                        id=node.get("id", ""),
                        fbid_v2=node.get("fbid_v2", None),
                        profile_pic_id=node.get("profile_pic_id", None),
                        profile_pic_url=node.get("profile_pic_url", None),
                        username=node.get("username", None),
                        full_name=node.get("full_name", None),
                        is_private=node.get("is_private", False),
                        is_verified=node.get("is_verified", False),
                    )
                )

            _after = edge.get("page_info", {}).get("end_cursor")
            has_next = edge.get("page_info", {}).get("has_next_page", False)
            print(f"Fetched batch of {edge_name}, count: {len(edge['edges'])}")

            if (
                normalized_fetch_at_max is not None
                and len(records) >= normalized_fetch_at_max
            ):
                break

    return records


def get_current_followers_v2(
    profile: InstagramProfile,
    store_data: bool = True,
    _store_fn: Callable[[list[FollowerUserRecord]], None] | None = None,
    fetch_at_max: int | None = None,
):
    """V2 of get_current_followers with different approach"""
    follower_user_data_list = _get_relationship_records_v2(
        profile=profile,
        target_user_id=profile.user_id,
        edge_name="edge_followed_by",
        query_hash="c76146de99bb02f6415203be841dd25a",
        fetch_at_max=fetch_at_max,
    )

    if store_data and _store_fn:
        _store_fn(follower_user_data_list)
    print(f"Total followers fetched: {len(follower_user_data_list)}")
    return follower_user_data_list


def get_current_following_v2(
    profile: InstagramProfile,
    store_data: bool = True,
    _store_fn: Callable[[list[FollowerUserRecord]], None] | None = None,
    fetch_at_max: int | None = None,
):
    """V2 of get_current_following with different approach"""
    following_user_data_list = _get_relationship_records_v2(
        profile=profile,
        target_user_id=profile.user_id,
        edge_name="edge_follow",
        query_hash="d04b0a864b4b54837c0d870b0e77e076",
        fetch_at_max=fetch_at_max,
    )

    if store_data and _store_fn:
        _store_fn(following_user_data_list)
    print(f"Total following users fetched: {len(following_user_data_list)}")
    return following_user_data_list


def get_target_followers_v2(
    profile: InstagramProfile,
    target_user_id: str,
    store_data: bool = False,
    _store_fn: Callable[[list[FollowerUserRecord]], None] | None = None,
    fetch_at_max: int | None = None,
) -> list[FollowerUserRecord]:
    followers = _get_relationship_records_v2(
        profile=profile,
        target_user_id=target_user_id,
        edge_name="edge_followed_by",
        query_hash="c76146de99bb02f6415203be841dd25a",
        fetch_at_max=fetch_at_max,
    )
    if store_data and _store_fn:
        _store_fn(followers)
    return followers


def get_target_following_v2(
    profile: InstagramProfile,
    target_user_id: str,
    store_data: bool = False,
    _store_fn: Callable[[list[FollowerUserRecord]], None] | None = None,
    fetch_at_max: int | None = None,
) -> list[FollowerUserRecord]:
    following = _get_relationship_records_v2(
        profile=profile,
        target_user_id=target_user_id,
        edge_name="edge_follow",
        query_hash="d04b0a864b4b54837c0d870b0e77e076",
        fetch_at_max=fetch_at_max,
    )
    if store_data and _store_fn:
        _store_fn(following)
    return following


# NOTE: the above v2 approach is based on reverse engineering the Instagram web interface and faster than the v1 approach.
# Both approaches work. But, I am currently using the v2 approach for fetching followers.
def get_current_followers(
    profile: InstagramProfile,
    store_data: bool = True,
    _store_fn: Callable[[list[FollowerUserRecord]], None] | None = None,
) -> list[FollowerUserRecord]:
    """Get the set of current followers"""

    __user_data = get_user_data(profile)
    followers_count = __user_data["account_followers_count"]
    username = __user_data["username"]
    print(f"[i] Followers count for {username}: {followers_count}")
    assert isinstance(followers_count, int), "Invalid followers count in user data"
    _max_fetch_count = INSTA_FOLLOWERS_FETCH_PAGE_SIZE
    follower_user_data_list: list[FollowerUserRecord] = []

    with requests.Session() as session:
        session.headers.update(
            _headers(profile)
            | {"referer": f"https://www.instagram.com/{username}/followers/"}
        )
        session.cookies.update(_cookies(profile))

        _query_params: dict[str, int | str] = {
            "search_surface": "followers_list_page",
            "count": _max_fetch_count,
        }

        _iterations = (followers_count + _max_fetch_count - 1) // _max_fetch_count
        _progress = tqdm.tqdm(
            total=_iterations,
            desc="Fetching followers",
            unit="requests",
        )
        _max_id = None
        while followers_count > 0:
            url = f"https://www.instagram.com/api/v1/friendships/{profile.user_id}/followers"
            if _max_id:
                _query_params = _query_params | {"max_id": _max_id}
            try:
                response = session.get(url, params=_query_params)
                followers_count_data = response.json()
                if followers_count_data.get("status") == "fail":
                    print(f"Error in response: {followers_count_data.get('message')}")
                    break
            except (requests.RequestException, ValueError) as e:
                print(f"Error fetching followers: {e}")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                break

            _max_id = followers_count_data.get("next_max_id")
            pprint.pprint(followers_count_data)
            users_data = followers_count_data.get("users", [])
            print("[i] Fetched batch of followers, count:", len(users_data))

            for user_data in users_data:
                follower_record = FollowerUserRecord(
                    pk_id=user_data.get("pk", ""),
                    id=user_data.get("id", ""),
                    fbid_v2=user_data.get("fbid_v2", None),
                    profile_pic_id=user_data.get("profile_pic_id", None),
                    profile_pic_url=user_data.get("profile_pic_url", None),
                    username=user_data.get("username", None),
                    full_name=user_data.get("full_name", None),
                    is_private=user_data.get("is_private", False),
                )
                follower_user_data_list.append(follower_record)
            followers_count -= _max_fetch_count
            _progress.update(1)
            # delay
            time.sleep(INSTA_FOLLOWERS_LOOP_DELAY_SECONDS)

    if store_data and _store_fn:
        _store_fn(follower_user_data_list)
    print(f"Total followers fetched: {len(follower_user_data_list)}")
    return follower_user_data_list


if __name__ == "__main__":
    raise RuntimeError(
        "Instantiate InstagramProfile and call functions with explicit credentials."
    )
