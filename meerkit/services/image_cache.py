from pathlib import Path

from meerkit.services.db_service import retrieve_img_path_by_pk_id


class ImageCacheReader:
    """Storage and retrieval handler for image cache based on primary key of account."""

    @staticmethod
    def retrieve(pk_id: str) -> Path | None:
        local_path = retrieve_img_path_by_pk_id(pk_id)
        return Path(local_path) if local_path else None


def get_cached_image_path(pk_id: str) -> Path | None:
    """Return the cached image Path if it exists on disk, else None."""
    return ImageCacheReader.retrieve(pk_id)
