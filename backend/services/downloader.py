import requests

from backend.config import IMAGE_CACHE_DIR
from backend.extensions import image_download_queue


def process_img_download(profile_pk_id: str, profile_pic_url: str) -> str | None:
    """Downloads the profile image for a given pk_id and profile_pic_url, and caches it on disk."""
    img_path = IMAGE_CACHE_DIR / f"{profile_pk_id}.jpeg"
    if img_path.exists():
        return str(img_path)

    response = requests.get(profile_pic_url, timeout=10)
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
    app_user_id: str, profile_pk_id: str, profile_pic_url: str
) -> None:
    """Enqueue an image download task for the given profile_pk_id and profile_pic_url."""
    image_download_queue.put((app_user_id, profile_pk_id, profile_pic_url))
