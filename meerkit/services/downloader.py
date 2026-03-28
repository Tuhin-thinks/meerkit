from typing import Any, cast

import requests

from meerkit.config import IMAGE_CACHE_DIR, IMAGE_DOWNLOAD_REQUEST_TIMEOUT
from meerkit.extensions import image_download_queue
from meerkit.services import db_service
from meerkit.services.instagram_api_usage import instagram_api_usage_tracker


def process_img_download(
    app_user_id: str,
    instagram_user_id: str,
    profile_pk_id: str,
    profile_pic_url: str,
) -> str | None:
    """Downloads the profile image for a given pk_id and profile_pic_url, and caches it on disk."""
    img_path = IMAGE_CACHE_DIR / f"{profile_pk_id}.jpeg"
    cached_url = db_service.get_latest_cached_image_url(profile_pk_id)
    if cached_url == profile_pic_url and img_path.exists():
        return str(img_path)

    response = instagram_api_usage_tracker.track_call(
        app_user_id=app_user_id,
        instagram_user_id=instagram_user_id,
        category="img_download",
        caller_service="downloader",
        caller_method="process_img_download",
        execute=lambda: requests.get(
            profile_pic_url, timeout=IMAGE_DOWNLOAD_REQUEST_TIMEOUT
        ),
    )
    response.raise_for_status()
    # store in cache directory with filename as pk_id.jpg
    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        raise ValueError(
            f"[Download worker] URL did not point to an image. Content-Type: {content_type};\n"
            "Failed download profile image for"
            f"\tImage URL: {profile_pic_url}\n"
            f"\tProfile PK ID: {profile_pk_id}\n"
        )
    with open(img_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return str(img_path)


def enqueue_image_download(
    app_user_id: str,
    instagram_user_id: str,
    profile_pk_id: str,
    profile_pic_url: str,
) -> None:
    """Enqueue an image download task for the given profile_pk_id and profile_pic_url."""
    cast(Any, image_download_queue).put(
        (app_user_id, instagram_user_id, profile_pk_id, profile_pic_url)
    )
