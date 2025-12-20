# Best Practices Analysis

This document compares our implementation against industry best practices and identifies areas for improvement.

---

## What We Got Right ✓

### 1. Circuit Breaker Pattern
Our implementation follows the standard three-state model from Michael Nygard's "Release It!":

```
CLOSED → (failures exceed threshold) → OPEN
OPEN → (timeout expires) → HALF_OPEN
HALF_OPEN → (success) → CLOSED
HALF_OPEN → (failure) → OPEN
```

**Best Practice Alignment:**
- ✓ State machine with CLOSED/OPEN/HALF_OPEN states
- ✓ Configurable failure threshold
- ✓ Configurable timeout duration
- ✓ Success threshold for recovery (2 successes to close)
- ✓ Thread-safe with asyncio.Lock

**Reference:** [aiobreaker](https://github.com/arlyon/aiobreaker), [purgatory](https://github.com/mardiros/purgatory)

### 2. Exponential Backoff with Jitter

```python
delay = base_delay * (2 ** retry_count)  # Exponential
delay = delay * (0.5 + random())          # Jitter (50-150%)
delay = min(delay, max_delay)             # Cap
```

**Best Practice Alignment:**
- ✓ Exponential growth prevents rapid retries
- ✓ Jitter prevents "thundering herd" problem
- ✓ Maximum delay cap prevents infinite waits
- ✓ Configurable base delay and growth factor

**Reference:** AWS best practices, Google Cloud retry documentation

### 3. Error Classification

```python
class RetryableError(Exception):
    """Temporary - will retry (network, rate limit, timeout)"""

class PermanentError(Exception):
    """Permanent - goes to DLQ (bad data, auth failure)"""
```

**Best Practice Alignment:**
- ✓ Distinguishes transient vs permanent failures
- ✓ Prevents wasting retries on unrecoverable errors
- ✓ Dead letter queue for manual review

### 4. SQLite Best Practices

```sql
PRAGMA journal_mode=WAL;    -- Write-Ahead Logging
PRAGMA synchronous=NORMAL;  -- Balance durability/speed
PRAGMA foreign_keys=ON;     -- Referential integrity
```

**Best Practice Alignment:**
- ✓ WAL mode for concurrent reads during writes
- ✓ Proper indexing on frequently queried columns
- ✓ Atomic dequeue with UPDATE...RETURNING

**Reference:** [SQLite Worker pattern](https://medium.com/@roshanlamichhane/sqlite-worker-supercharge-your-sqlite-performance-in-multi-threaded-python-applications-01e2e43cc406)

### 5. Worker Pool Pattern

**Best Practice Alignment:**
- ✓ Multiple async workers for parallelism
- ✓ Dynamic scaling (add/remove workers)
- ✓ Graceful shutdown (finish current task)
- ✓ Worker status tracking

**Reference:** [Async Worker Pool Pattern](https://shav.dev/blog/pool-of-workers)

---

## Areas for Improvement

### 1. Exception Exclusion from Circuit Breaker

**Issue:** We trip the circuit breaker on ALL failures, but some exceptions shouldn't count.

**Best Practice:** Distinguish infrastructure failures from application errors.

```python
# SHOULD trip circuit breaker (infrastructure failures):
- ConnectionRefused
- Timeout
- HTTP 500-504

# Should NOT trip circuit breaker (application errors):
- HTTP 400 Bad Request (our fault, not server's)
- HTTP 404 Not Found (file doesn't exist)
- ValidationError (bad data)
```

**Fix:**

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    # NEW: Exceptions that should NOT trip the breaker
    excluded_exceptions: tuple = (
        PermanentError,
        FileNotFoundError,
        ValidationError,
    )
```

### 2. Timeout Wrappers

**Issue:** Not all async operations have explicit timeouts.

**Best Practice:** Always wrap external calls with timeouts.

```python
# Current (no timeout):
result = await uploader.upload_file(path)

# Best Practice:
try:
    result = await asyncio.wait_for(
        uploader.upload_file(path),
        timeout=300  # 5 minutes
    )
except asyncio.TimeoutError:
    raise RetryableError("Upload timeout")
```

### 3. Dedicated SQLite Worker Thread

**Issue:** SQLite has threading limitations. Multiple async workers hitting the same connection can cause contention.

**Best Practice:** Use a dedicated database thread with a queue.

```python
# Consider using: https://pypi.org/project/aiosqlite/
# Or implement SQLite Worker pattern:

class SQLiteWorker:
    """Dedicated thread for all DB operations."""

    def __init__(self, db_path):
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        conn = sqlite3.connect(self._db_path)
        while True:
            operation, args, result_future = self._queue.get()
            try:
                result = operation(conn, *args)
                result_future.set_result(result)
            except Exception as e:
                result_future.set_exception(e)
```

**Note:** aiosqlite already handles this internally, so we're partially covered.

### 4. Use Established Libraries

**Consider replacing custom implementations with battle-tested libraries:**

| Component | Current | Alternative |
|-----------|---------|-------------|
| Circuit Breaker | Custom | [aiobreaker](https://github.com/arlyon/aiobreaker) |
| Task Queue | Custom SQLite | [litequeue](https://github.com/litements/litequeue), [taskiq](https://github.com/taskiq-python/taskiq) |
| Retry Logic | Custom | [tenacity](https://github.com/jd/tenacity) |
| Rate Limiting | Custom | [aiolimiter](https://github.com/mjpieters/aiolimiter) |

**Trade-off:** Custom code is simpler to understand and has no external dependencies, but established libraries are more battle-tested.

### 5. Metrics & Monitoring

**Issue:** Limited observability into system health.

**Best Practice:** Export Prometheus metrics or structured logs.

```python
from prometheus_client import Counter, Gauge, Histogram

# Counters
tasks_processed = Counter('tasks_processed_total', 'Tasks processed', ['status'])
uploads_bytes = Counter('uploads_bytes_total', 'Bytes uploaded')

# Gauges
queue_depth = Gauge('queue_depth', 'Tasks waiting in queue')
circuit_state = Gauge('circuit_breaker_state', 'Circuit breaker state')
active_workers = Gauge('active_workers', 'Workers currently processing')

# Histograms
upload_duration = Histogram('upload_duration_seconds', 'Upload duration')
hash_duration = Histogram('hash_duration_seconds', 'Hash duration')
```

### 6. Structured Logging

**Issue:** Plain text logs are hard to parse.

**Best Practice:** Use structured JSON logging.

```python
import structlog

logger = structlog.get_logger()

# Instead of:
logger.info(f"Uploaded file {path} in {duration}s")

# Use:
logger.info(
    "file_uploaded",
    path=str(path),
    duration_seconds=duration,
    media_id=media_id,
    bytes=file_size,
)
```

### 7. Graceful Degradation

**Issue:** If Google Photos API is completely down, we keep retrying indefinitely.

**Best Practice:** Implement fallback strategies.

```python
class SyncOrchestrator:
    async def handle_prolonged_outage(self):
        """Called when circuit breaker has been open for extended period."""
        # 1. Notify user via dashboard
        await self.notify_outage()

        # 2. Switch to local-only mode (hash but don't upload)
        self.upload_enabled = False

        # 3. Queue uploads for later
        await self.queue_for_later()

        # 4. Periodically check if API recovers
        while not await self.api_health_check():
            await asyncio.sleep(300)  # Check every 5 minutes
```

---

## Recommended Priority

1. **High Priority:**
   - Add exception exclusion to circuit breaker
   - Add timeouts to all async operations
   - Improve error messages for DLQ tasks

2. **Medium Priority:**
   - Add Prometheus metrics
   - Switch to structured logging
   - Consider `tenacity` for retry logic

3. **Low Priority:**
   - Replace custom queue with `litequeue`
   - Add fallback strategies
   - Consider Redis for distributed queue (if multi-node)

---

## References

- [aiobreaker - Async Circuit Breaker](https://github.com/arlyon/aiobreaker)
- [purgatory - Circuit Breaker for Python](https://github.com/mardiros/purgatory)
- [litequeue - SQLite-backed Queue](https://github.com/litements/litequeue)
- [tenacity - Python Retry Library](https://github.com/jd/tenacity)
- [Async Worker Pool Pattern](https://shav.dev/blog/pool-of-workers)
- [SQLite Worker Pattern](https://medium.com/@roshanlamichhane/sqlite-worker-supercharge-your-sqlite-performance-in-multi-threaded-python-applications-01e2e43cc406)
- [Developing Async Task Queue in Python](https://testdriven.io/blog/developing-an-asynchronous-task-queue-in-python/)
