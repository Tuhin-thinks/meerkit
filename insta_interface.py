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

# NOTE: not used in this project.
# already_unfollowed_users = load_unfollowed_users()


def unfollow_user(
    username: str,
    profile: InstagramProfile,
    retry_count: int = 3,
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
    retry_count: int = 3,
) -> int:
    """Follow an Instagram user by profile link using GraphQL mutation."""
    if retry_count < 3:
        print(
            "Retrying follow for "
            f"{instagram_profile_link}, attempts left: {retry_count}"
        )

    # user_id = _resolve_user_pk(username, profile)
    username = _extract_username_from_profile_link(instagram_profile_link)
    user_id = profile.user_id

    if not isinstance(user_id, str) or not user_id:
        print(
            "User ID for "
            f"{instagram_profile_link} not found or invalid. Cannot proceed with following."
        )
        return -1

    print(f"Following user: {username} ({user_id})")

    variables = {
        "target_user_id": user_id,
        "container_module": "profile",
        "nav_chain": "PolarisProfilePostsTabRoot:profilePage:1:via_cold_start",
    }

    follow_headers = {
        **_headers(profile),
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.instagram.com",
        "referer": f"https://www.instagram.com/{username}/",
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
        f"{instagram_profile_link}. Status code: {response.status_code}"
    )
    return -1


def get_user_data(
    profile: InstagramProfile,
    unfollow_signal_followers_threshold: int = 10000,
) -> dict[str, str | int | bool]:
    # user_id_query_url = (
    #     f"https://www.instagram.com/web/search/topsearch/?query={username}"
    # )
    # resp = requests.get(
    #     user_id_query_url,
    #     headers=_headers(profile),
    #     cookies=_cookies(profile),
    # )
    # if not resp.ok:
    #     # write response error to a file
    #     with open(
    #         profile_query_data_path / f"user_id_query_error_{username}.html", "w"
    #     ) as f:
    #         f.write(resp.text)
    #     print("Fetching user pk:", resp.status_code)
    # resp.raise_for_status()
    # print(resp.json())
    # try:
    #     user_id = resp.json()["users"][0]["user"]["pk"]
    # except IndexError:
    #     return {"error": "User not found"}

    print(f"{profile.user_id=}")

    variables = {
        "enable_integrity_filters": True,
        "id": profile.user_id,
        "render_surface": "PROFILE",
        "__relay_internal__pv__PolarisProjectCannesEnabledrelayprovider": True,
        "__relay_internal__pv__PolarisProjectCannesLoggedInEnabledrelayprovider": True,
        "__relay_internal__pv__PolarisCannesGuardianExperienceEnabledrelayprovider": False,
        "__relay_internal__pv__PolarisCASB976ProfileEnabledrelayprovider": False,
    }

    data = {
        "variables": json.dumps(variables),
        "doc_id": "31574646175516262",  # which graphql query to use
    }

    response = requests.post(
        url,
        headers=_headers(profile),
        cookies=_cookies(profile),
        data=data,
    )
    if not response.ok:
        # write response error to a file
        with open(
            profile_query_data_path / f"profile_query_error_{profile.user_id}.html", "w"
        ) as f:
            f.write(response.text)
        print("Fetching user profile data:", response.status_code)
    response.raise_for_status()

    profile_query_data = response.json()["data"]
    pprint.pprint(profile_query_data)
    friendship_status = profile_query_data["user"]["friendship_status"] or {}
    # extract important fields
    me_following_account = friendship_status.get("following", False)
    being_followed_by_account = friendship_status.get("followed_by", False)
    account_followers_count = profile_query_data["user"]["follower_count"]
    username = profile_query_data["user"]["username"]

    # save json a file
    with open(profile_query_data_path / f"profile_query_{username}.json", "w") as f:
        json.dump(response.json(), f, indent=4)

    result = {
        "username": username,
        "me_following_account": me_following_account,
        "being_followed_by_account": being_followed_by_account,
        "account_followers_count": account_followers_count,
    }

    # unfollow signal
    if me_following_account and not being_followed_by_account:
        if account_followers_count < unfollow_signal_followers_threshold:
            print(f"Unfollow signal for {username=}")
            result["unfollow_signal"] = True
        else:
            result["unfollow_signal"] = False
    else:
        result["unfollow_signal"] = False

    return result


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

def get_current_followers_v2(
    profile: InstagramProfile,
    store_data: bool = True,
    _store_fn: Callable[[list[FollowerUserRecord]], None] | None = None,
):
    """V2 of get_current_followers with different approach"""
    _max_fetch_count = 24
    follower_user_data_list: list[FollowerUserRecord] = []

    with requests.Session() as session:
        query_hash = "c76146de99bb02f6415203be841dd25a"
        session.headers.update(_headers(profile))
        session.cookies.update(_cookies(profile))

        _after = None

        has_next = True

        while has_next:
            variables = {
                "id": profile.user_id,
                "include_reel": False,
                "fetch_mutual": False,
                "first": 50,
                "after": _after,
            }
            _url = f"{url}?query_hash={query_hash}&variables={quote(json.dumps(variables))}"
            response = session.get(_url)
            if not response.ok:
                print(
                    f"Error fetching followers: {response.status_code} - {response.text}"
                )
                break

            data = response.json()
            edge = data["data"]["user"]["edge_followed_by"]

            for item in edge["edges"]:
                node = item["node"]
                follower_record = FollowerUserRecord(
                    pk_id=node.get("id", ""),
                    id=node.get("id", ""),
                    fbid_v2=node.get("fbid_v2", None),
                    profile_pic_id=node.get("profile_pic_id", None),
                    profile_pic_url=node.get("profile_pic_url", None),
                    username=node.get("username", None),
                    full_name=node.get("full_name", None),
                    is_private=node.get("is_private", False),
                )
                follower_user_data_list.append(follower_record)

            _after = edge.get("page_info", {}).get("end_cursor")
            has_next = edge.get("page_info", {}).get("has_next_page", False)
            print(f"Fetched batch of followers, count: {len(edge['edges'])}")

    if store_data and _store_fn:
        _store_fn(follower_user_data_list)
    print(f"Total followers fetched: {len(follower_user_data_list)}")
    return follower_user_data_list

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
    _max_fetch_count = 24
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
            time.sleep(0.3)

    if store_data and _store_fn:
        _store_fn(follower_user_data_list)
    print(f"Total followers fetched: {len(follower_user_data_list)}")
    return follower_user_data_list


if __name__ == "__main__":
    raise RuntimeError(
        "Instantiate InstagramProfile and call functions with explicit credentials."
    )
