# Google Photos Sync Tool - Research

## Problem Statement

Google Drive's photo sync rescans the entire archive every time, which is unacceptably slow for large photo libraries (100k+ photos). We need a tool that:
1. Runs directly on NAS
2. Detects already-synced files instantly (no rescan)
3. Only uploads new/changed content
4. Provides visibility into sync status

---

## Google Photos API - Key Findings

### API Restrictions (March 2025)

Google severely restricted the Photos Library API effective March 31, 2025:

- **Read Limitation**: Apps can only access media items *they uploaded* - cannot enumerate existing library
- **Removed Scopes**: `photoslibrary.readonly`, `photoslibrary.sharing`, `photoslibrary` scopes removed
- **No Hash Field**: API does not expose file hashes/checksums in mediaItem responses
- **No Size Field**: API does not return file size, preventing proper sync comparisons

### MediaItem Response Fields

```json
{
  "id": "persistent-media-item-id",
  "description": "user description",
  "productUrl": "https://photos.google.com/...",
  "baseUrl": "https://...",
  "mimeType": "image/jpeg",
  "filename": "IMG_1234.jpg",
  "mediaMetadata": {
    "creationTime": "2024-01-15T10:30:00Z",
    "width": "4032",
    "height": "3024",
    "photo": {
      "cameraMake": "Apple",
      "cameraModel": "iPhone 15 Pro",
      "focalLength": 6.86,
      "apertureFNumber": 1.78,
      "isoEquivalent": 100
    }
  }
}
```

**Notable Absences**: No hash, no file size, no upload timestamp

### Deduplication Behavior

Google Photos **does** deduplicate at upload time:

1. **Hash-based**: Same binary bytes = same media_id returned
2. **Filename Retention**: Keeps filename from FIRST upload (causes sync tool confusion)
3. **Photos Only**: Videos are NOT deduplicated
4. **Silent**: No error returned, just returns existing media_id

**Source**: rclone documentation confirms:
> "If you upload the same image twice then Google Photos will deduplicate it. However it will retain the filename from the first upload which may confuse rclone."

### Upload Quotas & Limits

- All API uploads count against storage quota (no "high quality" option via API)
- Uploads stored at "original quality"
- Rate limits apply (undocumented exact limits)
- Batch uploads supported via `batchCreate` endpoint

---

## Existing Tools Analysis

### rclone

**Pros**:
- Mature, well-tested
- Supports Google Photos backend

**Cons**:
- Cannot use dates for sync (API limitation)
- Only does existence checks (no size comparison)
- Rescans entire library due to filename mismatch after dedup
- Confused by Google's filename retention behavior

### gphotos-uploader

**Pros**:
- Tracks uploads in local database
- Won't re-upload already synced files

**Cons**:
- Limited maintenance
- No web UI
- No batch statistics

### gphotos-sync

**Pros**:
- Active development (gilesknap/gphotos-sync)
- Good documentation

**Cons**:
- Download-only ("read only and never modifies your cloud library")
- Not suitable for upload use case

### google-photos-library-api (Python)

**Pros**:
- Clean async Python client
- Supports uploads (unlike official client)
- Good for building custom solution

**Cons**:
- Just a library, not a complete tool

---

## Proposed Architecture

### Core Insight

We cannot query "does this file exist in Google Photos" due to API limitations. But we CAN:

1. Track what WE have uploaded in a local database
2. Use file metadata (mtime + size) to skip unchanged files
3. Use content hash to detect duplicates across different paths
4. Rely on Google's server-side dedup for edge cases

### Database Schema

```sql
-- Files we're tracking
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    filepath TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT,
    media_id TEXT,  -- Google Photos media item ID
    uploaded_at TIMESTAMP,
    status TEXT DEFAULT 'pending'  -- pending, uploading, uploaded, error
);

-- Index for fast lookups
CREATE INDEX idx_files_hash ON files(sha256);
CREATE INDEX idx_files_status ON files(status);
CREATE INDEX idx_files_mtime ON files(mtime);

-- Upload batches
CREATE TABLE batches (
    id INTEGER PRIMARY KEY,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    files_scanned INTEGER DEFAULT 0,
    files_hashed INTEGER DEFAULT 0,
    files_uploaded INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    files_errored INTEGER DEFAULT 0,
    bytes_uploaded INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'  -- running, completed, failed, cancelled
);

-- Individual upload tasks within a batch
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER REFERENCES batches(id),
    file_id INTEGER REFERENCES files(id),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'pending',  -- pending, running, success, error
    error_message TEXT,
    bytes_transferred INTEGER DEFAULT 0
);

-- Statistics for dashboard
CREATE TABLE stats (
    id INTEGER PRIMARY KEY,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stat_type TEXT NOT NULL,  -- scan, hash, upload, error
    count INTEGER DEFAULT 0,
    bytes INTEGER DEFAULT 0
);

-- Configuration
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Sync Algorithm

```
SCAN PHASE (fast - filesystem only):
for each file in source_directories:
    stat = os.stat(file)
    db_record = db.get(filepath)

    if db_record and db_record.mtime == stat.mtime and db_record.size == stat.size:
        SKIP  # unchanged, already processed
    else:
        mark_for_hashing(file, stat)

HASH PHASE (CPU bound, parallelizable):
for each file in needs_hashing:
    sha256 = compute_hash(file)

    existing = db.get_by_hash(sha256)
    if existing and existing.media_id:
        # Same content already uploaded from different path
        db.update(file, sha256=sha256, media_id=existing.media_id, status='uploaded')
        SKIP
    else:
        mark_for_upload(file, sha256)

UPLOAD PHASE (network bound):
for each file in needs_upload:
    try:
        media_id = google_photos.upload(file)
        db.update(file, media_id=media_id, status='uploaded')
    except DuplicateError:
        # Google's server-side dedup caught it
        db.update(file, status='uploaded')
    except Error as e:
        db.update(file, status='error', error=str(e))
```

### Performance Characteristics

| Phase | Bottleneck | Speed | Parallelizable |
|-------|------------|-------|----------------|
| Scan | Disk I/O (stat calls) | ~50,000 files/sec | Yes |
| Hash | CPU + Disk I/O | ~500 MB/sec | Yes |
| Upload | Network | Depends on connection | Yes (with limits) |

**First Run** (100k photos, 500GB):
- Scan: ~2 seconds
- Hash: ~17 minutes (at 500MB/sec)
- Upload: Hours/days depending on upload speed

**Subsequent Runs** (nothing changed):
- Scan: ~2 seconds
- Hash: 0 (nothing to hash)
- Upload: 0 (nothing to upload)

---

## Technology Stack

### Backend
- **Python 3.11+**: Async support, good library ecosystem
- **SQLite**: Embedded, no setup, handles millions of rows
- **aiohttp**: Async HTTP for uploads
- **google-photos-library-api**: Clean async client

### Web Dashboard
- **FastAPI**: Modern async Python web framework
- **HTMX**: Simple dynamic updates without SPA complexity
- **Tailwind CSS**: Utility-first styling
- **SQLite**: Same DB as backend

### Deployment
- **Docker**: Container for NAS deployment
- **Docker Compose**: Easy configuration
- **Volume mounts**: For photo directories and config

---

## API Key Setup

### Requirements
1. Google Cloud Console account
2. Project with Photos Library API enabled
3. OAuth 2.0 credentials (Desktop app type)

### Steps
1. Go to https://console.cloud.google.com/
2. Create new project or select existing
3. Enable "Photos Library API"
4. Create OAuth 2.0 Client ID (Desktop application)
5. Download credentials.json
6. Place in config directory
7. Run authentication flow (one-time browser auth)

### Scopes Required
```
https://www.googleapis.com/auth/photoslibrary.appendonly
```

Note: We only need `appendonly` since we're uploading, not reading.

---

## References

- [Google Photos API Reference](https://developers.google.com/photos/library/reference/rest/v1/mediaItems)
- [rclone Google Photos Backend](https://rclone.org/googlephotos/)
- [google-photos-library-api PyPI](https://pypi.org/project/google-photos-library-api/)
- [gphotos-uploader GitHub](https://github.com/pdumoulin/gphotos-uploader)
