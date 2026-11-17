import logging
import multiprocessing
import os
import threading
import time

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue, Worker

from app.config import get_settings
from app.jobs import schedule_cleanup
from app.logging_config import configure_logging

logger = logging.getLogger("clip.worker")
QUEUE_NAME = "default"
CONNECT_ATTEMPTS = 15
CONNECT_WAIT_SECONDS = 1


def connect_redis(redis_url: str) -> Redis:
    last_error: RedisError | None = None
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            client = Redis.from_url(redis_url)
            client.ping()
            return client
        except RedisError as exc:
            last_error = exc
            logger.info("redis_retry attempt=%s", attempt)
            time.sleep(CONNECT_WAIT_SECONDS)
    raise RuntimeError("Não foi possível conectar ao Redis") from last_error


def run_worker() -> None:
    settings = get_settings()
    connection = connect_redis(settings.redis_url)
    queue = Queue(QUEUE_NAME, connection=connection)
    logger.info("worker_started queue=%s", QUEUE_NAME)
    worker = Worker(queues=[queue], connection=connection)
    worker.work()


def cleanup_loop() -> None:
    settings = get_settings()
    while True:
        time.sleep(settings.cleanup_interval_seconds)
        try:
            schedule_cleanup()
        except Exception:
            logger.exception("cleanup_schedule_failed")


def main() -> None:
    configure_logging()
    settings = get_settings()
    if not os.environ.get("REDIS_URL") and settings.clip_env == "production":
        logger.error("REDIS_URL ausente")
        raise SystemExit(1)
    thread = threading.Thread(target=cleanup_loop, name="cleanup", daemon=True)
    thread.start()
    count = max(1, settings.worker_concurrency)
    if count == 1:
        run_worker()
        return
    processes = [multiprocessing.Process(target=run_worker, name=f"clip-worker-{index}") for index in range(count)]
    for process in processes:
        process.start()
    for process in processes:
        process.join()


if __name__ == "__main__":
    main()
