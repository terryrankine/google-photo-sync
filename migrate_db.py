#!/usr/bin/env python3
"""Drop and recreate tasks and work_batches tables with correct schema."""
import sqlite3

conn = sqlite3.connect('/data/gphoto_sync.db')
c = conn.cursor()

# Drop old tables
c.execute('DROP TABLE IF EXISTS tasks')
c.execute('DROP TABLE IF EXISTS work_batches')

# Recreate with correct schema
c.execute('''CREATE TABLE IF NOT EXISTS work_batches (
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
)''')

c.execute('''CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    work_batch_id INTEGER REFERENCES work_batches(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP,
    bytes_transferred INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')

# Create indexes
c.execute('CREATE INDEX IF NOT EXISTS idx_work_batches_job ON work_batches(job_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_work_batches_status ON work_batches(status, batch_type)')
c.execute('CREATE INDEX IF NOT EXISTS idx_tasks_job ON tasks(job_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_tasks_work_batch ON tasks(work_batch_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')

conn.commit()
conn.close()
print('Migration complete: tasks and work_batches tables recreated')
