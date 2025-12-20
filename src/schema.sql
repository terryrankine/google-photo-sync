-- Google Photos Sync - Database Schema
-- SQLite 3
-- Supports multi-host operation (Windows + NAS with different mount paths)

PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

-- Hosts table: Track different machines/mount points
-- This allows the same DB to be used from Windows (mounted drive) and NAS (local path)
CREATE TABLE IF NOT EXISTS hosts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hostname TEXT UNIQUE NOT NULL,           -- e.g., 'DESKTOP-ABC123', 'synology-nas'
    description TEXT,                         -- e.g., 'Windows Dev Machine', 'Synology NAS'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Path mappings: How each host sees the same source directory
-- Example:
--   host='DESKTOP-ABC123', source_name='photos', local_path='Y:\photos'
--   host='synology-nas', source_name='photos', local_path='/volume1/photos'
CREATE TABLE IF NOT EXISTS path_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,                -- Logical name: 'photos', 'archive', etc.
    local_path TEXT NOT NULL,                 -- Host-specific path: 'Y:\photos' or '/volume1/photos'
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(host_id, source_name)
);

CREATE INDEX IF NOT EXISTS idx_path_mappings_host ON path_mappings(host_id);

-- Files being tracked for sync
-- Now uses relative_path (host-independent) + source_name for identification
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Host-independent identification
    source_name TEXT NOT NULL,                -- Logical source: 'photos', 'archive'
    relative_path TEXT NOT NULL,              -- Path relative to source root: '2024/01/IMG_001.jpg'
    filename TEXT NOT NULL,

    -- Host-specific info (from last scan)
    scanned_by_host_id INTEGER REFERENCES hosts(id),
    local_path TEXT,                          -- Full path on that host: 'Y:\photos\2024\01\IMG_001.jpg'

    -- File metadata
    extension TEXT,
    mtime REAL NOT NULL,                      -- File modification time (Unix timestamp)
    size INTEGER NOT NULL,                    -- File size in bytes

    -- Content identification
    sha256 TEXT,                              -- Content hash (the real identifier)

    -- Google Photos sync status
    media_id TEXT,                            -- Google Photos media item ID
    uploaded_at TIMESTAMP,                    -- When we uploaded it
    uploaded_by_host_id INTEGER REFERENCES hosts(id),

    -- Status tracking
    status TEXT DEFAULT 'pending',            -- pending, hashing, uploading, uploaded, error, skipped
    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Unique on source + relative path (same file across hosts)
    UNIQUE(source_name, relative_path)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime);
CREATE INDEX IF NOT EXISTS idx_files_source ON files(source_name);
CREATE INDEX IF NOT EXISTS idx_files_media_id ON files(media_id) WHERE media_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_files_host ON files(scanned_by_host_id);

-- Sync jobs (a complete scan+hash+upload run)
-- A job contains multiple work_batches, each with ~1000 files
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    host_id INTEGER REFERENCES hosts(id),     -- Which host ran this job
    source_dirs TEXT NOT NULL,                -- JSON array of source_names
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,

    -- Scan phase stats
    files_scanned INTEGER DEFAULT 0,
    files_unchanged INTEGER DEFAULT 0,        -- Skipped due to mtime+size match
    files_new INTEGER DEFAULT 0,              -- New files found

    -- Hash phase stats
    files_hashed INTEGER DEFAULT 0,
    files_hash_skipped INTEGER DEFAULT 0,     -- Skipped due to hash match (already uploaded)
    bytes_hashed INTEGER DEFAULT 0,

    -- Upload phase stats
    files_uploaded INTEGER DEFAULT 0,
    files_deduplicated INTEGER DEFAULT 0,     -- Google's server-side dedup caught these
    files_skipped INTEGER DEFAULT 0,
    files_errored INTEGER DEFAULT 0,
    bytes_uploaded INTEGER DEFAULT 0,

    -- Overall
    status TEXT DEFAULT 'pending',            -- pending, scanning, hashing, uploading, completed, failed, cancelled, paused
    error_message TEXT,
    progress_percent REAL DEFAULT 0,
    current_phase TEXT,                       -- scan, hash, upload
    current_file TEXT,                        -- Currently processing

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_started ON jobs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_host ON jobs(host_id);

-- Work batches: chunks of ~1000 files for parallel processing
-- Workers claim and process entire batches, not individual files
CREATE TABLE IF NOT EXISTS work_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    batch_type TEXT NOT NULL,                 -- 'hash' or 'upload'
    batch_number INTEGER NOT NULL,            -- 1, 2, 3... within job
    file_count INTEGER DEFAULT 0,             -- Number of files in this batch

    status TEXT DEFAULT 'pending',            -- pending, running, completed, failed
    worker_id INTEGER,                        -- Which worker claimed this batch
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    files_processed INTEGER DEFAULT 0,        -- Progress within batch
    files_succeeded INTEGER DEFAULT 0,
    files_failed INTEGER DEFAULT 0,
    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_work_batches_job ON work_batches(job_id);
CREATE INDEX IF NOT EXISTS idx_work_batches_status ON work_batches(status, batch_type);
CREATE INDEX IF NOT EXISTS idx_work_batches_worker ON work_batches(worker_id) WHERE status = 'running';

-- Individual tasks within a work_batch
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    work_batch_id INTEGER REFERENCES work_batches(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,                  -- hash, upload
    priority INTEGER DEFAULT 0,

    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    status TEXT DEFAULT 'pending',            -- pending, running, success, error, retry, dead
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP,

    -- For upload tasks
    bytes_transferred INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tasks_job ON tasks(job_id);
CREATE INDEX IF NOT EXISTS idx_tasks_work_batch ON tasks(work_batch_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_type_status ON tasks(task_type, status);
CREATE INDEX IF NOT EXISTS idx_tasks_retry ON tasks(next_retry_at) WHERE status = 'retry';

-- Time-series statistics for dashboard
CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date TEXT NOT NULL,                       -- YYYY-MM-DD for daily aggregation
    host_id INTEGER REFERENCES hosts(id),     -- Stats per host

    -- Counts
    files_scanned INTEGER DEFAULT 0,
    files_hashed INTEGER DEFAULT 0,
    files_uploaded INTEGER DEFAULT 0,
    files_errored INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,

    -- Bytes
    bytes_read INTEGER DEFAULT 0,             -- Bytes read from disk (hashing)
    bytes_uploaded INTEGER DEFAULT 0,         -- Bytes sent to Google

    -- Performance
    scan_duration_ms INTEGER DEFAULT 0,
    hash_duration_ms INTEGER DEFAULT 0,
    upload_duration_ms INTEGER DEFAULT 0,

    UNIQUE(date, host_id)
);

CREATE INDEX IF NOT EXISTS idx_stats_date ON stats(date);

-- Configuration key-value store
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default configuration
INSERT OR IGNORE INTO config (key, value, description) VALUES
    ('source_dirs', '[]', 'JSON array of source_names to sync'),
    ('file_extensions', 'jpg,jpeg,png,gif,heic,heif,webp,mp4,mov,avi,mkv,3gp', 'Comma-separated list of extensions to sync'),
    ('ignore_patterns', '.thumbnails,@eaDir,.DS_Store,Thumbs.db,.SynologyWorkingDirectory', 'Comma-separated patterns to ignore'),
    ('parallel_uploads', '4', 'Number of concurrent uploads'),
    ('parallel_hashers', '4', 'Number of concurrent hash workers'),
    ('auto_sync_enabled', 'false', 'Enable automatic scheduled sync'),
    ('auto_sync_cron', '0 2 * * *', 'Cron expression for auto sync (default: 2am daily)'),
    ('google_auth_status', 'not_configured', 'Google API authentication status'),
    ('google_account', '', 'Authenticated Google account email'),
    ('current_host_id', '', 'ID of the host this instance is running on');

-- Activity log for recent events
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    host_id INTEGER REFERENCES hosts(id),
    event_type TEXT NOT NULL,                 -- scan_started, scan_completed, upload_completed, error, etc.
    message TEXT NOT NULL,
    details TEXT,                             -- JSON with additional details
    job_id INTEGER REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log(event_type);

-- Trigger to update updated_at on files
CREATE TRIGGER IF NOT EXISTS files_updated_at
AFTER UPDATE ON files
BEGIN
    UPDATE files SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Trigger to update host last_seen_at
CREATE TRIGGER IF NOT EXISTS hosts_last_seen
AFTER INSERT ON jobs
BEGIN
    UPDATE hosts SET last_seen_at = CURRENT_TIMESTAMP WHERE id = NEW.host_id;
END;

-- View: Database size and stats
CREATE VIEW IF NOT EXISTS db_stats AS
SELECT
    (SELECT COUNT(*) FROM files) as total_files,
    (SELECT COUNT(*) FROM files WHERE status = 'uploaded') as uploaded_files,
    (SELECT COUNT(*) FROM files WHERE status = 'pending') as pending_files,
    (SELECT COUNT(*) FROM files WHERE status = 'error') as error_files,
    (SELECT COUNT(DISTINCT sha256) FROM files WHERE sha256 IS NOT NULL) as unique_hashes,
    (SELECT SUM(size) FROM files) as total_bytes,
    (SELECT SUM(size) FROM files WHERE status = 'uploaded') as uploaded_bytes,
    (SELECT COUNT(*) FROM hosts) as total_hosts;

-- View: Last 7 days activity
CREATE VIEW IF NOT EXISTS last_7_days AS
SELECT
    date,
    host_id,
    files_scanned,
    files_hashed,
    files_uploaded,
    files_errored,
    bytes_read,
    bytes_uploaded
FROM stats
WHERE date >= date('now', '-7 days')
ORDER BY date DESC;

-- View: Files with host info
CREATE VIEW IF NOT EXISTS files_with_host AS
SELECT
    f.*,
    h.hostname as scanned_by_hostname,
    uh.hostname as uploaded_by_hostname
FROM files f
LEFT JOIN hosts h ON f.scanned_by_host_id = h.id
LEFT JOIN hosts uh ON f.uploaded_by_host_id = uh.id;

-- Helper: Get or create host by hostname
-- Usage: INSERT OR IGNORE INTO hosts (hostname) VALUES ('myhost');
--        SELECT id FROM hosts WHERE hostname = 'myhost';
