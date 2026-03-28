import threading
import traceback
from typing import Any, cast

from meerkit.config import MAX_IMAGE_DOWNLOAD_WORKERS
from meerkit.extensions import image_download_queue
from meerkit.services import downloader
from meerkit.services.db_service import (
    cache_image_path,
    close_worker_db,
    init_worker_db,
)

_worker_lock = threading.Lock()
_worker_threads: list[threading.Thread] = []


def start_download_worker() -> None:
    global _worker_threads

    with _worker_lock:
        _worker_threads = [thread for thread in _worker_threads if thread.is_alive()]
        if len(_worker_threads) >= MAX_IMAGE_DOWNLOAD_WORKERS:
            print(
                f"[Download worker] already running ({len(_worker_threads)}/{MAX_IMAGE_DOWNLOAD_WORKERS})."
            )
            return

    def _run():
        init_worker_db()
        while True:
            item = image_download_queue.get()
            # print(item)
            if item is None:  # poison pill to stop
                break
            try:
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
                img_path = downloader.process_img_download(
                    app_user_id,
                    instagram_user_id,
                    profile_pk_id,
                    profile_pic_url,
                )
                if img_path:
                    cache_image_path([(profile_pk_id, profile_pic_url, img_path)])

            except Exception as _:
                traceback.print_exc()
            finally:
                image_download_queue.task_done()
            # delay to not overwhelm Instagram with too many requests in a short time, especially since some scans may have many followers
            # time.sleep(IMAGE_DOWNLOAD_DELAY_SECONDS())
        print("[Download worker] received shutdown signal, exiting...")
        close_worker_db()

    workers_to_start = MAX_IMAGE_DOWNLOAD_WORKERS - len(_worker_threads)
    for _ in range(workers_to_start):
        worker_name = f"download-worker-{len(_worker_threads) + 1}"
        thread = threading.Thread(target=_run, daemon=True, name=worker_name)
        thread.start()
        _worker_threads.append(thread)

    print(
        f"[Download worker] started {workers_to_start} worker(s). Total: {len(_worker_threads)}"
    )
