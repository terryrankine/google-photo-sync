-- Add work_batches table
CREATE TABLE IF NOT EXISTS work_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    batch_type TEXT NOT NULL,
    batch_number INTEGER NOT NULL,
    file_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    worker_id INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    files_processed INTEGER DEFAULT 0,
    files_succeeded INTEGER DEFAULT 0,
    files_failed INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_work_batches_job ON work_batches(job_id);
CREATE INDEX IF NOT EXISTS idx_work_batches_status ON work_batches(status, batch_type);
CREATE INDEX IF NOT EXISTS idx_work_batches_worker ON work_batches(worker_id) WHERE status = 'running';

-- Add work_batch_id to tasks if not exists
-- SQLite doesn't support ADD COLUMN IF NOT EXISTS, so this may error if already exists
-- ALTER TABLE tasks ADD COLUMN work_batch_id INTEGER REFERENCES work_batches(id) ON DELETE CASCADE;
