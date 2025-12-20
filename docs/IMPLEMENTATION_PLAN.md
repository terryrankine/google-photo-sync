# Implementation Plan

## Overview

A NAS-native Google Photos sync tool with web dashboard, batch processing, and intelligent duplicate detection.

---

## Phase 1: Core Engine

### 1.1 Database Layer (`src/db.py`)

```python
# SQLite wrapper with connection pooling
# All schema from RESEARCH.md
# Key methods:
- get_file(filepath) -> FileRecord
- get_file_by_hash(sha256) -> FileRecord
- upsert_file(filepath, mtime, size, sha256, media_id, status)
- create_batch() -> batch_id
- update_batch_stats(batch_id, stats)
- get_pending_files(batch_id) -> List[FileRecord]
- record_stat(stat_type, count, bytes)
```

### 1.2 Scanner (`src/scanner.py`)

```python
# Filesystem scanner
# Uses os.scandir() for speed
# Filters by extension (.jpg, .jpeg, .png, .heic, .mp4, .mov, etc.)
# Compares mtime+size against DB
# Outputs: List of files needing hash, List of unchanged files

async def scan_directory(path: Path, recursive: bool = True) -> ScanResult:
    ...
```

### 1.3 Hasher (`src/hasher.py`)

```python
# SHA256 computation with streaming (memory efficient)
# Parallel processing with ProcessPoolExecutor
# Progress callbacks for UI updates

async def hash_files(files: List[Path], workers: int = 4) -> Dict[Path, str]:
    ...
```

### 1.4 Uploader (`src/uploader.py`)

```python
# Google Photos API client wrapper
# Handles auth, token refresh
# Batch uploads where possible
# Retry logic with exponential backoff
# Rate limiting

class GooglePhotosUploader:
    async def authenticate(self, credentials_path: Path)
    async def upload_file(self, filepath: Path) -> str  # returns media_id
    async def upload_batch(self, files: List[Path]) -> Dict[Path, str]
```

### 1.5 Orchestrator (`src/sync.py`)

```python
# Coordinates scan -> hash -> upload pipeline
# Manages batches
# Emits events for UI updates

class SyncOrchestrator:
    async def run_sync(self, source_dirs: List[Path]) -> BatchResult:
        batch = self.db.create_batch()

        # Phase 1: Scan
        scan_result = await self.scanner.scan(source_dirs)
        self.db.update_batch(batch, files_scanned=scan_result.total)

        # Phase 2: Hash
        hashes = await self.hasher.hash_files(scan_result.needs_hash)
        self.db.update_batch(batch, files_hashed=len(hashes))

        # Phase 3: Upload
        for file, hash in hashes.items():
            if self.db.hash_already_uploaded(hash):
                self.db.mark_uploaded(file, hash)
                continue
            media_id = await self.uploader.upload(file)
            self.db.mark_uploaded(file, hash, media_id)

        return batch
```

---

## Phase 2: Task/Batch System

### 2.1 Batch Manager (`src/batch.py`)

```python
class BatchManager:
    """Manages sync batches with pause/resume/cancel"""

    def create_batch(self, source_dirs: List[Path]) -> Batch
    def pause_batch(self, batch_id: int)
    def resume_batch(self, batch_id: int)
    def cancel_batch(self, batch_id: int)
    def get_batch_status(self, batch_id: int) -> BatchStatus
    def list_batches(self, limit: int = 50) -> List[Batch]
```

### 2.2 Task Queue (`src/tasks.py`)

```python
# Simple SQLite-backed task queue
# Supports priorities
# Handles failures with retry

class TaskQueue:
    def enqueue(self, task_type: str, payload: dict, priority: int = 0)
    def dequeue(self, task_type: str) -> Task
    def complete(self, task_id: int, result: dict)
    def fail(self, task_id: int, error: str, retry: bool = True)
```

### 2.3 Background Worker (`src/worker.py`)

```python
# Runs in separate thread/process
# Processes tasks from queue
# Reports progress via DB

class SyncWorker:
    async def run_forever(self):
        while True:
            task = self.queue.dequeue()
            if task:
                await self.process(task)
            else:
                await asyncio.sleep(1)
```

---

## Phase 3: Web Dashboard

### 3.1 API Routes (`web/api.py`)

```python
from fastapi import FastAPI

app = FastAPI()

# Status
@app.get("/api/status")
async def get_status() -> SystemStatus

# Batches
@app.get("/api/batches")
async def list_batches(limit: int = 50) -> List[Batch]

@app.post("/api/batches")
async def create_batch(source_dirs: List[str]) -> Batch

@app.get("/api/batches/{id}")
async def get_batch(id: int) -> BatchDetail

@app.post("/api/batches/{id}/pause")
@app.post("/api/batches/{id}/resume")
@app.post("/api/batches/{id}/cancel")

# Stats
@app.get("/api/stats/overview")
async def get_overview() -> OverviewStats

@app.get("/api/stats/daily")
async def get_daily_stats(days: int = 7) -> List[DailyStat]

# Config
@app.get("/api/config")
async def get_config() -> Config

@app.put("/api/config")
async def update_config(config: Config) -> Config

# Files
@app.get("/api/files")
async def list_files(status: str = None, limit: int = 100) -> List[FileRecord]

@app.get("/api/files/errors")
async def list_errors(limit: int = 100) -> List[FileError]
```

### 3.2 Dashboard Pages

#### Home / Overview (`web/templates/index.html`)
```
┌─────────────────────────────────────────────────────────────┐
│  Google Photos Sync                              [Settings] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │   Status    │ │   Files     │ │  Database   │           │
│  │   ● IDLE    │ │   142,847   │ │   48.2 MB   │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                             │
│  Last 7 Days                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ████                                               │   │
│  │  ████ ██                                            │   │
│  │  ████ ████ ██                                       │   │
│  │  ████ ████ ████ ██     ██                           │   │
│  │  Mon  Tue  Wed  Thu Fri Sat Sun                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Recent Activity                                            │
│  ├─ Uploaded 847 files (2.3 GB)              2 hours ago   │
│  ├─ Scanned /photos/2024 - 12,421 files      3 hours ago   │
│  ├─ Batch #42 completed                       Yesterday    │
│  └─ ...                                                     │
│                                                             │
│  [Start New Sync]                                           │
└─────────────────────────────────────────────────────────────┘
```

#### Stats Page (`web/templates/stats.html`)
```
┌─────────────────────────────────────────────────────────────┐
│  Statistics                                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Totals                                                     │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│  │   Scanned   │   Hashed    │  Uploaded   │   Errors    │ │
│  │   284,721   │   284,721   │   142,847   │      23     │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
│                                                             │
│  Data Movement (Last 7 Days)                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Date       │ Reads    │ Writes   │ Data In/Out    │   │
│  │─────────────┼──────────┼──────────┼────────────────│   │
│  │  Dec 20     │ 12,421   │ 847      │ 2.3 GB ↑       │   │
│  │  Dec 19     │ 8,234    │ 1,203    │ 4.1 GB ↑       │   │
│  │  Dec 18     │ 0        │ 0        │ 0              │   │
│  │  Dec 17     │ 45,221   │ 12,847   │ 34.2 GB ↑      │   │
│  │  ...        │ ...      │ ...      │ ...            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Database                                                   │
│  ├─ Hash DB Size: 48.2 MB                                  │
│  ├─ Total Records: 284,721                                 │
│  ├─ Unique Hashes: 142,847                                 │
│  └─ Duplicate Files Detected: 141,874                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Batches Page (`web/templates/batches.html`)
```
┌─────────────────────────────────────────────────────────────┐
│  Batches                                      [New Batch]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Active Batch: #47                                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Status: UPLOADING                                   │   │
│  │  Progress: ████████████░░░░░░░░ 62%                 │   │
│  │  Files: 847 / 1,362                                  │   │
│  │  Speed: 12.4 MB/s                                    │   │
│  │  ETA: 14 minutes                                     │   │
│  │                                                       │   │
│  │  [Pause]  [Cancel]                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  History                                                    │
│  ┌────┬────────────┬──────────┬──────────┬────────────┐   │
│  │ ID │ Started    │ Files    │ Status   │ Duration   │   │
│  ├────┼────────────┼──────────┼──────────┼────────────│   │
│  │ 46 │ Dec 19 2pm │ 12,847   │ ✓ Done   │ 2h 14m     │   │
│  │ 45 │ Dec 17 9am │ 45,221   │ ✓ Done   │ 8h 42m     │   │
│  │ 44 │ Dec 15 3pm │ 892      │ ✗ Failed │ 12m        │   │
│  │ ...│ ...        │ ...      │ ...      │ ...        │   │
│  └────┴────────────┴──────────┴──────────┴────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Config Page (`web/templates/config.html`)
```
┌─────────────────────────────────────────────────────────────┐
│  Configuration                                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Google API Setup                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Status: ✓ Authenticated                             │   │
│  │  Account: photos@gmail.com                           │   │
│  │  Token Expires: Dec 25, 2024                         │   │
│  │                                                       │   │
│  │  [Re-authenticate]  [Revoke Access]                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Setup Instructions                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  1. Go to Google Cloud Console                       │   │
│  │     https://console.cloud.google.com/                │   │
│  │                                                       │   │
│  │  2. Create a new project (or select existing)        │   │
│  │                                                       │   │
│  │  3. Enable "Photos Library API"                      │   │
│  │     APIs & Services > Library > Search "Photos"      │   │
│  │                                                       │   │
│  │  4. Create OAuth 2.0 credentials                     │   │
│  │     APIs & Services > Credentials > Create           │   │
│  │     > OAuth client ID > Desktop app                  │   │
│  │                                                       │   │
│  │  5. Download credentials.json                        │   │
│  │                                                       │   │
│  │  6. Upload below or place in /config/credentials.json│   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Upload Credentials                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  [Choose File] credentials.json                      │   │
│  │  [Upload & Authenticate]                             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Source Directories                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  /photos/camera-roll                          [X]    │   │
│  │  /photos/archive                              [X]    │   │
│  │  /photos/imports                              [X]    │   │
│  │  [+ Add Directory]                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Sync Settings                                              │
│  ├─ Parallel uploads: [4] ▼                                │
│  ├─ Hash workers: [4] ▼                                    │
│  ├─ File extensions: jpg,jpeg,png,heic,mp4,mov             │
│  ├─ Ignore patterns: .thumbnails, @eaDir, .DS_Store        │
│  └─ Auto-sync schedule: [Disabled] ▼                       │
│                                                             │
│  [Save Configuration]                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 4: Docker Packaging

### 4.1 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY web/ ./web/

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 4.2 docker-compose.yml

```yaml
version: '3.8'

services:
  gphoto-sync:
    build: .
    container_name: gphoto-sync
    ports:
      - "8080:8080"
    volumes:
      - ./config:/config           # Credentials & config
      - ./data:/data               # SQLite database
      - /volume1/photos:/photos:ro # Photo directories (read-only)
    environment:
      - TZ=America/New_York
    restart: unless-stopped
```

---

## File Structure

```
google-photo-container/
├── docs/
│   ├── RESEARCH.md
│   └── IMPLEMENTATION_PLAN.md
├── src/
│   ├── __init__.py
│   ├── db.py              # Database layer
│   ├── scanner.py         # Filesystem scanner
│   ├── hasher.py          # SHA256 computation
│   ├── uploader.py        # Google Photos API client
│   ├── sync.py            # Orchestrator
│   ├── batch.py           # Batch manager
│   ├── tasks.py           # Task queue
│   └── worker.py          # Background worker
├── web/
│   ├── __init__.py
│   ├── app.py             # FastAPI application
│   ├── api.py             # API routes
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── stats.html
│       ├── batches.html
│       └── config.html
├── tasks/
│   └── .gitkeep
├── config/
│   └── .gitkeep
├── data/
│   └── .gitkeep
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Implementation Order

1. **Week 1: Core Engine**
   - [ ] Database schema + migrations
   - [ ] Scanner with mtime/size caching
   - [ ] Parallel hasher
   - [ ] Basic uploader (no batching yet)
   - [ ] CLI for testing

2. **Week 2: Task System**
   - [ ] Batch manager
   - [ ] Task queue
   - [ ] Background worker
   - [ ] Pause/resume/cancel

3. **Week 3: Web Dashboard**
   - [ ] FastAPI setup
   - [ ] API endpoints
   - [ ] Dashboard pages (HTMX)
   - [ ] Config page with auth flow

4. **Week 4: Polish**
   - [ ] Docker packaging
   - [ ] Error handling
   - [ ] Logging
   - [ ] Documentation
   - [ ] Testing on NAS

---

## Dependencies

```
# requirements.txt
fastapi>=0.104.0
uvicorn>=0.24.0
aiohttp>=3.9.0
aiosqlite>=0.19.0
google-photos-library-api>=0.10.0
python-multipart>=0.0.6
jinja2>=3.1.2
pydantic>=2.5.0
```
