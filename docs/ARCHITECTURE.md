# System Architecture

## Overview

Google Photos Sync is a NAS-native tool designed for efficient, incremental photo backup to Google Photos. The architecture prioritizes:

1. **Speed**: Skip unchanged files via mtime+size checks
2. **Reliability**: Retry logic, circuit breakers, dead letter queues
3. **Scalability**: Multi-worker parallel processing
4. **Visibility**: Real-time progress via web dashboard

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Web Dashboard (FastAPI)                        │
│                    http://localhost:18080                                │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Dashboard  │  │   Batches   │  │    Stats    │  │   Config    │    │
│  │   Page      │  │    Page     │  │    Page     │  │    Page     │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         └─────────────────┴─────────────────┴─────────────────┘         │
│                                    │                                     │
│                            REST API (api.py)                            │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Orchestrator (sync.py)                          │
│                                                                         │
│   Coordinates the three-phase sync process:                            │
│   1. Scan → 2. Hash → 3. Upload                                        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│    Scanner      │       │     Hasher      │       │    Uploader     │
│   (scanner.py)  │       │   (hasher.py)   │       │  (uploader.py)  │
│                 │       │                 │       │                 │
│ • os.scandir()  │       │ • SHA256        │       │ • Google API    │
│ • mtime+size    │       │ • Parallel      │       │ • Rate limiting │
│ • Extension     │       │ • Streaming     │       │ • Retry logic   │
│   filtering     │       │                 │       │                 │
└────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │                         │                         │
         └─────────────────────────┴─────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Task Queue (task_queue.py)                       │
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │   Worker 0  │    │   Worker 1  │    │   Worker N  │   WorkerPool   │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                 │
│         └─────────────────┬┴───────────────────┘                       │
│                           │                                             │
│                    ┌──────┴──────┐                                      │
│                    │ TaskQueue   │◄──── Circuit Breaker                 │
│                    │ (SQLite)    │◄──── Retry Config                    │
│                    └─────────────┘                                      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SQLite Database                                  │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  files   │  │ batches  │  │  tasks   │  │  stats   │  │  config  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Task & Batch Processing System

### Conceptual Model

```
                    BATCH (sync operation)
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
      ┌──────────┐   ┌──────────┐   ┌──────────┐
      │  Task 1  │   │  Task 2  │   │  Task N  │    (1000+ tasks per batch)
      │  file_a  │   │  file_b  │   │  file_n  │
      └──────────┘   └──────────┘   └──────────┘
            │              │              │
            └──────────────┼──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  TaskQueue   │
                    │  (SQLite)    │
                    └──────┬───────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
   ┌──────────┐      ┌──────────┐      ┌──────────┐
   │ Worker 0 │      │ Worker 1 │      │ Worker 2 │
   └──────────┘      └──────────┘      └──────────┘
```

### Batch Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                        BATCH STATES                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────┐     ┌──────────┐     ┌─────────┐     ┌─────────┐ │
│   │ PENDING │────▶│ SCANNING │────▶│ HASHING │────▶│UPLOADING│ │
│   └─────────┘     └──────────┘     └─────────┘     └────┬────┘ │
│                                                          │      │
│        ┌─────────────────────────────────────────────────┘      │
│        │                                                        │
│        ▼                                                        │
│   ┌─────────┐                                                   │
│   │COMPLETED│                                                   │
│   └─────────┘                                                   │
│                                                                  │
│   From any state:                                               │
│   ┌────────┐     ┌───────────┐     ┌────────┐                  │
│   │ PAUSED │◄───▶│  RUNNING  │────▶│ FAILED │                  │
│   └────────┘     └───────────┘     └────────┘                  │
│        │                                │                       │
│        └───────────────┬────────────────┘                       │
│                        ▼                                        │
│                  ┌───────────┐                                  │
│                  │ CANCELLED │                                  │
│                  └───────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Task Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                         TASK STATES                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                      ┌─────────┐                                │
│                      │ PENDING │                                │
│                      └────┬────┘                                │
│                           │                                     │
│                           ▼                                     │
│                      ┌─────────┐                                │
│              ┌───────│ RUNNING │───────┐                        │
│              │       └─────────┘       │                        │
│              │                         │                        │
│          Success                    Failure                     │
│              │                         │                        │
│              ▼                         ▼                        │
│        ┌─────────┐              ┌───────────┐                   │
│        │ SUCCESS │              │   RETRY   │◄─────┐            │
│        └─────────┘              └─────┬─────┘      │            │
│                                       │            │            │
│                               ┌───────┴───────┐    │            │
│                               │               │    │            │
│                         retry_count      retry_count            │
│                         < max            >= max                 │
│                               │               │                 │
│                               │               ▼                 │
│                               │         ┌──────────┐            │
│                               └────────▶│   DEAD   │            │
│                              (wait)     │ (DLQ)    │            │
│                                         └──────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Worker Pool Architecture

### How Workers Process Tasks

```python
# Simplified worker loop
class Worker:
    async def run(self):
        while self._running:
            # 1. Check circuit breaker
            if not await circuit_breaker.can_execute():
                await sleep(5)  # Back off when circuit is open
                continue

            # 2. Atomically dequeue a task
            task = await queue.dequeue()  # Thread-safe via SQLite
            if not task:
                await sleep(0.5)  # No work available
                continue

            # 3. Process the task
            try:
                handler = handlers[task.task_type]
                await handler(task)
                await queue.complete(task.id, success=True)
            except RetryableError as e:
                await queue.complete(task.id, success=False, error=str(e))
            except PermanentError as e:
                # Skip retries, go straight to dead letter queue
                await queue.complete(task.id, success=False, error=str(e))
```

### Dequeue Operation (Atomic)

```sql
-- Atomically claim a task (prevents race conditions)
UPDATE tasks
SET status = 'running', started_at = CURRENT_TIMESTAMP
WHERE id = (
    SELECT id FROM tasks
    WHERE status IN ('pending', 'retry')
    AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
    ORDER BY priority DESC, created_at ASC
    LIMIT 1
)
RETURNING *;
```

### Worker Pool Scaling

```
Initial state: 4 workers
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Worker 0│ │Worker 1│ │Worker 2│ │Worker 3│
└────────┘ └────────┘ └────────┘ └────────┘

After scale(6): Add 2 workers
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Worker 0│ │Worker 1│ │Worker 2│ │Worker 3│ │Worker 4│ │Worker 5│
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘

After scale(2): Remove 4 workers (graceful shutdown)
┌────────┐ ┌────────┐
│Worker 0│ │Worker 1│
└────────┘ └────────┘
```

---

## Failure Handling

### Retry Logic with Exponential Backoff

```
Attempt 1: Immediate
Attempt 2: Wait 1s × 2^0 = 1s    (+ jitter: 0.5-1.5s)
Attempt 3: Wait 1s × 2^1 = 2s    (+ jitter: 1-3s)
Attempt 4: Wait 1s × 2^2 = 4s    (+ jitter: 2-6s)
Attempt 5: DEAD LETTER QUEUE

Jitter prevents "thundering herd" when many tasks retry simultaneously.
```

```python
@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0  # Cap at 5 minutes
    exponential_base: float = 2.0
    jitter: bool = True  # Add 50-150% randomness
```

### Circuit Breaker Pattern

Prevents hammering a failing API:

```
                          CLOSED
                       (normal operation)
                             │
                 5 consecutive failures
                             │
                             ▼
                           OPEN
                    (blocking all requests)
                             │
                    60 seconds timeout
                             │
                             ▼
                        HALF-OPEN
                   (allow 1 test request)
                        │         │
                    success     failure
                        │         │
                        ▼         ▼
                     CLOSED      OPEN
```

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5      # Failures to open
    success_threshold: int = 2      # Successes to close (in half-open)
    timeout_seconds: float = 60.0   # How long to stay open
```

### Error Classification

```python
class RetryableError(Exception):
    """Temporary failures - will retry"""
    # HTTP 408 Request Timeout
    # HTTP 429 Too Many Requests (rate limit)
    # HTTP 500-504 Server errors
    # Network timeouts
    # Connection refused

class PermanentError(Exception):
    """Permanent failures - goes to dead letter queue"""
    # HTTP 400 Bad Request
    # HTTP 401 Unauthorized
    # HTTP 403 Forbidden
    # HTTP 404 Not Found
    # File not found locally
    # Invalid file format
```

### Dead Letter Queue (DLQ)

Tasks that exhaust all retries go to DLQ for manual review:

```sql
SELECT * FROM tasks WHERE status = 'dead';

-- Example DLQ entries:
-- id=1234, file_id=567, error="HTTP 403: Quota exceeded"
-- id=1235, file_id=789, error="File corrupted: invalid JPEG header"
```

---

## Data Flow

### Sync Operation Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          SYNC OPERATION                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PHASE 1: SCAN                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│     /photos/                      Database (files table)                │
│        │                                    │                           │
│        ▼                                    ▼                           │
│   ┌─────────┐                        ┌───────────┐                      │
│   │scandir()│───────compare─────────▶│mtime+size │                      │
│   └─────────┘                        └───────────┘                      │
│        │                                    │                           │
│        ▼                                    ▼                           │
│   ┌─────────────────────────────────────────────────────┐               │
│   │         Unchanged files: SKIP (no DB update)        │               │
│   │         New/modified files: → needs_hash list       │               │
│   └─────────────────────────────────────────────────────┘               │
│                                                                          │
│  PHASE 2: HASH                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   needs_hash list                   Database (files table)              │
│        │                                    │                           │
│        ▼                                    ▼                           │
│   ┌─────────────┐                    ┌───────────┐                      │
│   │  SHA256     │───────compare─────▶│ existing  │                      │
│   │(parallel)   │                    │  hashes   │                      │
│   └─────────────┘                    └───────────┘                      │
│        │                                    │                           │
│        ▼                                    ▼                           │
│   ┌─────────────────────────────────────────────────────┐               │
│   │   Hash exists with media_id: SKIP (duplicate)       │               │
│   │   New hash: → needs_upload list                     │               │
│   └─────────────────────────────────────────────────────┘               │
│                                                                          │
│  PHASE 3: UPLOAD                                                        │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   needs_upload list                 Google Photos API                   │
│        │                                    │                           │
│        ▼                                    ▼                           │
│   ┌─────────────┐                    ┌───────────┐                      │
│   │Create Tasks │───────upload──────▶│  Dedup?   │                      │
│   │(1000/batch) │                    │           │                      │
│   └─────────────┘                    └───────────┘                      │
│        │                                    │                           │
│        ▼                                    ▼                           │
│   ┌─────────────────────────────────────────────────────┐               │
│   │   Returns media_id → store in database              │               │
│   │   (Google dedupes server-side, returns existing ID) │               │
│   └─────────────────────────────────────────────────────┘               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### First Run vs Subsequent Runs

```
FIRST RUN (100,000 photos, 500GB):
┌─────────────────────────────────────────────────────────────────┐
│ Phase     │ Files      │ Time        │ Network     │ Notes     │
├───────────┼────────────┼─────────────┼─────────────┼───────────┤
│ Scan      │ 100,000    │ ~2 seconds  │ None        │ stat()    │
│ Hash      │ 100,000    │ ~17 minutes │ None        │ 500MB/s   │
│ Upload    │ 100,000    │ Hours/days  │ 500GB ↑     │ API calls │
└───────────┴────────────┴─────────────┴─────────────┴───────────┘

SUBSEQUENT RUNS (nothing changed):
┌─────────────────────────────────────────────────────────────────┐
│ Phase     │ Files      │ Time        │ Network     │ Notes     │
├───────────┼────────────┼─────────────┼─────────────┼───────────┤
│ Scan      │ 100,000    │ ~2 seconds  │ None        │ stat()    │
│ Hash      │ 0          │ 0           │ None        │ All skip  │
│ Upload    │ 0          │ 0           │ None        │ All skip  │
└───────────┴────────────┴─────────────┴─────────────┴───────────┘
Total time: ~2 seconds for "nothing to do" case
```

---

## Database Schema

### Entity Relationship

```
┌─────────────────┐       ┌─────────────────┐
│     batches     │       │      files      │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ source_dirs     │       │ filepath        │
│ started_at      │       │ filename        │
│ completed_at    │       │ mtime           │
│ status          │       │ size            │
│ files_scanned   │       │ sha256          │
│ files_uploaded  │       │ media_id        │◄────┐
│ bytes_uploaded  │       │ status          │     │
│ progress_percent│       │ uploaded_at     │     │
│ current_phase   │       └─────────────────┘     │
└────────┬────────┘                               │
         │                                        │
         │ 1:N                                    │
         │                                        │
         ▼                                        │
┌─────────────────┐                               │
│      tasks      │                               │
├─────────────────┤                               │
│ id (PK)         │                               │
│ batch_id (FK)───┼───────────────────────────────┘
│ file_id (FK)    │
│ task_type       │
│ priority        │
│ status          │
│ retry_count     │
│ max_retries     │
│ error_message   │
│ next_retry_at   │
│ started_at      │
│ completed_at    │
└─────────────────┘

┌─────────────────┐       ┌─────────────────┐
│      stats      │       │     config      │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ key (PK)        │
│ date            │       │ value           │
│ files_scanned   │       │ description     │
│ files_uploaded  │       │ updated_at      │
│ bytes_uploaded  │       └─────────────────┘
│ bytes_read      │
└─────────────────┘
```

---

## Component Interactions

### Upload Task Handler Example

```python
async def handle_upload_task(task: Task):
    """Handler registered with WorkerPool for UPLOAD tasks."""

    # 1. Get file info from database
    file_info = await db.get_file(task.file_id)

    # 2. Validate file still exists
    if not file_info.path.exists():
        raise PermanentError(f"File not found: {file_info.path}")

    # 3. Check if content hash already uploaded
    existing = await db.get_by_hash(file_info.sha256)
    if existing and existing.media_id:
        # Duplicate detected - copy media_id, skip upload
        await db.update_file(task.file_id, media_id=existing.media_id)
        return

    # 4. Upload to Google Photos
    result = await uploader.upload_file(file_info.path)

    if result.success:
        # 5. Store media_id in database
        await db.update_file(
            task.file_id,
            media_id=result.media_id,
            status='uploaded',
            uploaded_at=datetime.now()
        )

        # 6. Update batch statistics
        await db.increment_batch_stats(
            task.batch_id,
            files_uploaded=1,
            bytes_uploaded=file_info.size
        )
    else:
        raise RetryableError(result.error)
```

### System Startup Sequence

```
1. FastAPI app starts (web/app.py)
   │
   ├─► Initialize SQLite database
   │   └─► Run schema.sql if first run
   │
   ├─► Create TaskQueue instance
   │   └─► Attach CircuitBreaker
   │
   ├─► Create WorkerPool(num_workers=4)
   │   └─► Register handlers: {HASH: hash_handler, UPLOAD: upload_handler}
   │
   ├─► Start WorkerPool
   │   └─► Spawn Worker 0, 1, 2, 3 as asyncio tasks
   │
   └─► Start serving HTTP on port 8080
```

---

## Configuration

### Environment Variables

```bash
# Paths
CONFIG_DIR=/config        # OAuth credentials
DATA_DIR=/data           # SQLite database
PHOTOS_DIR=/photos       # Photo source directory

# Logging
LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR

# Workers
PARALLEL_UPLOADS=4       # Concurrent upload workers
PARALLEL_HASHERS=4       # Concurrent hash workers

# Timezone
TZ=America/New_York
```

### Database Config Table

```sql
INSERT INTO config (key, value, description) VALUES
('source_dirs', '[]', 'JSON array of directories to sync'),
('file_extensions', 'jpg,jpeg,png,heic,mp4,mov', 'Extensions to sync'),
('ignore_patterns', '.thumbnails,@eaDir', 'Patterns to ignore'),
('parallel_uploads', '4', 'Concurrent uploads'),
('parallel_hashers', '4', 'Concurrent hashers'),
('auto_sync_enabled', 'false', 'Enable scheduled sync'),
('auto_sync_cron', '0 2 * * *', 'Cron expression');
```

---

## Performance Characteristics

### Bottlenecks by Phase

| Phase  | Bottleneck | Optimization |
|--------|------------|--------------|
| Scan   | Disk I/O (stat) | os.scandir() batching |
| Hash   | CPU + Disk I/O | ProcessPoolExecutor |
| Upload | Network | Concurrent workers |

### Scaling Recommendations

| Photo Count | Hash Workers | Upload Workers | Memory |
|-------------|--------------|----------------|--------|
| < 10,000    | 2            | 2              | 256MB  |
| 10K - 100K  | 4            | 4              | 512MB  |
| 100K - 1M   | 8            | 4              | 1GB    |
| > 1M        | 8            | 8              | 2GB    |

---

## Multi-Host Support

### Problem
The same photo library may be accessed from multiple machines:
- Windows dev machine with NAS mounted as `Y:\`
- Directly on the NAS with paths like `/volume1/photos`

Without multi-host support, files would appear as different paths and get re-processed.

### Solution: Host-Independent Paths

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           MULTI-HOST ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Windows Machine                        NAS (Synology)                  │
│  hostname: DESKTOP-ABC123               hostname: synology-nas          │
│                                                                          │
│  path_mapping:                          path_mapping:                   │
│    source: 'photos'                       source: 'photos'              │
│    local:  'Y:\photos'                    local:  '/volume1/photos'     │
│                                                                          │
│  Scans file:                            Scans file:                     │
│  Y:\photos\2024\01\IMG_001.jpg          /volume1/photos/2024/01/IMG.jpg │
│       │                                        │                        │
│       └──────────────┬─────────────────────────┘                        │
│                      │                                                   │
│                      ▼                                                   │
│            ┌─────────────────────┐                                      │
│            │   Database Entry    │                                      │
│            ├─────────────────────┤                                      │
│            │ source: 'photos'    │                                      │
│            │ relative: '2024/01/ │                                      │
│            │   IMG_001.jpg'      │◄─── Same entry, different hosts     │
│            │ sha256: 'abc123...' │                                      │
│            │ media_id: 'xyz789'  │                                      │
│            └─────────────────────┘                                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Database Schema for Multi-Host

```sql
-- Registered hosts
CREATE TABLE hosts (
    id INTEGER PRIMARY KEY,
    hostname TEXT UNIQUE,           -- 'DESKTOP-ABC123'
    description TEXT,               -- 'Windows Dev Machine'
    last_seen_at TIMESTAMP
);

-- Path mappings per host
CREATE TABLE path_mappings (
    host_id INTEGER,
    source_name TEXT,               -- 'photos' (logical name)
    local_path TEXT,                -- 'Z:\photos' or '/volume1/photos'
    UNIQUE(host_id, source_name)
);

-- Files use host-independent keys
CREATE TABLE files (
    source_name TEXT,               -- 'photos'
    relative_path TEXT,             -- '2024/01/IMG_001.jpg' (forward slashes)
    sha256 TEXT,                    -- Content hash
    media_id TEXT,                  -- Google Photos ID
    scanned_by_host_id INTEGER,     -- Which host last scanned
    uploaded_by_host_id INTEGER,    -- Which host uploaded
    UNIQUE(source_name, relative_path)
);
```

### Path Conversion

```python
# On Windows (NAS mounted as Y:)
host_manager.add_path_mapping('photos', 'Y:\\photos')
source, rel = host_manager.to_relative_path('Y:\\photos\\2024\\01\\IMG.jpg')
# Returns: ('photos', '2024/01/IMG.jpg')

# On NAS (direct path)
host_manager.add_path_mapping('photos', '/volume1/photos')
source, rel = host_manager.to_relative_path('/volume1/photos/2024/01/IMG.jpg')
# Returns: ('photos', '2024/01/IMG.jpg')  # Same!

# Convert back to local path on any host
local = host_manager.to_local_path('photos', '2024/01/IMG.jpg')
# Windows: Path('Y:/photos/2024/01/IMG.jpg')
# NAS:     Path('/volume1/photos/2024/01/IMG.jpg')
```

### Workflow

1. **First run on Windows:**
   - Register host `DESKTOP-ABC123`
   - Add mapping: `photos` → `Y:\photos`
   - Scan, hash, upload → files stored with `relative_path`

2. **Later run on NAS:**
   - Register host `synology-nas`
   - Add mapping: `photos` → `/volume1/photos`
   - Scan → finds same `relative_path` entries
   - Already uploaded? Skip!

### Shared Database Options

1. **SQLite on NAS**: Mount the same DB file from both hosts
2. **SQLite with sync**: Use Syncthing/rsync to keep DB in sync
3. **Future: PostgreSQL**: For true multi-node concurrent access

---

## Security Considerations

1. **OAuth Tokens**: Stored in `/config/token.json`, never logged
2. **Read-only Photo Mounts**: Default Docker mount is `:ro`
3. **No Secrets in Logs**: Error messages sanitized
4. **Rate Limiting**: Prevents API abuse, protects quota
5. **Input Validation**: File paths validated before access

---

## Monitoring & Observability

### Key Metrics

- `queue.pending_count` - Tasks waiting to process
- `queue.running_count` - Tasks currently processing
- `queue.dead_count` - Tasks in dead letter queue
- `circuit_breaker.state` - CLOSED/OPEN/HALF_OPEN
- `worker.active_count` - Workers currently processing
- `upload.bytes_per_second` - Upload throughput
- `batch.progress_percent` - Current batch completion

### Health Check

```bash
curl http://localhost:18080/health
# {"status": "healthy"}

curl http://localhost:18080/api/status
# {"status": "idle"} or {"status": "uploading", "batch_id": 42, "progress": 67.5}
```

---

## Future Enhancements

1. **WebSocket** for real-time progress updates
2. **Redis** for distributed task queue (multi-node)
3. **S3/GCS** backup as secondary destination
4. **Face detection** for smart album organization
5. **Incremental backup** with file system watches (inotify)
