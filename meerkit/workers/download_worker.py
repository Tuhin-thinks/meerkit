import logging
import threading
from time import perf_counter
from typing import Any, cast

from meerkit.config import MAX_IMAGE_DOWNLOAD_WORKERS
from meerkit.extensions import image_download_queue
from meerkit.logging_context import bind_context, clear_context
from meerkit.services import downloader
from meerkit.services.db_service import (
    cache_image_path,
    close_worker_db,
    init_worker_db,
)

_worker_lock = threading.Lock()
_worker_threads: list[threading.Thread] = []
logger = logging.getLogger(__name__)


def start_download_worker() -> None:
    global _worker_threads

    with _worker_lock:
        _worker_threads = [thread for thread in _worker_threads if thread.is_alive()]
        if len(_worker_threads) >= MAX_IMAGE_DOWNLOAD_WORKERS:
            logger.info(
                "download_worker_already_running",
                extra={
                    "event": "download_worker_already_running",
                    "metrics": {
                        "active_workers": len(_worker_threads),
                        "max_workers": MAX_IMAGE_DOWNLOAD_WORKERS,
                    },
                },
            )
            return

    def _run():
        init_worker_db()
        while True:
            item = image_download_queue.get()
            if item is None:  # poison pill to stop
                break
            try:
                started_at = perf_counter()
                payload = cast(tuple[Any, ...], item)
                if len(payload) == 4:
                    app_user_id, instagram_user_id, profile_pk_id, profile_pic_url = (
                        payload
                    )
                elif len(payload) == 3:
                    app_user_id, profile_pk_id, profile_pic_url = payload
                    instagram_user_id = "unknown"
                else:
                    raise ValueError(
                        f"Unexpected download payload size: {len(payload)}"
                    )
                bind_context(
                    worker_type="download",
                    app_user_id=str(app_user_id),
                    instagram_user_id=str(instagram_user_id),
                    profile_pk_id=str(profile_pk_id),
                )
                img_path = downloader.process_img_download(
                    app_user_id,
                    instagram_user_id,
                    profile_pk_id,
                    profile_pic_url,
                )
                if img_path:
                    cache_image_path([(profile_pk_id, profile_pic_url, img_path)])
                logger.info(
                    "download_worker_item_processed",
                    extra={
                        "event": "download_worker_item_processed",
                        "metrics": {
                            "duration_ms": int((perf_counter() - started_at) * 1000),
                            "cached": bool(img_path),
                        },
                    },
                )

            except Exception as _:
                logger.exception("Download worker failed processing image payload")
            finally:
                clear_context()
                image_download_queue.task_done()
            # delay to not overwhelm Instagram with too many requests in a short time, especially since some scans may have many followers
            # time.sleep(IMAGE_DOWNLOAD_DELAY_SECONDS())
        logger.info(
            "download_worker_shutdown",
            extra={"event": "download_worker_shutdown"},
        )
        close_worker_db()

    workers_to_start = MAX_IMAGE_DOWNLOAD_WORKERS - len(_worker_threads)
    for _ in range(workers_to_start):
        worker_name = f"download-worker-{len(_worker_threads) + 1}"
        thread = threading.Thread(target=_run, daemon=True, name=worker_name)
        thread.start()
        _worker_threads.append(thread)

    logger.info(
        "download_worker_started",
        extra={
            "event": "download_worker_started",
            "metrics": {
                "workers_started": workers_to_start,
                "active_workers": len(_worker_threads),
            },
        },
    )
