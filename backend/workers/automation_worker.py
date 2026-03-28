"""
Automation worker — daemon thread pool consuming automation_action_queue.

Modeled after prediction_worker but backed by durable automation_actions /
automation_action_items DB state instead of transient queue-only payloads.
"""

import threading
import traceback

from backend.config import MAX_AUTOMATION_WORKERS
from backend.extensions import automation_action_queue
from backend.services import automation_runner, db_service
from backend.services.automation_service import (
    execute_follow_item,
    execute_left_right_compare_item,
    execute_unfollow_item,
    inter_action_delay,
)
from backend.services.db_service import close_worker_db, init_worker_db

_worker_lock = threading.Lock()
_worker_threads: list[threading.Thread] = []


def recover_queued_actions(app_user_id: str) -> int:
    """Re-enqueue actions that were queued/running when the process last stopped.

    This makes automation jobs survive process restart.
    Returns the count of actions re-enqueued.
    """
    recoverable = db_service.list_recoverable_automation_actions(app_user_id)
    count = 0
    for action in recoverable:
        action_id = action["action_id"]
        # Reset running → queued so the worker picks it up cleanly.
        if action.get("status") == "running":
            db_service.update_automation_action(action_id, status="queued")
        automation_action_queue.put(
            {
                "action_id": action_id,
                "app_user_id": action["app_user_id"],
                "action_type": action["action_type"],
                # instagram_user is not persisted; worker will skip execution if missing.
                "instagram_user": None,
                "is_recovery": True,
            }
        )
        count += 1
    if count:
        print(f"[Automation worker] recovered {count} action(s) for user {app_user_id}")
    return count


def start_automation_worker() -> None:
    global _worker_threads

    with _worker_lock:
        _worker_threads = [t for t in _worker_threads if t.is_alive()]
        if len(_worker_threads) >= MAX_AUTOMATION_WORKERS:
            print(
                f"[Automation worker] already running ({len(_worker_threads)}/{MAX_AUTOMATION_WORKERS})."
            )
            return

    def _run() -> None:
        init_worker_db()
        while True:
            item = automation_action_queue.get()
            if item is None:
                break

            action_id = item["action_id"]
            app_user_id = item["app_user_id"]
            action_type = item["action_type"]
            instagram_user = item.get("instagram_user")
            is_recovery = item.get("is_recovery", False)

            try:
                current = automation_runner.get_action_status(action_id)
                if not current:
                    print(f"[Automation worker] action {action_id} not found, skipping")
                    continue
                if current.get("status") == "cancelled":
                    print(
                        f"[Automation worker] action {action_id} is cancelled, skipping"
                    )
                    continue

                # Recovery runs without stored credentials — mark as error, not dead.
                if is_recovery and not instagram_user:
                    automation_runner.mark_action_error(
                        action_id,
                        "Action was queued before process restart and requires re-confirmation to run.",
                    )
                    continue

                if not isinstance(instagram_user, dict):
                    automation_runner.mark_action_error(
                        action_id,
                        "Action is missing execution credentials. Please re-confirm and run again.",
                    )
                    continue

                automation_runner.mark_action_running(action_id)
                _execute_action(
                    action_id=action_id,
                    action_type=action_type,
                    app_user_id=app_user_id,
                    instagram_user=instagram_user,
                )

            except Exception as exc:
                traceback.print_exc()
                automation_runner.mark_action_error(action_id, str(exc))
            finally:
                automation_action_queue.task_done()

        print("[Automation worker] received shutdown signal, exiting...")
        close_worker_db()

    workers_to_start = MAX_AUTOMATION_WORKERS - len(_worker_threads)
    for _ in range(workers_to_start):
        worker_name = f"automation-worker-{len(_worker_threads) + 1}"
        thread = threading.Thread(
            target=_run,
            daemon=True,
            name=worker_name,
        )
        thread.start()
        _worker_threads.append(thread)

    print(
        f"[Automation worker] started {workers_to_start} worker(s). Total: {len(_worker_threads)}"
    )


def _execute_action(
    *,
    action_id: str,
    action_type: str,
    app_user_id: str,
    instagram_user: dict,
) -> None:
    """Process all pending items for one action, one at a time with delays."""
    pending_items = db_service.list_automation_action_items(
        action_id, statuses=["pending"]
    )

    if not pending_items:
        # May happen on idempotent re-run of a completed action.
        automation_runner.mark_action_completed(action_id)
        return

    if action_type == "batch_follow":
        executor = execute_follow_item
    elif action_type == "batch_unfollow":
        executor = execute_unfollow_item
    elif action_type == "left_right_compare":
        executor = execute_left_right_compare_item
    else:
        raise ValueError(f"Unsupported automation action type: {action_type}")

    for idx, item in enumerate(pending_items):
        current = automation_runner.get_action_status(action_id)
        if current and current.get("status") == "cancelled":
            print(
                f"[Automation worker] action {action_id} cancelled mid-run, stopping at item {idx}"
            )
            return

        automation_runner.mark_action_heartbeat(action_id)

        success = executor(
            item=item,
            instagram_user=instagram_user,
            app_user_id=app_user_id,
        )
        if success:
            automation_runner.record_item_completed(action_id)
        else:
            automation_runner.record_item_failed(action_id)

        # Respect rate limits between actions — skip delay after last item.
        if idx < len(pending_items) - 1:
            automation_runner.mark_action_heartbeat(action_id)
            inter_action_delay()

    # Determine final status based on outcome counts.
    final = db_service.get_automation_action(action_id)
    if final:
        if action_type == "left_right_compare":
            config = dict(final.get("config") or {})
            comparison_result = dict(config.get("comparison_result") or {})
            if comparison_result:
                comparison_result["status"] = "completed"
                config["comparison_result"] = comparison_result
                db_service.update_automation_action(action_id, config_json=config)
                final = db_service.get_automation_action(action_id) or final

        failed = final.get("failed_items") or 0
        completed = final.get("completed_items") or 0
        if failed == 0:
            automation_runner.mark_action_completed(action_id)
        elif completed == 0:
            if action_type == "left_right_compare":
                config = dict(final.get("config") or {})
                comparison_result = dict(config.get("comparison_result") or {})
                if comparison_result:
                    comparison_result["status"] = "error"
                    config["comparison_result"] = comparison_result
                    db_service.update_automation_action(action_id, config_json=config)
            automation_runner.mark_action_error(action_id, "All items failed")
        else:
            if action_type == "left_right_compare":
                config = dict(final.get("config") or {})
                comparison_result = dict(config.get("comparison_result") or {})
                if comparison_result:
                    comparison_result["status"] = "partial"
                    config["comparison_result"] = comparison_result
                    db_service.update_automation_action(action_id, config_json=config)
            automation_runner.mark_action_partial(action_id)
