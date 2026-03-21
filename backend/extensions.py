from queue import Queue

# task queue stores tuples of (app_user_id, pk_id, profile_pic_url) for image download workers to consume
image_download_queue: Queue[tuple[str, str, str]] = Queue()

# prediction refresh queue stores dict payloads consumed by the prediction worker
prediction_refresh_queue: Queue[dict] = Queue()
