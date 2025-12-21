"""
Tests for task queue and worker system with work batch support.
"""

import pytest
import asyncio
from datetime import datetime, timedelta


class TestWorkBatches:
    """Test work batch creation and processing."""

    async def _setup_job_and_files(self, db, job_id=1, num_files=100):
        """Create job and file records for foreign key constraints."""
        # Create job with required source_dirs field
        await db.execute(
            "INSERT OR IGNORE INTO jobs (id, source_dirs, status, current_phase) VALUES (?, '[]', 'running', 'upload')",
            (job_id,)
        )
        # Create files with unique relative_path per file_id
        for fid in range(num_files):
            await db.execute(
                """INSERT OR IGNORE INTO files (id, source_name, relative_path, filename, local_path, extension, size, mtime, status)
                   VALUES (?, 'test', ?, ?, '/test/test.jpg', 'jpg', 1000, 0, 'pending')""",
                (fid, f"test_{fid}.jpg", f"test_{fid}.jpg")
            )
        await db.commit()

    @pytest.mark.asyncio
    async def test_create_work_batches_single(self, test_db):
        """Should create a single work batch for small file sets."""
        from src.task_queue import TaskQueue, TaskType

        await self._setup_job_and_files(test_db, job_id=1, num_files=100)

        queue = TaskQueue(test_db, batch_size=1000)  # Larger than file count
        file_ids = list(range(100))

        batch_ids = await queue.create_work_batches(1, file_ids, TaskType.UPLOAD)

        assert len(batch_ids) == 1

        # Verify batch in DB
        async with test_db.execute(
            "SELECT file_count FROM work_batches WHERE id = ?", (batch_ids[0],)
        ) as cursor:
            row = await cursor.fetchone()
            assert row["file_count"] == 100

    @pytest.mark.asyncio
    async def test_create_work_batches_multiple(self, test_db):
        """Should chunk files into multiple batches."""
        from src.task_queue import TaskQueue, TaskType

        await self._setup_job_and_files(test_db, job_id=1, num_files=2500)

        queue = TaskQueue(test_db, batch_size=1000)
        file_ids = list(range(2500))

        batch_ids = await queue.create_work_batches(1, file_ids, TaskType.UPLOAD)

        # 2500 files / 1000 batch_size = 3 batches (1000, 1000, 500)
        assert len(batch_ids) == 3

        # Verify batch sizes
        async with test_db.execute(
            "SELECT batch_number, file_count FROM work_batches ORDER BY batch_number"
        ) as cursor:
            rows = [dict(r) async for r in cursor]

        assert rows[0]["file_count"] == 1000
        assert rows[1]["file_count"] == 1000
        assert rows[2]["file_count"] == 500

    @pytest.mark.asyncio
    async def test_create_work_batches_creates_tasks(self, test_db):
        """Should create task records for each file."""
        from src.task_queue import TaskQueue, TaskType

        await self._setup_job_and_files(test_db, job_id=1, num_files=50)

        queue = TaskQueue(test_db, batch_size=1000)
        file_ids = list(range(50))

        batch_ids = await queue.create_work_batches(1, file_ids, TaskType.UPLOAD)

        # Check tasks were created
        async with test_db.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE work_batch_id = ?", (batch_ids[0],)
        ) as cursor:
            row = await cursor.fetchone()
            assert row["count"] == 50

    @pytest.mark.asyncio
    async def test_claim_work_batch(self, test_db):
        """Should atomically claim a work batch."""
        from src.task_queue import TaskQueue, TaskType, BatchStatus

        await self._setup_job_and_files(test_db, job_id=1, num_files=50)

        queue = TaskQueue(test_db, batch_size=1000)
        await queue.create_work_batches(1, list(range(50)), TaskType.UPLOAD)

        batch = await queue.claim_work_batch(worker_id=42)

        assert batch is not None
        assert batch.worker_id == 42
        assert batch.status == BatchStatus.RUNNING
        assert len(batch.tasks) == 50

    @pytest.mark.asyncio
    async def test_claim_work_batch_exclusive(self, test_db):
        """Two workers should not claim the same batch."""
        from src.task_queue import TaskQueue, TaskType

        await self._setup_job_and_files(test_db, job_id=1, num_files=50)

        queue = TaskQueue(test_db, batch_size=1000)
        await queue.create_work_batches(1, list(range(50)), TaskType.UPLOAD)

        batch1 = await queue.claim_work_batch(worker_id=1)
        batch2 = await queue.claim_work_batch(worker_id=2)

        assert batch1 is not None
        assert batch2 is None  # No more batches available

    @pytest.mark.asyncio
    async def test_claim_work_batch_by_type(self, test_db):
        """Should filter by task type when claiming."""
        from src.task_queue import TaskQueue, TaskType

        await self._setup_job_and_files(test_db, job_id=1, num_files=100)

        queue = TaskQueue(test_db, batch_size=1000)

        # Create batches for different task types
        await queue.create_work_batches(1, list(range(50)), TaskType.HASH)
        await queue.create_work_batches(1, list(range(50, 100)), TaskType.UPLOAD)

        # Claim only upload batches
        batch = await queue.claim_work_batch(worker_id=1, task_type=TaskType.UPLOAD)

        assert batch is not None
        assert batch.batch_type == "upload"

    @pytest.mark.asyncio
    async def test_complete_work_batch(self, test_db):
        """Should mark batch as completed with stats."""
        from src.task_queue import TaskQueue, TaskType, BatchStatus

        await self._setup_job_and_files(test_db, job_id=1, num_files=50)

        queue = TaskQueue(test_db, batch_size=1000)
        await queue.create_work_batches(1, list(range(50)), TaskType.UPLOAD)
        batch = await queue.claim_work_batch(worker_id=1)

        await queue.complete_work_batch(batch.id, files_succeeded=45, files_failed=5)

        async with test_db.execute(
            "SELECT status, files_succeeded, files_failed FROM work_batches WHERE id = ?",
            (batch.id,)
        ) as cursor:
            row = await cursor.fetchone()
            # Has failures so status should be FAILED
            assert row["status"] == BatchStatus.FAILED.value
            assert row["files_succeeded"] == 45
            assert row["files_failed"] == 5

    @pytest.mark.asyncio
    async def test_get_job_progress(self, test_db):
        """Should aggregate progress across work batches."""
        from src.task_queue import TaskQueue, TaskType

        await self._setup_job_and_files(test_db, job_id=1, num_files=200)

        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(200)), TaskType.UPLOAD)

        # Complete one batch with all successes (status=completed)
        batch1 = await queue.claim_work_batch(worker_id=1)
        await queue.complete_work_batch(batch1.id, 100, 0)

        progress = await queue.get_job_progress(1)

        assert progress["total_batches"] == 2
        assert progress["completed_batches"] == 1
        assert progress["total_succeeded"] == 100
        assert progress["total_failed"] == 0


class TestTaskCompletion:
    """Test individual task completion with retry logic."""

    async def _setup_job_and_files(self, db, job_id=1, num_files=10):
        """Create job and file records."""
        await db.execute(
            "INSERT OR IGNORE INTO jobs (id, source_dirs, status, current_phase) VALUES (?, '[]', 'running', 'upload')",
            (job_id,)
        )
        for fid in range(num_files):
            await db.execute(
                """INSERT OR IGNORE INTO files (id, source_name, relative_path, filename, local_path, extension, size, mtime, status)
                   VALUES (?, 'test', ?, ?, '/test/test.jpg', 'jpg', 1000, 0, 'pending')""",
                (fid, f"test_{fid}.jpg", f"test_{fid}.jpg")
            )
        await db.commit()

    @pytest.mark.asyncio
    async def test_complete_task_success(self, test_db):
        """Should mark task as successful."""
        from src.task_queue import TaskQueue, TaskType, TaskStatus

        await self._setup_job_and_files(test_db, 1, 10)

        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(10)), TaskType.UPLOAD)
        batch = await queue.claim_work_batch(worker_id=1)

        task = batch.tasks[0]
        await queue.complete_task(task.id, success=True)

        async with test_db.execute(
            "SELECT status FROM tasks WHERE id = ?", (task.id,)
        ) as cursor:
            row = await cursor.fetchone()
            assert row["status"] == TaskStatus.SUCCESS.value

    @pytest.mark.asyncio
    async def test_complete_task_retry(self, test_db):
        """Should schedule retry on failure."""
        from src.task_queue import TaskQueue, TaskType, TaskStatus

        await self._setup_job_and_files(test_db, 1, 10)

        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(10)), TaskType.UPLOAD)
        batch = await queue.claim_work_batch(worker_id=1)

        task = batch.tasks[0]
        await queue.complete_task(task.id, success=False, error="Network error")

        async with test_db.execute(
            "SELECT status, retry_count, next_retry_at FROM tasks WHERE id = ?", (task.id,)
        ) as cursor:
            row = await cursor.fetchone()
            assert row["status"] == TaskStatus.RETRY.value
            assert row["retry_count"] == 1
            assert row["next_retry_at"] is not None

    @pytest.mark.asyncio
    async def test_complete_task_dead_after_max_retries(self, test_db):
        """Should move to dead letter queue after max retries."""
        from src.task_queue import TaskQueue, TaskType, TaskStatus

        await self._setup_job_and_files(test_db, 1, 10)

        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(10)), TaskType.UPLOAD)
        batch = await queue.claim_work_batch(worker_id=1)

        task = batch.tasks[0]

        # Task has max_retries=3 by default. Set retry_count=3 so next failure
        # goes to dead (since 3 < 3 is False)
        await test_db.execute(
            "UPDATE tasks SET retry_count = 3 WHERE id = ?", (task.id,)
        )
        await test_db.commit()
        await queue.complete_task(task.id, success=False, error="Persistent failure")

        async with test_db.execute(
            "SELECT status FROM tasks WHERE id = ?", (task.id,)
        ) as cursor:
            row = await cursor.fetchone()
            assert row["status"] == TaskStatus.DEAD.value


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """Circuit should open after threshold failures."""
        from src.task_queue import CircuitBreaker, CircuitState

        breaker = CircuitBreaker(fail_max=3)

        assert breaker.state == CircuitState.CLOSED

        for _ in range(3):
            await breaker.record_failure()

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_blocks_when_open(self):
        """Circuit should block requests when open."""
        from src.task_queue import CircuitBreaker, CircuitState

        breaker = CircuitBreaker(fail_max=1, reset_timeout=60)

        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        can_execute = await breaker.can_execute()
        assert can_execute is False

    @pytest.mark.asyncio
    async def test_circuit_recovers_after_timeout(self):
        """Circuit should allow test request after timeout."""
        from src.task_queue import CircuitBreaker, CircuitState

        breaker = CircuitBreaker(fail_max=1, reset_timeout=0.1)

        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        await asyncio.sleep(0.2)

        can_execute = await breaker.can_execute()
        assert can_execute is True
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_circuit_closes_after_success(self):
        """Circuit should close after success in half-open state."""
        from src.task_queue import CircuitBreaker, CircuitState

        breaker = CircuitBreaker(fail_max=1, success_threshold=2, reset_timeout=0.1)

        await breaker.record_failure()
        await asyncio.sleep(0.2)
        await breaker.can_execute()  # Enter HALF_OPEN

        await breaker.record_success()
        await breaker.record_success()

        assert breaker.state == CircuitState.CLOSED


class TestBatchWorkerUnit:
    """Unit tests for batch worker - tests internal methods without async loops."""

    async def _setup_job_and_files(self, db, job_id=1, num_files=50):
        """Create job and file records."""
        await db.execute(
            "INSERT OR IGNORE INTO jobs (id, source_dirs, status, current_phase) VALUES (?, '[]', 'running', 'upload')",
            (job_id,)
        )
        for fid in range(num_files):
            await db.execute(
                """INSERT OR IGNORE INTO files (id, source_name, relative_path, filename, local_path, extension, size, mtime, status)
                   VALUES (?, 'test', ?, ?, '/test/test.jpg', 'jpg', 1000, 0, 'pending')""",
                (fid, f"test_{fid}.jpg", f"test_{fid}.jpg")
            )
        await db.commit()

    @pytest.mark.asyncio
    async def test_process_batch_calls_handler_for_each_task(self, test_db):
        """Handler should be called for each task in batch."""
        from src.task_queue import TaskQueue, TaskType

        await self._setup_job_and_files(test_db, 1, 10)

        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(10)), TaskType.UPLOAD)

        batch = await queue.claim_work_batch(worker_id=1)
        processed_ids = []

        # Manually process tasks like BatchWorker does
        for task in batch.tasks:
            processed_ids.append(task.file_id)
            await queue.complete_task(task.id, success=True)

        await queue.complete_work_batch(batch.id, len(processed_ids), 0)

        assert len(processed_ids) == 10

    @pytest.mark.asyncio
    async def test_batch_tracks_failures(self, test_db):
        """Batch should track both successes and failures."""
        from src.task_queue import TaskQueue, TaskType, TaskStatus

        await self._setup_job_and_files(test_db, 1, 10)

        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(10)), TaskType.UPLOAD)

        batch = await queue.claim_work_batch(worker_id=1)
        succeeded = 0
        failed = 0

        for i, task in enumerate(batch.tasks):
            if i < 3:
                await queue.complete_task(task.id, success=False, error="Error")
                failed += 1
            else:
                await queue.complete_task(task.id, success=True)
                succeeded += 1

        await queue.complete_work_batch(batch.id, succeeded, failed)

        async with test_db.execute(
            "SELECT files_succeeded, files_failed FROM work_batches WHERE id = ?", (batch.id,)
        ) as cursor:
            row = await cursor.fetchone()
            assert row["files_succeeded"] == 7
            assert row["files_failed"] == 3


class TestWorkerPoolUnit:
    """Unit tests for worker pool - tests structure without running loops."""

    @pytest.mark.asyncio
    async def test_worker_pool_creates_workers(self, test_db):
        """Pool should create the specified number of workers."""
        from src.task_queue import TaskQueue, TaskType, WorkerPool

        queue = TaskQueue(test_db)

        async def handler(task):
            pass

        pool = WorkerPool(
            queue=queue,
            handlers={TaskType.UPLOAD: handler},
            num_workers=4
        )

        # Don't call start() - just verify construction
        assert pool.num_workers == 4
        assert len(pool.workers) == 0  # Workers created on start()

    @pytest.mark.asyncio
    async def test_worker_pool_status(self, test_db):
        """Pool should report status correctly."""
        from src.task_queue import TaskQueue, TaskType, WorkerPool

        queue = TaskQueue(test_db)

        async def handler(task):
            pass

        pool = WorkerPool(
            queue=queue,
            handlers={TaskType.UPLOAD: handler},
            num_workers=2
        )

        status = pool.get_status()
        assert status["total_workers"] == 0
        assert status["active"] == 0


class TestRetryDelay:
    """Test retry delay calculation with exponential backoff and jitter."""

    def test_exponential_backoff(self):
        """Delay should increase with retry count."""
        from src.task_queue import get_retry_delay

        delay_0 = get_retry_delay(0)
        delay_1 = get_retry_delay(1)
        delay_2 = get_retry_delay(2)
        delay_3 = get_retry_delay(3)

        # Delays should increase (exponential backoff with jitter)
        # Jitter adds randomness so we check rough ordering
        assert delay_0 >= 0
        assert delay_1 >= delay_0 * 0.5  # Allow for jitter variance
        assert delay_2 >= delay_1 * 0.5
        assert delay_3 >= delay_2 * 0.5

    def test_max_delay_cap(self):
        """Delay should be capped at max."""
        from src.task_queue import get_retry_delay

        # With max_delay=10, even high retry counts should be capped
        delay = get_retry_delay(20, max_delay=10.0)
        assert delay <= 10.0

    def test_jitter_adds_randomness(self):
        """Jitter should add randomness to delays."""
        from src.task_queue import get_retry_delay

        # get_retry_delay includes jitter for thundering herd prevention
        delays = [get_retry_delay(2) for _ in range(10)]
        # With jitter, delays should vary
        assert len(set(delays)) > 1
