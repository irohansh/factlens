"""
Background Job Queue implementation for FactLens.
Supports Redis list queue (LPUSH/BRPOP) with automatic zero-crash fallback
to Python concurrent.futures.ThreadPoolExecutor when Redis is offline.
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from factlens.config import settings
from factlens.cache import get_cache
from factlens.worker import process_document_job

logger = logging.getLogger("factlens.queue")

REDIS_QUEUE_KEY = "factlens:jobs:queue"


class JobQueue:
    """
    Queue manager handling job dispatching and background worker execution.
    """

    def __init__(self, mode: Optional[str] = None):
        self.mode = (mode or settings.QUEUE_MODE).lower()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="factlens_worker")
        self._running = False
        self._consumer_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start background queue consumers if not already running."""
        if self._running:
            return
        self._running = True

        cache = get_cache()
        if self.mode == "redis" and cache.is_available():
            logger.info("Starting Redis background consumer thread on queue key '%s'...", REDIS_QUEUE_KEY)
            self._consumer_thread = threading.Thread(
                target=self._redis_consumer_loop,
                daemon=True,
                name="FactLens-RedisQueueConsumer"
            )
            self._consumer_thread.start()
        else:
            logger.info("JobQueue initialized in ThreadPoolExecutor mode (workers=4).")

    def stop(self) -> None:
        """Stop consumers and wait for workers to finish."""
        self._running = False
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=2.0)
        self._executor.shutdown(wait=False)
        logger.info("JobQueue stopped.")

    def enqueue(self, job_id: str, doc_id: str) -> None:
        """
        Enqueue a document processing job.
        Dispatches to Redis if available, or directly to ThreadPoolExecutor.
        """
        cache = get_cache()
        use_redis = (self.mode == "redis") and cache.is_available()

        if use_redis:
            try:
                payload = json.dumps({"job_id": job_id, "doc_id": doc_id})
                cache.client.lpush(REDIS_QUEUE_KEY, payload)
                logger.info("Pushed job %s for document %s to Redis queue.", job_id, doc_id)
                # Ensure consumer is running
                if not self._running or not (self._consumer_thread and self._consumer_thread.is_alive()):
                    self.start()
                return
            except Exception as e:
                logger.warning("Failed pushing job %s to Redis (%s), falling back to in-memory thread pool.", job_id, e)

        # In-memory ThreadPoolExecutor fallback
        logger.info("Submitting job %s for document %s to ThreadPoolExecutor.", job_id, doc_id)
        self._executor.submit(process_document_job, job_id, doc_id)

    def _redis_consumer_loop(self) -> None:
        """Continuously pulls tasks from Redis queue and processes them."""
        cache = get_cache()
        while self._running:
            try:
                if not cache.is_available():
                    time.sleep(2.0)
                    continue

                # brpop with 2 second timeout so thread can check self._running
                result = cache.client.brpop(REDIS_QUEUE_KEY, timeout=2)
                if result:
                    _, raw_payload = result
                    payload = json.loads(raw_payload)
                    job_id = payload.get("job_id")
                    doc_id = payload.get("doc_id")
                    if job_id and doc_id:
                        # Process in thread pool to avoid blocking the single consumer
                        self._executor.submit(process_document_job, job_id, doc_id)
            except Exception as e:
                logger.error("Error in Redis consumer loop: %s", e)
                time.sleep(2.0)


# Global queue singleton
_queue_instance: Optional[JobQueue] = None

def get_queue() -> JobQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = JobQueue()
        _queue_instance.start()
    return _queue_instance
