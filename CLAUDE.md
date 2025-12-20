# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Google Photos Sync Tool - A NAS-native application for syncing photos to Google Photos with intelligent duplicate detection. Built with Python 3.11 async/await, FastAPI backend, SQLite database, and HTMX-powered web dashboard.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally with hot reload
uvicorn web.app:app --reload --port 8080

# Run all tests
pytest

# Run single test file
pytest tests/test_scanner.py -v

# Run specific test
pytest tests/test_scanner.py::test_scan_discovers_new_files -v

# Docker deployment
docker-compose up -d

# Windows-specific deployment
docker-compose -f docker-compose.windows.yml up -d
# Access at http://localhost:18080
```

## Architecture

### Three-Phase Sync Process

1. **SCAN**: Fast filesystem traversal using os.scandir()/stat(), skips unchanged files via mtime+size comparison (~50k files/sec)
2. **HASH**: Parallel SHA256 computation with process pool workers for duplicate detection (~500 MB/sec)
3. **UPLOAD**: Rate-limited Google Photos API calls with retry logic, exponential backoff, and circuit breaker pattern

### Core Components

- `src/scanner.py` - Filesystem scanning (stat-based, no file reading)
- `src/hasher.py` - SHA256 streaming with parallel workers
- `src/uploader.py` - Google Photos API client
- `src/sync.py` - SyncOrchestrator coordinating scan/hash/upload phases
- `src/auth.py` - TokenManager for OAuth2 token refresh
- `src/task_queue.py` - Job queue with circuit breaker, retry logic, dead letter queue
- `src/host_manager.py` - Multi-host/mount-point tracking (Windows + NAS support)
- `src/schema.sql` - SQLite schema with WAL mode
- `web/app.py` - FastAPI application (initializes SyncOrchestrator)
- `web/api.py` - REST API endpoints

### Frontend

- `frontend/` - Svelte 4 + Vite + Tailwind CSS
- Builds to `web/static/` served by FastAPI
- Dashboard with Chart.js for metrics visualization

### Key Design Pattern

Uses `source_name + relative_path` for host-independent file identification. The same SQLite database works across Windows (mounted drive Y:/) and NAS (local /volume1/photos) by mapping logical source names to actual paths per host.

## Google Photos API Constraints (Critical Context)

- Cannot enumerate existing library (only items uploaded by this app)
- Cannot read media items not uploaded by this app
- No hash/size fields in API responses
- Videos are NOT deduplicated server-side
- Design relies on local SQLite tracking + Google's server-side dedup as safety net

## Error Handling Patterns

- `RetryableError` vs `PermanentError` distinction in task_queue.py
- Circuit breaker (CLOSED/OPEN/HALF_OPEN states)
- Exponential backoff with jitter to prevent thundering herd
- Dead letter queue for failed uploads requiring manual review

## Testing

Uses pytest with pytest-asyncio. Test fixtures in `tests/conftest.py` provide:
- Async fixtures for async/await code
- Temporary directories for file operations
- Mock Google Photos API with deduplication simulation
- Sample file structures for realistic scenarios

## Environment Variables

- `TZ` - Timezone (default: UTC, set to Australia/Perth for this project)
- `LOG_LEVEL` - Logging verbosity (default: INFO)
- `CONFIG_DIR` - OAuth credentials directory (default: /config)
- `DATA_DIR` - SQLite database directory (default: /data)
- `PHOTOS_DIR` - Source photos root (default: /photos)

## Development Status (2025-12-20)

### Working
- Full sync pipeline: SCAN → HASH → UPLOAD
- Dashboard with stats, active batch progress, chart
- Files page with pagination
- Settings page with source directory management
- Google Photos upload with token refresh
- All SQL queries use parameterized queries (no SQL injection)

### Known Limitations
- Docker Desktop on Windows cannot mount network drives (Y:\)
- Use `./test_photos` for local testing or run container on NAS

### Port Configuration
- Container internal: 8080
- Host mapped: **18080** (access at http://localhost:18080)

## NAS Deployment

See `CLAUDE.local.md` for host-specific deployment info (not committed to git).

General notes:
- Use Windows OpenSSH (`C:\Windows\System32\OpenSSH\ssh.exe`), not Git's SSH
- Container runs on port 18080 externally

## MCP Servers

- **context7** - Use for up-to-date library documentation lookup
  - Add "use context7" to prompts for library docs
  - Example: "How do I use aiosqlite transactions? use context7"
