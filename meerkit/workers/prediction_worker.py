import logging
import threading
from time import perf_counter

from meerkit.config import MAX_PREDICTION_REFRESH_WORKERS
from meerkit.extensions import prediction_refresh_queue
from meerkit.logging_context import bind_context, clear_context
from meerkit.services import db_service, prediction_runner
from meerkit.services.db_service import close_worker_db, init_worker_db

_worker_lock = threading.Lock()
_worker_threads: list[threading.Thread] = []
logger = logging.getLogger(__name__)


def start_prediction_worker() -> None:
    global _worker_threads

    with _worker_lock:
        _worker_threads = [thread for thread in _worker_threads if thread.is_alive()]
        if len(_worker_threads) >= MAX_PREDICTION_REFRESH_WORKERS:
            logger.info(
                "prediction_worker_already_running",
                extra={
                    "event": "prediction_worker_already_running",
                    "metrics": {
                        "active_workers": len(_worker_threads),
                        "max_workers": MAX_PREDICTION_REFRESH_WORKERS,
                    },
                },
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
                started_at = perf_counter()
                bind_context(
                    worker_type="prediction",
                    task_id=str(task_id),
                    prediction_id=str(prediction_id),
                )
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
                logger.info(
                    "prediction_task_completed",
                    extra={
                        "event": "prediction_task_completed",
                        "metrics": {
                            "duration_ms": int((perf_counter() - started_at) * 1000),
                        },
                    },
                )
            except Exception as exc:
                logger.exception("Prediction worker failed task processing")
                prediction_runner.mark_task_error(task_id, str(exc))
                db_service.update_prediction(prediction_id, status="error")
            finally:
                clear_context()
                prediction_refresh_queue.task_done()

        logger.info(
            "prediction_worker_shutdown",
            extra={"event": "prediction_worker_shutdown"},
        )
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

    logger.info(
        "prediction_worker_started",
        extra={
            "event": "prediction_worker_started",
            "metrics": {
                "workers_started": workers_to_start,
                "active_workers": len(_worker_threads),
            },
        },
    )
