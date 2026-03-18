import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from backend.config import USERS_DIR, profile_data_dir, user_dir
from insta_interface import InstagramProfile, get_user_data


def _read_json(path: Path, fallback: dict | list) -> dict | list:
    if not path.exists():
        return fallback
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def _hash_password(password: str) -> str:
    """Hash an app-user password for local credential verification."""
    return hashlib.sha256(password.encode()).hexdigest()


def _users_file() -> Path:
    return USERS_DIR / "app_users.json"


def _instagram_users_file(app_user_id: str) -> Path:
    return user_dir(app_user_id) / "instagram_users.json"


def _state_file(app_user_id: str) -> Path:
    return user_dir(app_user_id) / "state.json"


def _get_all_app_users() -> list[dict]:
    payload = _read_json(_users_file(), [])
    return payload if isinstance(payload, list) else []


def _set_all_app_users(users: list[dict]) -> None:
    _write_json(_users_file(), users)


def _find_app_user_by_name(name: str) -> dict | None:
    normalized = name.strip().lower()
    for user in _get_all_app_users():
        if user.get("name", "").strip().lower() == normalized:
            return user
    return None


def register_app_user(name: str, password: str) -> dict:
    """Create a new app user account identified by name/password."""
    normalized_name = name.strip()
    if not normalized_name or not password:
        raise ValueError("name and password are required")

    if _find_app_user_by_name(normalized_name):
        raise ValueError("App user already exists")

    app_user_id = (
        f"app_{hashlib.sha256(normalized_name.lower().encode()).hexdigest()[:16]}"
    )
    users = _get_all_app_users()
    users.append(
        {
            "app_user_id": app_user_id,
            "name": normalized_name,
            "password_hash": _hash_password(password),
            "created_at": datetime.now().isoformat(),
        }
    )
    _set_all_app_users(users)

    user_dir(app_user_id).mkdir(parents=True, exist_ok=True)
    _write_json(_instagram_users_file(app_user_id), [])
    _write_json(_state_file(app_user_id), {"active_instagram_user_id": None})

    return {"app_user_id": app_user_id, "name": normalized_name}


def login_app_user(name: str, password: str) -> dict | None:
    """Validate app-user credentials and return app user identity on success."""
    user = _find_app_user_by_name(name)
    if not user:
        return None
    if user.get("password_hash") != _hash_password(password):
        return None
    return {"app_user_id": user["app_user_id"], "name": user["name"]}


def get_instagram_users(app_user_id: str) -> list[dict]:
    """Return all instagram users owned by an app user."""
    payload = _read_json(_instagram_users_file(app_user_id), [])
    return payload if isinstance(payload, list) else []


def _safe_fetch_instagram_username(
    csrf_token: str, session_id: str, user_id: str
) -> str | None:
    """Fetch username from Instagram for friendlier first-time profile naming."""
    try:
        profile = InstagramProfile(
            csrf_token=csrf_token,
            session_id=session_id,
            user_id=user_id,
        )
        user_data = get_user_data(profile=profile)
    except Exception:
        return None

    username = user_data.get("username")
    if isinstance(username, str):
        normalized = username.strip()
        return normalized or None
    return None


def _parse_cookie_string(cookie_string: str) -> dict[str, str]:
    """Parse a pasted cookie header string into key/value pairs."""
    raw = cookie_string.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()

    cookies: dict[str, str] = {}
    for chunk in raw.split(";"):
        piece = chunk.strip()
        if not piece or "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            continue
        cookies[normalized_key] = value.strip()
    return cookies


def add_instagram_user(
    app_user_id: str,
    name: str,
    csrf_token: str,
    session_id: str,
    user_id: str,
) -> dict:
    """Create an instagram user record with mandatory credentials."""
    if not csrf_token or not session_id or not user_id:
        raise ValueError("csrf_token, session_id and user_id are required")

    instagram_users = get_instagram_users(app_user_id)
    fetched_username = _safe_fetch_instagram_username(
        csrf_token=csrf_token,
        session_id=session_id,
        user_id=user_id,
    )
    now_iso = datetime.now().isoformat()
    instagram_user_id = user_id
    instagram_user = {
        "instagram_user_id": instagram_user_id,
        "name": name.strip() or fetched_username or f"Instagram {user_id}",
        "username": fetched_username,
        "csrf_token": csrf_token,
        "session_id": session_id,
        "user_id": user_id,
        "csrf_token_added_at": now_iso,
        "session_id_added_at": now_iso,
        "created_at": now_iso,
    }
    instagram_users.append(instagram_user)
    _write_json(_instagram_users_file(app_user_id), instagram_users)

    profile_data_dir(app_user_id, instagram_user_id).mkdir(parents=True, exist_ok=True)

    state = _read_json(_state_file(app_user_id), {"active_instagram_user_id": None})
    if isinstance(state, dict) and not state.get("active_instagram_user_id"):
        state["active_instagram_user_id"] = instagram_user_id
        _write_json(_state_file(app_user_id), state)

    return instagram_user


def update_instagram_user(
    app_user_id: str,
    instagram_user_id: str,
    display_name: str | None = None,
    cookie_string: str | None = None,
) -> dict | None:
    """Update instagram user display name and/or credentials from a cookie string."""
    instagram_users = get_instagram_users(app_user_id)
    target_index = next(
        (
            idx
            for idx, user in enumerate(instagram_users)
            if user.get("instagram_user_id") == instagram_user_id
        ),
        None,
    )
    if target_index is None:
        return None

    target_user = dict(instagram_users[target_index])
    now_iso = datetime.now().isoformat()
    touched_credentials = False

    if display_name is not None:
        normalized_display_name = display_name.strip()
        if not normalized_display_name:
            raise ValueError("display_name cannot be empty")
        target_user["name"] = normalized_display_name

    if cookie_string is not None:
        parsed = _parse_cookie_string(cookie_string)
        parsed_session_id = (parsed.get("sessionid") or "").strip()
        parsed_user_id = (
            parsed.get("ds_user_id")
            or parsed.get("user_id")
            or parsed.get("userid")
            or ""
        ).strip()
        parsed_csrf = (parsed.get("csrftoken") or "").strip()

        if not parsed_session_id or not parsed_user_id:
            raise ValueError("cookie string must include sessionid and ds_user_id")

        target_user["session_id"] = parsed_session_id
        target_user["user_id"] = parsed_user_id
        target_user["session_id_added_at"] = now_iso
        touched_credentials = True

        if parsed_csrf:
            target_user["csrf_token"] = parsed_csrf
            target_user["csrf_token_added_at"] = now_iso

        refreshed_username = _safe_fetch_instagram_username(
            csrf_token=target_user.get("csrf_token", ""),
            session_id=target_user["session_id"],
            user_id=target_user["user_id"],
        )
        if not refreshed_username:
            raise ValueError(
                "cookie refresh failed; verify cookie values (sessionid, ds_user_id, csrftoken)"
            )

        target_user["username"] = refreshed_username
        if display_name is None:
            target_user["name"] = refreshed_username

    if not touched_credentials and display_name is None:
        raise ValueError("nothing to update")

    instagram_users[target_index] = target_user
    _write_json(_instagram_users_file(app_user_id), instagram_users)
    return target_user


def get_instagram_user(app_user_id: str, instagram_user_id: str) -> dict | None:
    """Return one instagram user by id for the given app user."""
    instagram_users = get_instagram_users(app_user_id)
    return next(
        (u for u in instagram_users if u["instagram_user_id"] == instagram_user_id),
        None,
    )


def get_active_instagram_user_id(app_user_id: str) -> str | None:
    """Return active instagram user id for this app user."""
    state = _read_json(_state_file(app_user_id), {})
    if not isinstance(state, dict):
        return None
    return state.get("active_instagram_user_id")


def set_active_instagram_user(app_user_id: str, instagram_user_id: str) -> bool:
    """Set active instagram user if it belongs to the app user."""
    if not get_instagram_user(app_user_id, instagram_user_id):
        return False
    _write_json(
        _state_file(app_user_id), {"active_instagram_user_id": instagram_user_id}
    )
    return True


def delete_instagram_user(app_user_id: str, instagram_user_id: str) -> bool:
    """Delete one instagram user and its scoped persisted scan/cache data."""
    instagram_users = get_instagram_users(app_user_id)
    kept = [u for u in instagram_users if u["instagram_user_id"] != instagram_user_id]
    if len(kept) == len(instagram_users):
        return False

    _write_json(_instagram_users_file(app_user_id), kept)

    profile_path = user_dir(app_user_id) / "profiles" / instagram_user_id
    if profile_path.exists():
        shutil.rmtree(profile_path)

    active_id = get_active_instagram_user_id(app_user_id)
    if active_id == instagram_user_id:
        _write_json(
            _state_file(app_user_id),
            {
                "active_instagram_user_id": kept[0]["instagram_user_id"]
                if kept
                else None
            },
        )

    return True


def delete_all_instagram_users(app_user_id: str) -> None:
    """Delete all instagram users and all profile-scoped data for an app user."""
    _write_json(_instagram_users_file(app_user_id), [])
    _write_json(_state_file(app_user_id), {"active_instagram_user_id": None})

    profiles_root = user_dir(app_user_id) / "profiles"
    if profiles_root.exists():
        shutil.rmtree(profiles_root)


def build_me_payload(app_user_id: str, name: str) -> dict:
    """Build the auth payload consumed by frontend session bootstrap."""
    instagram_users = get_instagram_users(app_user_id)
    active_id = get_active_instagram_user_id(app_user_id)
    active_user = get_instagram_user(app_user_id, active_id) if active_id else None
    return {
        "app_user_id": app_user_id,
        "name": name,
        "instagram_users": instagram_users,
        "active_instagram_user": active_user,
    }


def get_app_user_by_id(app_user_id: str) -> dict | None:
    """Return app user record by app user id."""
    for user in _get_all_app_users():
        if user.get("app_user_id") == app_user_id:
            return user
    return None


def clear_user_session_payload(app_user_id: str) -> None:
    """Reserved for future cleanup hooks on logout."""
    _ = app_user_id


USERS_DIR.mkdir(parents=True, exist_ok=True)
