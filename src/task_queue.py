"""
Task Queue with Multi-Worker Support

Handles batched processing with:
- Work batches of ~1000 files for efficient parallel processing
- Multiple concurrent workers that claim entire batches
- Retry logic with exponential backoff (via tenacity)
- Circuit breaker pattern for API failures
- Dead letter queue for permanent failures

Architecture:
- Job: A complete sync run (scan → hash → upload)
- WorkBatch: A chunk of ~1000 files claimed by a single worker
- Task: Individual file operation within a batch
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Batch size for chunking files (100 for more granular progress updates)
BATCH_SIZE = 100


def get_retry_delay(retry_count: int, max_delay: float = 300.0, initial: float = 1.0) -> float:
    """
    Calculate retry delay using exponential backoff with jitter.

    Based on tenacity's wait_exponential_jitter algorithm:
    - Base delay doubles each retry: initial * 2^retry_count
    - Adds random jitter in range [0, base_delay] to prevent thundering herd
    - Caps at max_delay
    """
    # Exponential backoff: initial * 2^retry_count
    exp_delay = initial * (2 ** retry_count)

    # Add jitter: random value between 0 and exp_delay
    jitter = random.uniform(0, exp_delay)

    # Total delay with cap
    return min(exp_delay + jitter, max_delay)


class CircuitState(Enum):
    CLOSED = "closed"    # Normal operation
    OPEN = "open"        # Blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Simple async circuit breaker for API protection."""

    def __init__(self, fail_max: int = 5, reset_timeout: float = 60.0, success_threshold: int = 2):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.success_threshold = success_threshold
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def current_state(self) -> str:
        return self.state.value

    async def can_execute(self) -> bool:
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if self.last_failure_time:
                    elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                    if elapsed >= self.reset_timeout:
                        self.state = CircuitState.HALF_OPEN
                        logger.info("Circuit breaker: OPEN -> HALF_OPEN")
                        return True
                return False

            return True  # HALF_OPEN allows test request

    async def record_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    logger.info("Circuit breaker: HALF_OPEN -> CLOSED (recovered)")
            else:
                self.failure_count = 0

    async def record_failure(self):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
                logger.warning("Circuit breaker: HALF_OPEN -> OPEN (still failing)")
            elif self.failure_count >= self.fail_max:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker: CLOSED -> OPEN (after {self.failure_count} failures)")


# Global circuit breaker instance
circuit_breaker = CircuitBreaker(fail_max=5, reset_timeout=60)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    DEAD = "dead"  # Moved to dead letter queue


class TaskType(Enum):
    HASH = "hash"
    UPLOAD = "upload"
    VERIFY = "verify"


class BatchStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    id: int
    job_id: int
    work_batch_id: Optional[int]
    file_id: int
    task_type: TaskType
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None


@dataclass
class WorkBatch:
    """A chunk of ~1000 files for a worker to process."""
    id: int
    job_id: int
    batch_type: str  # 'hash' or 'upload'
    batch_number: int
    file_count: int
    status: BatchStatus = BatchStatus.PENDING
    worker_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    files_processed: int = 0
    files_succeeded: int = 0
    files_failed: int = 0
    tasks: list[Task] = field(default_factory=list)


class TaskQueue:
    """
    SQLite-backed task queue with work batch support.

    Files are chunked into work_batches of ~1000 files each.
    Workers claim entire batches and process all files within.
    """

    def __init__(self, db, batch_size: int = BATCH_SIZE):
        self.db = db
        self.batch_size = batch_size
        self._shutdown = False

    async def create_work_batches(
        self,
        job_id: int,
        file_ids: list[int],
        task_type: TaskType
    ) -> list[int]:
        """
        Create work batches by chunking file_ids into groups of batch_size.
        Returns list of work_batch IDs.
        """
        work_batch_ids = []
        batch_number = 1

        for i in range(0, len(file_ids), self.batch_size):
            chunk = file_ids[i:i + self.batch_size]

            # Create work_batch record
            cursor = await self.db.execute("""
                INSERT INTO work_batches (job_id, batch_type, batch_number, file_count, status)
                VALUES (?, ?, ?, ?, ?)
            """, (job_id, task_type.value, batch_number, len(chunk), BatchStatus.PENDING.value))
            work_batch_id = cursor.lastrowid

            # Create tasks for this batch
            task_data = [
                (job_id, work_batch_id, fid, task_type.value, 0, TaskStatus.PENDING.value)
                for fid in chunk
            ]
            await self.db.executemany("""
                INSERT INTO tasks (job_id, work_batch_id, file_id, task_type, priority, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, task_data)

            work_batch_ids.append(work_batch_id)
            batch_number += 1

        await self.db.commit()
        logger.info(f"Created {len(work_batch_ids)} work batches for job {job_id} ({task_type.value})")
        return work_batch_ids

    async def claim_work_batch(self, worker_id: int, task_type: Optional[TaskType] = None, job_id: Optional[int] = None) -> Optional[WorkBatch]:
        """
        Atomically claim the next available work batch for processing.
        Returns the WorkBatch with all its tasks loaded.
        If job_id is specified, only claims batches from that job.
        """
        # Build query with parameterized filters
        params = [BatchStatus.PENDING.value]
        query = "SELECT id FROM work_batches WHERE status = ?"

        if task_type:
            query += " AND batch_type = ?"
            params.append(task_type.value)
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)

        query += " ORDER BY id ASC LIMIT 1"

        # Find and claim a pending batch
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            batch_id = row[0]

        # Claim it - use rowcount to detect race condition
        cursor = await self.db.execute("""
            UPDATE work_batches
            SET status = ?, worker_id = ?, started_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = ?
        """, (BatchStatus.RUNNING.value, worker_id, batch_id, BatchStatus.PENDING.value))
        await self.db.commit()

        # Check if we actually claimed it (another worker may have grabbed it first)
        if cursor.rowcount == 0:
            # Lost the race - try again with next available batch
            return await self.claim_work_batch(worker_id, task_type, job_id)

        # Load full batch with tasks
        return await self._load_work_batch(batch_id)

    async def _load_work_batch(self, batch_id: int) -> Optional[WorkBatch]:
        """Load a work batch and all its tasks."""
        async with self.db.execute(
            "SELECT * FROM work_batches WHERE id = ?", (batch_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

        batch = WorkBatch(
            id=row["id"],
            job_id=row["job_id"],
            batch_type=row["batch_type"],
            batch_number=row["batch_number"],
            file_count=row["file_count"],
            status=BatchStatus(row["status"]),
            worker_id=row["worker_id"],
            files_processed=row["files_processed"],
            files_succeeded=row["files_succeeded"],
            files_failed=row["files_failed"],
        )

        # Load tasks
        async with self.db.execute(
            "SELECT * FROM tasks WHERE work_batch_id = ?", (batch_id,)
        ) as cursor:
            async for task_row in cursor:
                batch.tasks.append(self._row_to_task(task_row))

        return batch

    async def complete_task(self, task_id: int, success: bool, error: Optional[str] = None):
        """Mark a single task as completed."""
        if success:
            await self.db.execute("""
                UPDATE tasks
                SET status = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (TaskStatus.SUCCESS.value, task_id))
        else:
            await self._handle_task_failure(task_id, error)
        await self.db.commit()

    async def _handle_task_failure(self, task_id: int, error: Optional[str]):
        """Handle task failure with retry logic using tenacity for delay calculation."""
        async with self.db.execute(
            "SELECT retry_count, max_retries FROM tasks WHERE id = ?",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            retry_count, max_retries = row

        if retry_count < max_retries:
            delay = get_retry_delay(retry_count)
            next_retry = datetime.now() + timedelta(seconds=delay)
            await self.db.execute("""
                UPDATE tasks
                SET status = ?, retry_count = retry_count + 1,
                    error_message = ?, next_retry_at = ?
                WHERE id = ?
            """, (TaskStatus.RETRY.value, error, next_retry.isoformat(), task_id))
            logger.info(f"Task {task_id} scheduled for retry in {delay:.1f}s")
        else:
            await self.db.execute("""
                UPDATE tasks
                SET status = ?, completed_at = CURRENT_TIMESTAMP, error_message = ?
                WHERE id = ?
            """, (TaskStatus.DEAD.value, error, task_id))
            logger.error(f"Task {task_id} moved to dead letter queue: {error}")

    async def complete_work_batch(
        self,
        batch_id: int,
        files_succeeded: int,
        files_failed: int
    ):
        """Mark a work batch as completed."""
        status = BatchStatus.COMPLETED if files_failed == 0 else BatchStatus.FAILED
        await self.db.execute("""
            UPDATE work_batches
            SET status = ?, completed_at = CURRENT_TIMESTAMP,
                files_processed = files_succeeded + files_failed,
                files_succeeded = ?, files_failed = ?
            WHERE id = ?
        """, (status.value, files_succeeded, files_failed, batch_id))
        await self.db.commit()
        logger.info(f"WorkBatch {batch_id} completed: {files_succeeded} succeeded, {files_failed} failed")

    async def update_batch_progress(self, batch_id: int, files_processed: int):
        """Update progress within a batch."""
        await self.db.execute("""
            UPDATE work_batches SET files_processed = ? WHERE id = ?
        """, (files_processed, batch_id))
        await self.db.commit()

    async def get_job_progress(self, job_id: int) -> dict:
        """Get aggregated progress for a job."""
        async with self.db.execute("""
            SELECT
                COUNT(*) as total_batches,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_batches,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running_batches,
                SUM(files_succeeded) as total_succeeded,
                SUM(files_failed) as total_failed,
                SUM(file_count) as total_files
            FROM work_batches
            WHERE job_id = ?
        """, (job_id,)) as cursor:
            row = await cursor.fetchone()

        return {
            "total_batches": row[0] or 0,
            "completed_batches": row[1] or 0,
            "running_batches": row[2] or 0,
            "total_succeeded": row[3] or 0,
            "total_failed": row[4] or 0,
            "total_files": row[5] or 0,
        }

    async def get_queue_stats(self) -> dict:
        """Get current queue statistics."""
        stats = {
            "pending_batches": 0,
            "running_batches": 0,
            "completed_batches": 0,
            "failed_batches": 0,
            "by_type": {},
            "circuit_breaker": circuit_breaker.current_state,
        }

        async with self.db.execute("""
            SELECT batch_type, status, COUNT(*) as count
            FROM work_batches
            GROUP BY batch_type, status
        """) as cursor:
            async for row in cursor:
                batch_type, status, count = row
                if batch_type not in stats["by_type"]:
                    stats["by_type"][batch_type] = {}
                stats["by_type"][batch_type][status] = count

                if status == "pending":
                    stats["pending_batches"] += count
                elif status == "running":
                    stats["running_batches"] += count
                elif status == "completed":
                    stats["completed_batches"] += count
                elif status == "failed":
                    stats["failed_batches"] += count

        return stats

    async def update_queue_metrics(self):
        """Update in-memory queue depth metrics for dashboard."""
        from .metrics import get_metrics

        metrics = get_metrics()

        # Query batch counts and file counts by type and status
        hash_pending = hash_running = hash_pending_files = 0
        upload_pending = upload_running = upload_pending_files = 0

        async with self.db.execute("""
            SELECT batch_type, status, COUNT(*) as batch_count, SUM(file_count) as total_files
            FROM work_batches
            WHERE status IN ('pending', 'running')
            GROUP BY batch_type, status
        """) as cursor:
            async for row in cursor:
                batch_type, status, batch_count, total_files = row
                if batch_type == 'hash':
                    if status == 'pending':
                        hash_pending = batch_count
                        hash_pending_files = total_files or 0
                    elif status == 'running':
                        hash_running = batch_count
                elif batch_type == 'upload':
                    if status == 'pending':
                        upload_pending = batch_count
                        upload_pending_files = total_files or 0
                    elif status == 'running':
                        upload_running = batch_count

        metrics.update_queue_depths(
            hash_pending_batches=hash_pending,
            hash_running_batches=hash_running,
            hash_pending_files=hash_pending_files,
            upload_pending_batches=upload_pending,
            upload_running_batches=upload_running,
            upload_pending_files=upload_pending_files,
        )

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task object."""
        return Task(
            id=row["id"],
            job_id=row["job_id"],
            work_batch_id=row["work_batch_id"],
            file_id=row["file_id"],
            task_type=TaskType(row["task_type"]),
            priority=row["priority"],
            status=TaskStatus(row["status"]),
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )


class BatchWorker:
    """
    Async worker that processes entire work batches.

    Each worker claims a batch of ~100 files and processes them all
    before claiming the next batch. Tracks real-time metrics.
    """

    def __init__(
        self,
        worker_id: int,
        queue: TaskQueue,
        handlers: dict[TaskType, Callable],
        worker_type: str = "upload",
        batch_handlers: dict[TaskType, Callable] = None,  # For batched processing
        job_id: Optional[int] = None,  # Only process batches for this job
    ):
        self.worker_id = worker_id
        self.queue = queue
        self.handlers = handlers
        self.batch_handlers = batch_handlers or {}  # Handler(tasks: list[Task]) for batched ops
        self.worker_type = worker_type
        self.job_id = job_id  # Filter to specific job
        self._running = False
        self._current_batch: Optional[WorkBatch] = None

        # Register with metrics
        from .metrics import get_metrics
        self._metrics = get_metrics().get_or_create_worker(worker_id, worker_type)

    async def start(self):
        """Start the worker loop."""
        self._running = True
        logger.info(f"BatchWorker {self.worker_id} ({self.worker_type}) started")

        while self._running:
            try:
                await self._process_one_batch()
            except Exception as e:
                logger.exception(f"BatchWorker {self.worker_id} error: {e}")
                await asyncio.sleep(1)

    async def stop(self):
        """Gracefully stop the worker."""
        self._running = False
        self._metrics.clear_batch()
        logger.info(f"BatchWorker {self.worker_id} stopping")

    async def _process_one_batch(self):
        """Claim and process one work batch with metrics tracking."""
        import time

        # Check circuit breaker
        if circuit_breaker.current_state == "open":
            logger.debug(f"BatchWorker {self.worker_id}: Circuit open, waiting...")
            await asyncio.sleep(5)
            return

        # Claim a batch (optionally filtered to specific job)
        batch = await self.queue.claim_work_batch(self.worker_id, job_id=self.job_id)
        if not batch:
            await asyncio.sleep(0.5)  # No batches, wait
            return

        self._current_batch = batch

        # Start batch metrics tracking
        self._metrics.start_batch(batch.id, batch.batch_number, batch.file_count)

        handler = self.handlers.get(TaskType(batch.batch_type))

        if not handler:
            logger.error(f"No handler for batch type: {batch.batch_type}")
            await self.queue.complete_work_batch(batch.id, 0, batch.file_count)
            self._metrics.clear_batch()
            return

        logger.info(f"BatchWorker {self.worker_id} processing batch {batch.id} ({batch.file_count} files)")

        succeeded = 0
        failed = 0

        for task in batch.tasks:
            if not self._running:
                break

            file_start_time = time.time()
            file_bytes = 0

            try:
                # Get file size for throughput calculation
                async with self.queue.db.execute(
                    "SELECT size FROM files WHERE id = ?", (task.file_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    file_bytes = row[0] if row else 0

                await handler(task)

                # Check if task is pipelined (completion handled elsewhere)
                if getattr(task, 'pipelined', False):
                    # Pipelined task - batcher will handle completion
                    # Just count as handed off for batch progress
                    succeeded += 1
                    elapsed = time.time() - file_start_time
                    self._metrics.record_file_complete(file_bytes, elapsed)
                else:
                    # Normal task - mark complete here
                    await self.queue.complete_task(task.id, True)
                    succeeded += 1
                    elapsed = time.time() - file_start_time
                    self._metrics.record_file_complete(file_bytes, elapsed)

            except RetryableError as e:
                logger.warning(f"Task {task.id} retryable error: {e}")
                await self.queue.complete_task(task.id, False, str(e))
                failed += 1
                self._metrics.files_processed += 1
            except PermanentError as e:
                logger.error(f"Task {task.id} permanent error: {e}")
                await self.queue.db.execute(
                    "UPDATE tasks SET retry_count = max_retries WHERE id = ?",
                    (task.id,)
                )
                await self.queue.complete_task(task.id, False, str(e))
                failed += 1
                self._metrics.files_processed += 1
            except Exception as e:
                logger.exception(f"Task {task.id} unexpected error")
                await self.queue.complete_task(task.id, False, str(e))
                failed += 1
                self._metrics.files_processed += 1

            # Update DB progress every 10 files
            if (succeeded + failed) % 10 == 0:
                await self.queue.update_batch_progress(batch.id, succeeded + failed)

        await self.queue.complete_work_batch(batch.id, succeeded, failed)
        self._metrics.clear_batch()
        self._current_batch = None


class RetryableError(Exception):
    """Error that should trigger a retry (e.g., rate limit, timeout)."""
    pass


class PermanentError(Exception):
    """Error that should not retry (e.g., file not found, invalid format)."""
    pass


class WorkerPool:
    """
    Manages a pool of batch workers for parallel processing.
    """

    def __init__(
        self,
        queue: TaskQueue,
        handlers: dict[TaskType, Callable],
        num_workers: int = 4,
        job_id: Optional[int] = None,  # Only process batches for this job
    ):
        self.queue = queue
        self.handlers = handlers
        self.num_workers = num_workers
        self.job_id = job_id
        self.workers: list[BatchWorker] = []
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        """Start all workers."""
        for i in range(self.num_workers):
            worker = BatchWorker(i, self.queue, self.handlers, job_id=self.job_id)
            self.workers.append(worker)
            task = asyncio.create_task(worker.start())
            self._tasks.append(task)

        logger.info(f"Started {self.num_workers} batch workers")

    async def stop(self):
        """Stop all workers gracefully."""
        for worker in self.workers:
            await worker.stop()

        # Wait for all workers to finish current batches
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("All batch workers stopped")

    async def scale(self, num_workers: int):
        """Dynamically adjust number of workers."""
        current = len(self.workers)

        if num_workers > current:
            for i in range(current, num_workers):
                worker = BatchWorker(i, self.queue, self.handlers)
                self.workers.append(worker)
                task = asyncio.create_task(worker.start())
                self._tasks.append(task)
            logger.info(f"Scaled up to {num_workers} workers")

        elif num_workers < current:
            for _ in range(current - num_workers):
                worker = self.workers.pop()
                await worker.stop()
            logger.info(f"Scaled down to {num_workers} workers")

    def get_status(self) -> dict:
        """Get status of all workers."""
        return {
            "total_workers": len(self.workers),
            "active": sum(1 for w in self.workers if w._current_batch),
            "workers": [
                {
                    "id": w.worker_id,
                    "running": w._running,
                    "current_batch": w._current_batch.id if w._current_batch else None,
                    "current_batch_files": w._current_batch.file_count if w._current_batch else 0,
                }
                for w in self.workers
            ]
        }
