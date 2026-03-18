import threading
import time
import traceback

from backend.config import IMAGE_DOWNLOAD_DELAY_SECONDS
from backend.extensions import image_download_queue
from backend.services import downloader
from backend.services.db_service import (
    cache_image_path,
    close_worker_db,
    init_worker_db,
)

_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None


def start_download_worker() -> None:
    global _worker_thread

    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            print("[Download worker] already running.")
            return

    def _run():
        init_worker_db()
        while True:
            item = image_download_queue.get()
            # print(item)
            if item is None:  # poison pill to stop
                break
            try:
                _app_user_id, profile_pk_id, profile_pic_url = item
                img_path = downloader.process_img_download(
                    profile_pk_id, profile_pic_url
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

    _worker_thread = threading.Thread(target=_run, daemon=True, name="download-worker")
    _worker_thread.start()

    print("[Download worker] started.")
