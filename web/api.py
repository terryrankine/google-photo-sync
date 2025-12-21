"""
REST API Endpoints

All API routes for the web dashboard.
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.sync import get_orchestrator

router = APIRouter()


# Request/Response Models
class ConfigUpdate(BaseModel):
    parallel_uploads: Optional[int] = None
    parallel_hashers: Optional[int] = None
    file_extensions: Optional[str] = None
    ignore_patterns: Optional[str] = None
    auto_sync_enabled: Optional[bool] = None
    auto_sync_cron: Optional[str] = None


# Status endpoints
@router.get("/status")
async def get_status(request: Request):
    """Get current system status."""
    db = request.app.state.db

    # Check for active job
    async with db.execute(
        "SELECT * FROM jobs WHERE status IN ('running', 'scanning', 'hashing', 'uploading') LIMIT 1"
    ) as cursor:
        active = await cursor.fetchone()

    if active:
        return {
            "status": active['status'],
            "job_id": active['id'],
            "progress": active['progress_percent'],
        }

    return {"status": "idle"}


@router.get("/dashboard")
async def get_dashboard(request: Request):
    """Get all dashboard data in a single call."""
    db = request.app.state.db
    data_dir = Path(os.getenv('DATA_DIR', './data'))
    db_path = data_dir / "gphoto_sync.db"

    # 1. Status + Active job
    async with db.execute("""
        SELECT * FROM jobs
        WHERE status IN ('running', 'scanning', 'hashing', 'uploading', 'paused')
        ORDER BY started_at DESC LIMIT 1
    """) as cursor:
        active_row = await cursor.fetchone()

    active_job = dict(active_row) if active_row else None
    status = active_row['status'] if active_row else 'idle'

    # 2. Stats cards
    async with db.execute("SELECT * FROM db_stats") as cursor:
        stats_row = await cursor.fetchone()

    stats = {
        "total_files": stats_row['total_files'] or 0,
        "uploaded_files": stats_row['uploaded_files'] or 0,
        "pending_files": stats_row['pending_files'] or 0,
        "error_files": stats_row['error_files'] or 0,
        "unique_hashes": stats_row['unique_hashes'] or 0,
        "total_bytes": stats_row['total_bytes'] or 0,
        "uploaded_bytes": stats_row['uploaded_bytes'] or 0,
    } if stats_row else {}

    # 3. DB size
    db_size = db_path.stat().st_size if db_path.exists() else 0

    # 4. Activity log (last 10)
    async with db.execute("""
        SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT 10
    """) as cursor:
        activity = [dict(row) async for row in cursor]

    # 5. Chart data (last 7 days)
    async with db.execute("""
        SELECT date, files_uploaded, files_hashed, files_errored
        FROM stats WHERE date >= date('now', '-7 days')
        ORDER BY date ASC
    """) as cursor:
        chart_rows = [dict(row) async for row in cursor]

    chart = {
        "labels": [row['date'] for row in chart_rows],
        "uploaded": [row['files_uploaded'] or 0 for row in chart_rows],
        "hashed": [row['files_hashed'] or 0 for row in chart_rows],
        "errors": [row['files_errored'] or 0 for row in chart_rows],
    }

    return {
        "status": status,
        "active_job": active_job,
        "stats": stats,
        "db_size_bytes": db_size,
        "activity": activity,
        "chart": chart,
    }


@router.get("/db-size")
async def get_db_size(request: Request):
    """Get database file size."""
    data_dir = Path(os.getenv('DATA_DIR', './data'))
    db_path = data_dir / "gphoto_sync.db"

    if db_path.exists():
        size = db_path.stat().st_size
        if size >= 1024 * 1024 * 1024:
            return f"DB: {size / (1024**3):.1f} GB"
        elif size >= 1024 * 1024:
            return f"DB: {size / (1024**2):.1f} MB"
        else:
            return f"DB: {size / 1024:.1f} KB"

    return "DB: 0 KB"


# Stats endpoints
@router.get("/stats/cards")
async def get_stats_cards(request: Request):
    """Get stats for dashboard cards."""
    db = request.app.state.db

    async with db.execute("SELECT * FROM db_stats") as cursor:
        row = await cursor.fetchone()

    return {
        "total_files": row['total_files'] or 0,
        "uploaded_files": row['uploaded_files'] or 0,
        "pending_files": row['pending_files'] or 0,
        "error_files": row['error_files'] or 0,
        "unique_hashes": row['unique_hashes'] or 0,
        "total_bytes": row['total_bytes'] or 0,
        "uploaded_bytes": row['uploaded_bytes'] or 0,
    }


@router.get("/stats/daily")
async def get_daily_stats(request: Request, days: int = 7):
    """Get daily statistics for the last N days."""
    db = request.app.state.db

    async with db.execute("""
        SELECT * FROM stats
        WHERE date >= date('now', ?)
        ORDER BY date DESC
    """, (f'-{days} days',)) as cursor:
        rows = [dict(row) async for row in cursor]

    return rows


@router.get("/stats/chart")
async def get_chart_data(request: Request, intervals: int = 20, minutes_per_interval: int = 5):
    """Get activity for Chart.js visualization.

    Returns upload, hash, and error counts for rolling time windows.
    Default: 20 intervals of 5 minutes each = 100 minutes of history.
    """
    db = request.app.state.db

    labels = []
    uploaded = []
    hashed = []
    errors = []

    for i in range(intervals - 1, -1, -1):
        start_offset = i * minutes_per_interval
        end_offset = (i + 1) * minutes_per_interval
        start_param = f'-{end_offset} minutes'
        end_param = f'-{start_offset} minutes'

        # Uploads in this window
        async with db.execute("""
            SELECT COUNT(*) as count
            FROM files
            WHERE uploaded_at IS NOT NULL
              AND uploaded_at >= datetime('now', ?)
              AND uploaded_at < datetime('now', ?)
        """, (start_param, end_param)) as cursor:
            row = await cursor.fetchone()
            uploaded.append(row['count'] if row else 0)

        # Hashed files (created with sha256) in this window
        async with db.execute("""
            SELECT COUNT(*) as count
            FROM files
            WHERE sha256 IS NOT NULL
              AND created_at >= datetime('now', ?)
              AND created_at < datetime('now', ?)
        """, (start_param, end_param)) as cursor:
            row = await cursor.fetchone()
            hashed.append(row['count'] if row else 0)

        # Errors in this window
        async with db.execute("""
            SELECT COUNT(*) as count
            FROM files
            WHERE status = 'error'
              AND updated_at >= datetime('now', ?)
              AND updated_at < datetime('now', ?)
        """, (start_param, end_param)) as cursor:
            row = await cursor.fetchone()
            errors.append(row['count'] if row else 0)

        if start_offset == 0:
            labels.append('now')
        else:
            labels.append(f'-{start_offset}m')

    return {
        "labels": labels,
        "uploaded": uploaded,
        "hashed": hashed,
        "errors": errors,
        "interval_minutes": minutes_per_interval,
    }


# Job endpoints
@router.get("/jobs")
async def list_jobs(request: Request, limit: int = 50):
    """List all jobs."""
    db = request.app.state.db

    async with db.execute("""
        SELECT * FROM jobs
        ORDER BY started_at DESC
        LIMIT ?
    """, (limit,)) as cursor:
        rows = [dict(row) async for row in cursor]

    return rows


@router.get("/jobs/active")
async def get_active_job(request: Request):
    """Get currently active job if any."""
    db = request.app.state.db

    async with db.execute("""
        SELECT * FROM jobs
        WHERE status IN ('running', 'scanning', 'hashing', 'uploading', 'paused')
        ORDER BY started_at DESC
        LIMIT 1
    """) as cursor:
        row = await cursor.fetchone()

    if row:
        return dict(row)
    return None


@router.get("/workers/live")
async def get_live_worker_metrics(request: Request):
    """
    Get real-time worker metrics for dashboard.
    Designed for 1-2 second polling - all data is in-memory.
    """
    from src.metrics import get_metrics

    db = request.app.state.db
    metrics = get_metrics()

    # Get job progress from DB for complete picture
    job_progress = None
    if metrics.current_job_id:
        async with db.execute(
            "SELECT * FROM jobs WHERE id = ?", (metrics.current_job_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                job_progress = dict(row)

    return {
        **metrics.to_dict(),
        "job_progress": job_progress,
    }


@router.post("/jobs")
async def create_job(request: Request, background_tasks: BackgroundTasks):
    """Create and start a new sync job."""
    db = request.app.state.db

    # Get source directories from config
    async with db.execute(
        "SELECT value FROM config WHERE key = 'source_dirs'"
    ) as cursor:
        row = await cursor.fetchone()
        source_dirs_json = row['value'] if row else '[]'

    source_dirs = json.loads(source_dirs_json)

    if not source_dirs:
        raise HTTPException(400, "No source directories configured. Add directories in Settings first.")

    # Create new job
    async with db.execute("""
        INSERT INTO jobs (source_dirs, status, current_phase)
        VALUES (?, 'pending', 'initializing')
    """, (source_dirs_json,)) as cursor:
        job_id = cursor.lastrowid

    await db.commit()

    # Trigger sync in background
    orchestrator = get_orchestrator()
    if orchestrator:
        background_tasks.add_task(orchestrator.start_sync, job_id, source_dirs)
        return {"job_id": job_id, "status": "started"}
    else:
        return {"job_id": job_id, "status": "created", "warning": "Orchestrator not initialized"}


@router.post("/jobs/{job_id}/pause")
async def pause_job(request: Request, job_id: int):
    """Pause a running job."""
    db = request.app.state.db

    await db.execute(
        "UPDATE jobs SET status = 'paused' WHERE id = ? AND status IN ('running', 'scanning', 'hashing', 'uploading')",
        (job_id,)
    )
    await db.commit()

    return {"status": "paused"}


@router.post("/jobs/{job_id}/resume")
async def resume_job(request: Request, job_id: int, background_tasks: BackgroundTasks):
    """Resume an interrupted or paused job."""
    db = request.app.state.db

    # Check job exists and is resumable
    async with db.execute(
        "SELECT status FROM jobs WHERE id = ?", (job_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(404, "Job not found")

    if row['status'] not in ('running', 'paused'):
        raise HTTPException(400, f"Cannot resume job with status '{row['status']}'")

    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(500, "Orchestrator not initialized")

    # Resume in background
    background_tasks.add_task(orchestrator.resume_sync, job_id)

    return {"status": "resuming", "job_id": job_id}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(request: Request, job_id: int):
    """Cancel a job."""
    db = request.app.state.db

    await db.execute(
        "UPDATE jobs SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (job_id,)
    )
    await db.commit()

    return {"status": "cancelled"}


# Config endpoints
@router.get("/config")
async def get_config(request: Request):
    """Get all configuration."""
    db = request.app.state.db

    config = {}
    async with db.execute("SELECT key, value FROM config") as cursor:
        async for row in cursor:
            config[row['key']] = row['value']

    return config


@router.put("/config")
async def update_config(request: Request, config: ConfigUpdate):
    """Update configuration."""
    db = request.app.state.db

    updates = config.dict(exclude_none=True)

    for key, value in updates.items():
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        await db.execute(
            "UPDATE config SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (str(value), key)
        )

    await db.commit()
    return {"status": "updated", "keys": list(updates.keys())}


@router.get("/config/source-dirs")
async def get_source_dirs(request: Request):
    """Get configured source directories."""
    db = request.app.state.db

    async with db.execute(
        "SELECT value FROM config WHERE key = 'source_dirs'"
    ) as cursor:
        row = await cursor.fetchone()

    dirs = json.loads(row['value']) if row and row['value'] else []
    return {"dirs": dirs}


class SourceDirsUpdate(BaseModel):
    dirs: List[str]


@router.put("/config/source-dirs")
async def update_source_dirs(request: Request, body: SourceDirsUpdate):
    """Update all source directories at once."""
    db = request.app.state.db

    await db.execute(
        "UPDATE config SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = 'source_dirs'",
        (json.dumps(body.dirs),)
    )
    await db.commit()

    return {"dirs": body.dirs}


class SourceDirRequest(BaseModel):
    path: str


@router.post("/config/source-dirs")
async def add_source_dir(request: Request, body: SourceDirRequest):
    """Add a source directory."""
    db = request.app.state.db

    path = body.path
    if not path:
        raise HTTPException(400, "Path is required")

    # Validate path exists
    if not Path(path).exists():
        raise HTTPException(400, f"Path does not exist: {path}")

    async with db.execute(
        "SELECT value FROM config WHERE key = 'source_dirs'"
    ) as cursor:
        row = await cursor.fetchone()

    dirs = json.loads(row['value']) if row and row['value'] else []

    if path not in dirs:
        dirs.append(path)
        await db.execute(
            "UPDATE config SET value = ? WHERE key = 'source_dirs'",
            (json.dumps(dirs),)
        )
        await db.commit()

    return {"dirs": dirs, "added": path}


@router.delete("/config/source-dirs")
async def remove_source_dir(request: Request, path: str):
    """Remove a source directory."""
    db = request.app.state.db

    async with db.execute(
        "SELECT value FROM config WHERE key = 'source_dirs'"
    ) as cursor:
        row = await cursor.fetchone()

    dirs = json.loads(row['value']) if row and row['value'] else []

    if path in dirs:
        dirs.remove(path)
        await db.execute(
            "UPDATE config SET value = ? WHERE key = 'source_dirs'",
            (json.dumps(dirs),)
        )
        await db.commit()

    return {"dirs": dirs, "removed": path}


# Auth endpoints
@router.post("/auth/upload")
async def upload_credentials(request: Request, credentials: UploadFile = File(...)):
    """Upload Google API credentials file."""
    config_dir = Path(os.getenv('CONFIG_DIR', './config'))
    creds_path = config_dir / "credentials.json"

    content = await credentials.read()
    creds_path.write_bytes(content)

    return {"status": "uploaded", "path": str(creds_path)}


@router.post("/auth/refresh")
async def refresh_auth(request: Request):
    """Trigger OAuth re-authentication."""
    # TODO: Implement actual OAuth flow
    return {"status": "auth_required", "url": "/auth/google"}


@router.post("/auth/revoke")
async def revoke_auth(request: Request):
    """Revoke Google API access."""
    db = request.app.state.db

    await db.execute(
        "UPDATE config SET value = 'not_configured' WHERE key = 'google_auth_status'"
    )
    await db.execute(
        "UPDATE config SET value = '' WHERE key = 'google_account'"
    )
    await db.commit()

    # Delete token file
    config_dir = Path(os.getenv('CONFIG_DIR', './config'))
    token_path = config_dir / "token.json"
    if token_path.exists():
        token_path.unlink()

    return {"status": "revoked"}


# Activity log
@router.get("/activity")
async def get_activity(request: Request, limit: int = 20):
    """Get recent activity log."""
    db = request.app.state.db

    async with db.execute("""
        SELECT * FROM activity_log
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,)) as cursor:
        rows = [dict(row) async for row in cursor]

    return rows


# Application logs (from in-memory buffer)
@router.get("/logs")
async def get_logs(limit: int = 100, level: str = None):
    """Get recent application logs from in-memory buffer."""
    from src.log_buffer import get_log_buffer
    buffer = get_log_buffer()
    return buffer.get_logs(limit=limit, level=level)


# Files endpoints
@router.get("/files")
async def list_files(
    request: Request,
    page: int = 1,
    limit: int = 50,
    search: str = "",
    status: str = "",
    sort_by: str = "created_at",
    sort_dir: str = "desc"
):
    """List files with pagination, search, status filter, and sorting."""
    db = request.app.state.db
    offset = (page - 1) * limit

    # Build query with optional filters
    where_clauses = []
    params = []

    if search:
        where_clauses.append("(relative_path LIKE ? OR filename LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    if status:
        where_clauses.append("status = ?")
        params.append(status)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Validate and sanitize sort parameters
    valid_columns = {'relative_path', 'size', 'status', 'mtime', 'created_at', 'uploaded_at'}
    if sort_by not in valid_columns:
        sort_by = 'created_at'
    sort_direction = 'ASC' if sort_dir.lower() == 'asc' else 'DESC'

    # Get files
    query = f"""
        SELECT id, source_name, relative_path, filename, local_path,
               extension, size, mtime, sha256, media_id, status,
               uploaded_at, created_at
        FROM files
        {where_sql}
        ORDER BY {sort_by} {sort_direction}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    async with db.execute(query, params) as cursor:
        rows = [dict(row) async for row in cursor]

    # Get total count with same filters
    count_query = f"SELECT COUNT(*) as count FROM files {where_sql}"
    count_params = params[:-2]  # Exclude LIMIT and OFFSET params

    async with db.execute(count_query, count_params) as cursor:
        total = (await cursor.fetchone())['count']

    return {
        "files": rows,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit
    }


@router.get("/files/{file_id}/preview")
async def get_file_preview(request: Request, file_id: int):
    """Serve image file for preview."""
    db = request.app.state.db

    async with db.execute("""
        SELECT f.source_name, f.relative_path, f.extension, p.local_path as source_path
        FROM files f
        JOIN path_mappings p ON f.source_name = p.source_name
        JOIN hosts h ON p.host_id = h.id
        WHERE f.id = ? AND h.hostname = (SELECT value FROM config WHERE key = 'current_hostname')
    """, (file_id,)) as cursor:
        row = await cursor.fetchone()

    if not row:
        # Fallback: try using the local_path stored in files table
        async with db.execute(
            "SELECT local_path, extension FROM files WHERE id = ?", (file_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row or not row['local_path']:
            raise HTTPException(404, "File not found")

        file_path = Path(row['local_path'])
    else:
        # Construct path from source mapping
        source_path = Path(row['source_path'])
        file_path = source_path / row['relative_path']

    if not file_path.exists():
        raise HTTPException(404, f"File not found on disk: {file_path}")

    # Determine media type
    ext = row['extension'].lower() if row['extension'] else ''
    media_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'heic': 'image/heic',
        'heif': 'image/heif',
        'mp4': 'video/mp4',
        'mov': 'video/quicktime',
        'avi': 'video/x-msvideo',
        'mkv': 'video/x-matroska',
    }
    media_type = media_types.get(ext, 'application/octet-stream')

    return FileResponse(file_path, media_type=media_type)


# Error tracking endpoints
@router.get("/errors")
async def get_errors(
    request: Request,
    page: int = 1,
    limit: int = 50,
    error_type: str = ""  # "files", "tasks", "dead"
):
    """Get files and tasks with errors."""
    db = request.app.state.db
    offset = (page - 1) * limit

    # Summary counts
    async with db.execute("""
        SELECT
            (SELECT COUNT(*) FROM files WHERE status = 'error') as error_files,
            (SELECT COUNT(*) FROM files WHERE error_message IS NOT NULL) as files_with_messages,
            (SELECT COUNT(*) FROM tasks WHERE status = 'dead') as dead_tasks,
            (SELECT COUNT(*) FROM tasks WHERE status = 'failed') as failed_tasks
    """) as cursor:
        summary = dict(await cursor.fetchone())

    # Get error files
    if error_type in ("", "files"):
        async with db.execute("""
            SELECT id, source_name, relative_path, filename, status,
                   error_message, updated_at
            FROM files
            WHERE status = 'error' OR error_message IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cursor:
            error_files = [dict(row) async for row in cursor]
    else:
        error_files = []

    # Get dead/failed tasks
    if error_type in ("", "tasks", "dead"):
        async with db.execute("""
            SELECT t.id, t.task_type, t.status, t.error_message,
                   t.retry_count, t.max_retries, t.completed_at,
                   f.relative_path, f.filename
            FROM tasks t
            LEFT JOIN files f ON t.file_id = f.id
            WHERE t.status IN ('dead', 'failed')
            ORDER BY t.completed_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cursor:
            error_tasks = [dict(row) async for row in cursor]
    else:
        error_tasks = []

    # Get recent error messages grouped by type
    async with db.execute("""
        SELECT error_message, COUNT(*) as count
        FROM files
        WHERE error_message IS NOT NULL
        GROUP BY error_message
        ORDER BY count DESC
        LIMIT 10
    """) as cursor:
        error_breakdown = [dict(row) async for row in cursor]

    return {
        "summary": summary,
        "error_files": error_files,
        "error_tasks": error_tasks,
        "error_breakdown": error_breakdown,
        "page": page,
        "limit": limit
    }


@router.post("/errors/retry/{task_id}")
async def retry_dead_task(request: Request, task_id: int):
    """Reset a dead task to pending for retry."""
    db = request.app.state.db

    async with db.execute(
        "SELECT status FROM tasks WHERE id = ?", (task_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(404, "Task not found")

    if row['status'] not in ('dead', 'failed'):
        raise HTTPException(400, f"Task status is '{row['status']}', not dead/failed")

    await db.execute("""
        UPDATE tasks
        SET status = 'pending',
            error_message = NULL,
            retry_count = 0,
            next_retry_at = NULL
        WHERE id = ?
    """, (task_id,))
    await db.commit()

    return {"status": "reset", "task_id": task_id}


@router.post("/errors/retry-all")
async def retry_all_dead_tasks(request: Request):
    """Reset all dead tasks to pending."""
    db = request.app.state.db

    async with db.execute("""
        UPDATE tasks
        SET status = 'pending',
            error_message = NULL,
            retry_count = 0,
            next_retry_at = NULL
        WHERE status = 'dead'
    """) as cursor:
        count = cursor.rowcount

    await db.commit()

    return {"status": "reset", "count": count}


@router.delete("/errors/clear")
async def clear_file_errors(request: Request):
    """Clear error status from files (reset to pending)."""
    db = request.app.state.db

    async with db.execute("""
        UPDATE files
        SET status = 'pending',
            error_message = NULL
        WHERE status = 'error'
    """) as cursor:
        count = cursor.rowcount

    await db.commit()

    return {"status": "cleared", "count": count}


# Database operations
@router.get("/db/stats")
async def get_db_stats(request: Request):
    """Get database statistics."""
    db = request.app.state.db

    async with db.execute("SELECT * FROM db_stats") as cursor:
        row = await cursor.fetchone()

    data_dir = Path(os.getenv('DATA_DIR', './data'))
    db_path = data_dir / "gphoto_sync.db"
    db_size = db_path.stat().st_size if db_path.exists() else 0

    return {
        **(dict(row) if row else {}),
        "db_size_bytes": db_size,
    }


@router.post("/db/vacuum")
async def vacuum_db(request: Request):
    """Optimize database (VACUUM)."""
    db = request.app.state.db

    await db.execute("VACUUM")

    return {"status": "optimized"}


@router.post("/db/export")
async def export_db(request: Request):
    """Export file list as CSV."""
    # TODO: Implement CSV export
    return {"status": "not_implemented"}


@router.post("/stats/backfill")
async def backfill_stats(request: Request):
    """Backfill daily stats from files table timestamps.

    Uses uploaded_at for upload stats and created_at for hash stats.
    """
    db = request.app.state.db

    # Clear existing stats first to avoid duplicates
    await db.execute("DELETE FROM stats")

    # Backfill by combining upload and hash data per date
    # Use a CTE to get all dates and aggregate data
    await db.execute("""
        INSERT INTO stats (date, files_uploaded, bytes_uploaded, files_hashed, bytes_read, files_errored)
        SELECT
            date,
            SUM(files_uploaded) as files_uploaded,
            SUM(bytes_uploaded) as bytes_uploaded,
            SUM(files_hashed) as files_hashed,
            SUM(bytes_read) as bytes_read,
            SUM(files_errored) as files_errored
        FROM (
            -- Uploaded files by upload date
            SELECT
                DATE(uploaded_at) as date,
                COUNT(*) as files_uploaded,
                SUM(size) as bytes_uploaded,
                0 as files_hashed,
                0 as bytes_read,
                0 as files_errored
            FROM files
            WHERE uploaded_at IS NOT NULL
            GROUP BY DATE(uploaded_at)

            UNION ALL

            -- Hashed files by creation date
            SELECT
                DATE(created_at) as date,
                0 as files_uploaded,
                0 as bytes_uploaded,
                COUNT(*) as files_hashed,
                SUM(size) as bytes_read,
                0 as files_errored
            FROM files
            WHERE sha256 IS NOT NULL
            GROUP BY DATE(created_at)

            UNION ALL

            -- Error files by update date
            SELECT
                DATE(updated_at) as date,
                0 as files_uploaded,
                0 as bytes_uploaded,
                0 as files_hashed,
                0 as bytes_read,
                COUNT(*) as files_errored
            FROM files
            WHERE status = 'error'
            GROUP BY DATE(updated_at)
        )
        GROUP BY date
    """)

    await db.commit()

    # Return the backfilled stats
    async with db.execute("""
        SELECT * FROM stats ORDER BY date DESC LIMIT 30
    """) as cursor:
        rows = [dict(row) async for row in cursor]

    return {"status": "backfilled", "rows": len(rows), "stats": rows}


@router.get("/uploads/recent")
async def get_recent_uploads(request: Request, minutes: int = 5, limit: int = 20):
    """Get recent uploads within a rolling time window.

    Args:
        minutes: Rolling window in minutes (default: 5)
        limit: Max items to return (default: 20)
    """
    db = request.app.state.db

    # Get recent uploads within rolling window
    async with db.execute("""
        SELECT
            id, filename, relative_path, size, uploaded_at, media_id,
            CAST((julianday('now') - julianday(uploaded_at)) * 24 * 60 AS INTEGER) as minutes_ago
        FROM files
        WHERE uploaded_at IS NOT NULL
          AND uploaded_at >= datetime('now', ?)
        ORDER BY uploaded_at DESC
        LIMIT ?
    """, (f'-{minutes} minutes', limit)) as cursor:
        recent = []
        async for row in cursor:
            item = dict(row)
            # Add preview URL for image link
            item['preview_url'] = f"/api/files/{item['id']}/preview"
            recent.append(item)

    # Get aggregate for rolling window
    async with db.execute("""
        SELECT
            COUNT(*) as count,
            SUM(size) as total_bytes
        FROM files
        WHERE uploaded_at IS NOT NULL
          AND uploaded_at >= datetime('now', ?)
    """, (f'-{minutes} minutes',)) as cursor:
        agg = dict(await cursor.fetchone())

    return {
        "window_minutes": minutes,
        "count": agg['count'] or 0,
        "total_bytes": agg['total_bytes'] or 0,
        "uploads": recent
    }


@router.delete("/jobs/cleanup")
async def cleanup_old_jobs(request: Request, days: int = 7, status: str = "failed"):
    """Delete old jobs by age and status.

    Args:
        days: Delete jobs older than this many days (default: 7)
        status: Only delete jobs with this status (default: failed)
               Use 'all' to delete all old jobs regardless of status
    """
    db = request.app.state.db

    if status == "all":
        async with db.execute("""
            DELETE FROM jobs
            WHERE started_at < datetime('now', ?)
            AND status NOT IN ('running', 'scanning', 'hashing', 'uploading', 'paused')
        """, (f'-{days} days',)) as cursor:
            deleted = cursor.rowcount
    else:
        async with db.execute("""
            DELETE FROM jobs
            WHERE started_at < datetime('now', ?)
            AND status = ?
        """, (f'-{days} days', status)) as cursor:
            deleted = cursor.rowcount

    await db.commit()

    return {"deleted": deleted, "days": days, "status": status}


@router.delete("/jobs/{job_id}")
async def delete_job(request: Request, job_id: int):
    """Delete a specific job."""
    db = request.app.state.db

    # Check job exists and is not active
    async with db.execute(
        "SELECT status FROM jobs WHERE id = ?", (job_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(404, "Job not found")

    if row['status'] in ('running', 'scanning', 'hashing', 'uploading'):
        raise HTTPException(400, "Cannot delete active job")

    # Delete associated work_batches and tasks first (foreign keys)
    await db.execute("DELETE FROM tasks WHERE job_id = ?", (job_id,))
    await db.execute("DELETE FROM work_batches WHERE job_id = ?", (job_id,))
    await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    await db.commit()

    return {"deleted": job_id}


# Backwards compatibility aliases for frontend transition
@router.get("/batches")
async def list_batches_compat(request: Request, limit: int = 50):
    """Alias for /jobs - backwards compatibility."""
    return await list_jobs(request, limit)


@router.get("/batches/active")
async def get_active_batch_compat(request: Request):
    """Alias for /jobs/active - backwards compatibility."""
    return await get_active_job(request)


@router.post("/batches")
async def create_batch_compat(request: Request, background_tasks: BackgroundTasks):
    """Alias for /jobs - backwards compatibility."""
    return await create_job(request, background_tasks)


@router.post("/batches/{batch_id}/pause")
async def pause_batch_compat(request: Request, batch_id: int):
    """Alias for /jobs/{id}/pause - backwards compatibility."""
    return await pause_job(request, batch_id)


@router.post("/batches/{batch_id}/resume")
async def resume_batch_compat(request: Request, batch_id: int, background_tasks: BackgroundTasks):
    """Alias for /jobs/{id}/resume - backwards compatibility."""
    return await resume_job(request, batch_id, background_tasks)


@router.post("/batches/{batch_id}/cancel")
async def cancel_batch_compat(request: Request, batch_id: int):
    """Alias for /jobs/{id}/cancel - backwards compatibility."""
    return await cancel_job(request, batch_id)


# Documentation endpoint
@router.get("/quickstart")
async def get_quickstart():
    """Serve quickstart.md content - single source of truth for setup docs."""
    # Look for quickstart.md in app root (where the code lives)
    possible_paths = [
        Path(__file__).parent.parent / "quickstart.md",  # /app/quickstart.md in container
        Path("/app/quickstart.md"),
        Path("./quickstart.md"),
    ]

    for path in possible_paths:
        if path.exists():
            return {"content": path.read_text(), "path": str(path)}

    return {"content": "# Quickstart Guide\n\nDocumentation not found.", "path": None}
