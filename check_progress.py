#!/usr/bin/env python3
"""Quick status check script for debugging sync progress."""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('/data/gphoto_sync.db')
conn.row_factory = sqlite3.Row

print("=" * 60)
print("GOOGLE PHOTOS SYNC STATUS")
print("=" * 60)

# Active job
print("\n=== Active Job ===")
for row in conn.execute('''
    SELECT id, status, current_phase, progress_percent,
           files_scanned, files_hashed, files_uploaded, files_errored,
           started_at
    FROM jobs
    WHERE status IN ('running', 'scanning', 'hashing', 'uploading', 'paused')
    ORDER BY started_at DESC LIMIT 1
'''):
    print(f"  Job #{row['id']}: {row['status']} ({row['current_phase']})")
    print(f"  Progress: {row['progress_percent']:.1f}%")
    print(f"  Scanned: {row['files_scanned']} | Hashed: {row['files_hashed']} | Uploaded: {row['files_uploaded']}")
    print(f"  Errors: {row['files_errored']}")
    print(f"  Started: {row['started_at']}")
else:
    # Check if any jobs exist
    cursor = conn.execute("SELECT COUNT(*) as cnt FROM jobs")
    if cursor.fetchone()['cnt'] == 0:
        print("  No jobs found")

# Overall stats
print("\n=== Overall Stats ===")
for row in conn.execute("SELECT * FROM db_stats"):
    print(f"  Total files: {row['total_files']:,}")
    print(f"  Uploaded: {row['uploaded_files']:,}")
    print(f"  Pending: {row['pending_files']:,}")
    print(f"  Errors: {row['error_files']:,}")
    print(f"  Unique hashes: {row['unique_hashes']:,}")

# Work batches summary
print("\n=== Work Batches by Status ===")
for row in conn.execute('''
    SELECT status, COUNT(*) as cnt,
           SUM(files_succeeded) as succeeded,
           SUM(files_failed) as failed
    FROM work_batches
    GROUP BY status
'''):
    print(f"  {row['status']}: {row['cnt']} batches ({row['succeeded'] or 0} succeeded, {row['failed'] or 0} failed)")

# Running batches
print("\n=== Currently Running Batches ===")
running = list(conn.execute('''
    SELECT id, job_id, batch_type, worker_id, file_count, files_processed
    FROM work_batches WHERE status='running' LIMIT 10
'''))
if running:
    for row in running:
        pct = (row['files_processed'] / row['file_count'] * 100) if row['file_count'] else 0
        print(f"  Batch {row['id']}: {row['batch_type']} worker={row['worker_id']} {row['files_processed']}/{row['file_count']} ({pct:.0f}%)")
else:
    print("  None")

# Error summary
print("\n=== Error Summary ===")
print("  Files with errors:")
for row in conn.execute('''
    SELECT status, COUNT(*) as cnt FROM files
    WHERE status = 'error' OR error_message IS NOT NULL
    GROUP BY status
'''):
    print(f"    {row['status']}: {row['cnt']}")

print("\n  Tasks in dead letter queue:")
for row in conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status = 'dead'"):
    print(f"    Dead tasks: {row['cnt']}")

# Recent errors (last 10)
print("\n=== Recent File Errors (last 10) ===")
errors = list(conn.execute('''
    SELECT relative_path, error_message, updated_at
    FROM files
    WHERE error_message IS NOT NULL
    ORDER BY updated_at DESC LIMIT 10
'''))
if errors:
    for row in errors:
        path = row['relative_path'][:50] + '...' if len(row['relative_path']) > 50 else row['relative_path']
        msg = row['error_message'][:60] + '...' if row['error_message'] and len(row['error_message']) > 60 else row['error_message']
        print(f"  {path}")
        print(f"    -> {msg}")
else:
    print("  No errors found")

# Dead tasks details
print("\n=== Dead Tasks (last 10) ===")
dead = list(conn.execute('''
    SELECT t.id, t.task_type, t.error_message, t.retry_count, f.relative_path
    FROM tasks t
    LEFT JOIN files f ON t.file_id = f.id
    WHERE t.status = 'dead'
    ORDER BY t.completed_at DESC LIMIT 10
'''))
if dead:
    for row in dead:
        path = row['relative_path'][:40] + '...' if row['relative_path'] and len(row['relative_path']) > 40 else row['relative_path']
        msg = row['error_message'][:50] + '...' if row['error_message'] and len(row['error_message']) > 50 else row['error_message']
        print(f"  Task {row['id']} ({row['task_type']}): {path}")
        print(f"    Retries: {row['retry_count']} | Error: {msg}")
else:
    print("  No dead tasks")

# Last successful uploads
print("\n=== Last 5 Successful Uploads ===")
for row in conn.execute('''
    SELECT relative_path, uploaded_at
    FROM files
    WHERE status = 'uploaded'
    ORDER BY uploaded_at DESC LIMIT 5
'''):
    path = row['relative_path'][:50] + '...' if len(row['relative_path']) > 50 else row['relative_path']
    print(f"  {row['uploaded_at']}: {path}")

print("\n" + "=" * 60)
