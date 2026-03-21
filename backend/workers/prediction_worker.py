import threading
import traceback

from backend.extensions import prediction_refresh_queue
from backend.services import db_service, prediction_runner
from backend.services.db_service import close_worker_db, init_worker_db

_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None


def start_prediction_worker() -> None:
    global _worker_thread

    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            print("[Prediction worker] already running.")
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

                from backend.services import account_handler

                account_handler.refresh_followback_prediction(
                    prediction_id=prediction_id,
                    instagram_user=item["instagram_user"],
                    relationship_type=item.get("relationship_type"),
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

    _worker_thread = threading.Thread(
        target=_run,
        daemon=True,
        name="prediction-worker",
    )
    _worker_thread.start()
    print("[Prediction worker] started.")
