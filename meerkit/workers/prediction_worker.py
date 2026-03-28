import threading
import traceback

from meerkit.config import MAX_PREDICTION_REFRESH_WORKERS
from meerkit.extensions import prediction_refresh_queue
from meerkit.services import db_service, prediction_runner
from meerkit.services.db_service import close_worker_db, init_worker_db

_worker_lock = threading.Lock()
_worker_threads: list[threading.Thread] = []


def start_prediction_worker() -> None:
    global _worker_threads

    with _worker_lock:
        _worker_threads = [thread for thread in _worker_threads if thread.is_alive()]
        if len(_worker_threads) >= MAX_PREDICTION_REFRESH_WORKERS:
            print(
                f"[Prediction worker] already running ({len(_worker_threads)}/{MAX_PREDICTION_REFRESH_WORKERS})."
            )
            return

    def _run() -> None:
        init_worker_db()
        while True:
            item = prediction_refresh_queue.get()
            if item is None:
                break

            task_id = item["task_id"]
            prediction_id = item["prediction_id"]
            try:
                current_task = prediction_runner.get_task_status(task_id)
                if current_task and current_task.get("status") == "cancelled":
                    continue

                prediction_runner.mark_task_running(task_id)
                prediction_runner.mark_task_progress(task_id, 0.4)

                from meerkit.services import account_handler

                account_handler.refresh_followback_prediction(
                    prediction_id=prediction_id,
                    instagram_user=item["instagram_user"],
                    relationship_type=item.get("relationship_type"),
                    fetch_relationships=item.get("fetch_relationships", True),
                )
                prediction_runner.mark_task_completed(task_id)
            except Exception as exc:
                traceback.print_exc()
                prediction_runner.mark_task_error(task_id, str(exc))
                db_service.update_prediction(prediction_id, status="error")
            finally:
                prediction_refresh_queue.task_done()

        print("[Prediction worker] received shutdown signal, exiting...")
        close_worker_db()

    workers_to_start = MAX_PREDICTION_REFRESH_WORKERS - len(_worker_threads)
    for _ in range(workers_to_start):
        worker_name = f"prediction-worker-{len(_worker_threads) + 1}"
        thread = threading.Thread(
            target=_run,
            daemon=True,
            name=worker_name,
        )
        thread.start()
        _worker_threads.append(thread)

    print(
        f"[Prediction worker] started {workers_to_start} worker(s). Total: {len(_worker_threads)}"
    )
