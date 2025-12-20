# Google Photos Sync Tool

A NAS-native tool for syncing photos to Google Photos with intelligent duplicate detection and a web dashboard.

## Features

- **Fast incremental sync**: Uses file mtime + size to skip unchanged files (no rehashing)
- **Content-based deduplication**: SHA256 hashing detects duplicates across directories
- **Server-side dedup**: Leverages Google Photos' built-in duplicate detection
- **Web dashboard**: Real-time progress, statistics, and configuration
- **Batch management**: Pause, resume, cancel sync operations
- **Docker-ready**: Easy deployment on Synology, TrueNAS, or any NAS

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo-url>
cd google-photo-container

# Create directories
mkdir -p config data
```

### 2. Set Up Google API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable "Photos Library API"
4. Create OAuth 2.0 credentials (Desktop app)
5. Download `credentials.json` to `./config/`

### 3. Configure Photo Directories

Edit `docker-compose.yml` to mount your photo directories:

```yaml
volumes:
  - ./config:/config
  - ./data:/data
  - /path/to/your/photos:/photos:ro
```

### 4. Run

```bash
docker-compose up -d
```

Open http://your-nas-ip:8080

### 5. Authenticate

1. Go to Settings in the web UI
2. Upload `credentials.json` if not already in `/config`
3. Click "Authenticate" and follow the OAuth flow

## How It Works

### The Problem

Google Drive's photo sync rescans your entire library every time, which is painfully slow for large collections.

### The Solution

```
1. SCAN: stat() each file → compare mtime+size with database
   └─ Unchanged? SKIP (microseconds per file)

2. HASH: Compute SHA256 for new/changed files
   └─ Hash already uploaded? SKIP (no network)

3. UPLOAD: Send to Google Photos
   └─ Google dedupes server-side (won't create duplicates)
```

### First Run

- Uploads everything (Google dedupes on their end)
- Populates local database with file metadata and hashes
- Takes time proportional to your library size

### Subsequent Runs

- Only stat() calls for unchanged files
- Only hash+upload for new/modified files
- Typically completes in seconds for "nothing changed" case

## Architecture

```
google-photo-container/
├── src/
│   ├── db.py          # SQLite database layer
│   ├── scanner.py     # Filesystem scanner
│   ├── hasher.py      # SHA256 computation (parallel)
│   ├── uploader.py    # Google Photos API client
│   ├── sync.py        # Orchestrator
│   └── worker.py      # Background task processor
├── web/
│   ├── app.py         # FastAPI application
│   ├── api.py         # REST API endpoints
│   └── templates/     # Jinja2 templates (HTMX)
├── config/            # Credentials and settings
├── data/              # SQLite database
└── docker-compose.yml
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TZ` | `UTC` | Timezone |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `CONFIG_DIR` | `/config` | Credentials directory |
| `DATA_DIR` | `/data` | Database directory |

### Web UI Settings

- **Source directories**: Paths to scan for photos
- **File extensions**: Which file types to sync
- **Ignore patterns**: Directories/files to skip
- **Parallel uploads**: Concurrent upload count (1-8)
- **Hash workers**: Parallel hash computations (1-8)

## API

### Endpoints

```
GET  /api/status           # Current sync status
GET  /api/batches          # List all batches
POST /api/batches          # Start new sync
GET  /api/batches/{id}     # Batch details
POST /api/batches/{id}/pause
POST /api/batches/{id}/resume
POST /api/batches/{id}/cancel
GET  /api/stats/overview   # Dashboard stats
GET  /api/stats/daily      # Last 7 days
GET  /api/config           # Current configuration
PUT  /api/config           # Update configuration
```

## Limitations

### Google Photos API (March 2025 Changes)

- Apps can only read media items **they uploaded**
- Cannot enumerate existing library
- Cannot check "does this file exist in my library"
- Workaround: Track uploads locally, rely on server-side dedup

### Videos

Google Photos does **not** deduplicate videos. First run may create duplicates if videos already exist in your library.

## Troubleshooting

### "Token expired" error

Re-authenticate via Settings page.

### Slow first run

Expected. The tool must hash and upload your entire library once. Subsequent runs will be fast.

### Database growing large

Run "Optimize Database" from Settings to vacuum SQLite.

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn web.app:app --reload --port 8080

# Run tests
pytest
```

## License

MIT
