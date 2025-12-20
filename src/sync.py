"""
Sync Orchestrator

Coordinates the three-phase sync process:
1. SCAN - Find new/changed files
2. HASH - Compute SHA256 hashes (via work batches)
3. UPLOAD - Upload to Google Photos (via work batches)

Architecture:
- Job: A complete sync run (this file creates jobs)
- WorkBatch: Chunk of ~1000 files (created by TaskQueue)
- Workers: Process entire batches, not individual files
"""

import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import aiosqlite

from .scanner import scan_directory, ScanResult, FileInfo
from .hasher import hash_files, CHUNK_SIZE
from .uploader import GooglePhotosUploader, UploadTokenBatcher
from .task_queue import TaskQueue, TaskType, WorkerPool, RetryableError, PermanentError
from .metrics import get_metrics

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    """Orchestrates the full sync pipeline using jobs and work batches."""

    def __init__(self, db: aiosqlite.Connection, config_dir: Path, data_dir: Path):
        self.db = db
        self.config_dir = config_dir
        self.data_dir = data_dir
        self._running = False
        self._current_job_id: Optional[int] = None
        self._task_queue: Optional[TaskQueue] = None
        self._worker_pool: Optional[WorkerPool] = None
        self._uploader: Optional[GooglePhotosUploader] = None
        self._token_batcher: Optional[UploadTokenBatcher] = None
        self._source_dirs: list[str] = []

    async def resume_sync(self, job_id: int):
        """Resume an interrupted job from its pending work batches."""
        if self._running:
            logger.warning("Sync already running")
            return

        # Get job info
        async with self.db.execute(
            "SELECT source_dirs, current_phase FROM jobs WHERE id = ?", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                logger.error(f"Job {job_id} not found")
                return

        self._source_dirs = json.loads(row[0])
        phase = row[1]

        self._running = True
        self._current_job_id = job_id
        get_metrics().start_job(job_id)

        try:
            # Check for pending work
            async with self.db.execute("""
                SELECT COUNT(*) FROM work_batches
                WHERE job_id = ? AND status IN ('pending', 'running')
            """, (job_id,)) as cursor:
                pending = (await cursor.fetchone())[0]

            if pending == 0:
                # No work left - mark complete
                await self._update_job_status(job_id, 'completed', 'done')
                logger.info(f"Job {job_id}: No pending work, marking complete")
                return

            logger.info(f"Resuming job {job_id} with {pending} pending batches")

            # Initialize uploader and worker pool
            await self._init_upload_pipeline(job_id)

            # Wait for all work to complete
            await self._wait_for_work_batches(job_id)
            await self._worker_pool.stop()

            # Update final progress
            progress = await self._task_queue.get_job_progress(job_id)
            await self._update_job_progress(
                job_id,
                uploaded=progress["total_succeeded"],
                errors=progress["total_failed"]
            )

            await self._update_job_status(job_id, 'completed', 'done')
            logger.info(f"Job {job_id} resumed and completed")

        except Exception as e:
            logger.error(f"Job {job_id} resume failed: {e}")
            await self._update_job_status(job_id, 'failed', 'error')
            raise
        finally:
            self._running = False
            self._current_job_id = None
            get_metrics().end_job()
            if self._worker_pool:
                await self._worker_pool.stop()
            if self._token_batcher:
                await self._token_batcher.stop()
            if self._uploader:
                await self._uploader.__aexit__(None, None, None)

    async def start_sync(self, job_id: int, source_dirs: list[str]):
        """Start a sync job with pipelined hash + upload processing."""
        if self._running:
            logger.warning("Sync already running")
            return

        self._running = True
        self._current_job_id = job_id
        self._source_dirs = source_dirs

        # Start job-level metrics tracking
        get_metrics().start_job(job_id)

        try:
            # Initialize task queue
            self._task_queue = TaskQueue(self.db)

            # Get worker counts from config
            parallel_hashers = await self._get_config_int('parallel_hashers', 4)
            parallel_uploads = await self._get_config_int('parallel_uploads', 4)

            await self._update_job_status(job_id, 'running', 'scanning')
            logger.info(f"Starting sync job {job_id} with dirs: {source_dirs}")

            # Phase 1: SCAN - find files that need hashing
            scan_result = await self._run_scan_phase(job_id, source_dirs)

            # Also get pending files that have hash but aren't uploaded
            pending_upload_ids = []
            async with self.db.execute("""
                SELECT id FROM files
                WHERE sha256 IS NOT NULL AND media_id IS NULL AND status = 'pending'
            """) as cursor:
                async for row in cursor:
                    pending_upload_ids.append(row[0])

            files_to_hash = scan_result.needs_hash if scan_result else []
            logger.info(f"Job {job_id}: {len(files_to_hash)} files need hash, {len(pending_upload_ids)} pending upload")

            if not files_to_hash and not pending_upload_ids:
                await self._update_job_status(job_id, 'completed', 'done')
                logger.info(f"Job {job_id}: No files to process")
                return

            # Phases 2+3: HASH new files and UPLOAD all pending
            await self._update_job_status(job_id, 'running', 'hashing')
            await self._run_pipelined_hash_upload(
                job_id,
                files_to_hash,
                pending_upload_ids,
                parallel_hashers,
                parallel_uploads
            )

            await self._update_job_status(job_id, 'completed', 'done')
            logger.info(f"Job {job_id} completed")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            await self._update_job_status(job_id, 'failed', 'error')
            raise
        finally:
            self._running = False
            self._current_job_id = None
            # End job-level metrics tracking
            get_metrics().end_job()
            if self._worker_pool:
                await self._worker_pool.stop()
            if self._token_batcher:
                await self._token_batcher.stop()
            if self._uploader:
                await self._uploader.__aexit__(None, None, None)

    async def _get_config_int(self, key: str, default: int) -> int:
        """Get integer config value."""
        async with self.db.execute(
            "SELECT value FROM config WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row else default

    async def _run_scan_phase(self, job_id: int, source_dirs: list[str]) -> Optional[ScanResult]:
        """Phase 1: Scan directories for files."""
        logger.info(f"Job {job_id}: Starting scan phase")

        all_files = []
        total_scanned = 0
        total_bytes = 0

        for dir_path in source_dirs:
            path = Path(dir_path)
            if not path.exists():
                logger.warning(f"Directory not found: {dir_path}")
                continue

            result = await scan_directory(path, db=self.db)
            all_files.extend(result.needs_hash)
            total_scanned += len(result.files)
            total_bytes += result.total_bytes

            await self._update_job_progress(
                job_id,
                scanned=total_scanned,
                total_bytes=total_bytes
            )

        logger.info(f"Job {job_id}: Scan found {len(all_files)} files needing hash")

        # Return combined result
        combined = ScanResult()
        combined.needs_hash = all_files
        combined.files = all_files
        combined.total_bytes = total_bytes
        return combined

    async def _init_upload_pipeline(self, job_id: int):
        """Initialize task queue, uploader, token batcher, and worker pool."""
        self._task_queue = TaskQueue(self.db)

        credentials_path = self.config_dir / "credentials.json"
        token_path = self.config_dir / "token.json"

        if not credentials_path.exists() or not token_path.exists():
            raise ValueError("Missing credentials or token - cannot upload")

        # Load known media_ids for deduplication detection
        known_media_ids = set()
        async with self.db.execute(
            "SELECT DISTINCT media_id FROM files WHERE media_id IS NOT NULL"
        ) as cursor:
            async for row in cursor:
                known_media_ids.add(row[0])

        self._uploader = GooglePhotosUploader(credentials_path, token_path, known_media_ids)
        await self._uploader.__aenter__()

        # Create token batcher for efficient batched batchCreate calls
        # Per Google best practices: upload bytes parallel, batchCreate serial with 50 items
        # Pass task_queue for pipelined mode - batcher handles task completion
        self._token_batcher = UploadTokenBatcher(self._uploader, self.db, self._task_queue)
        await self._token_batcher.start()

        # Create pipelined upload handler
        # Workers upload bytes and submit tokens without waiting for batchCreate
        # Batcher handles task completion asynchronously
        async def handle_upload(task):
            async with self.db.execute(
                "SELECT local_path FROM files WHERE id = ?", (task.file_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    raise PermanentError(f"File {task.file_id} not found")
                file_path = Path(row[0])

            if not file_path.exists():
                raise PermanentError(f"File missing: {file_path}")

            # Step 1: Upload bytes (parallel across workers)
            upload_token, filename = await self._uploader.upload_bytes_only(file_path)

            # Step 2: Submit to batcher - DON'T WAIT (pipelined)
            # Batcher will call batchCreate and handle task completion
            self._token_batcher.submit_nowait(
                task.id, task.file_id, upload_token, filename
            )

            # Mark task as pipelined - worker should not call complete_task
            task.pipelined = True

        # Start upload worker pool
        upload_workers = await self._get_config_int('parallel_uploads', 4)
        handlers = {TaskType.UPLOAD: handle_upload}
        self._worker_pool = WorkerPool(self._task_queue, handlers, upload_workers)
        await self._worker_pool.start()

    async def _run_pipelined_hash_upload(
        self,
        job_id: int,
        files_to_hash: list,
        pending_upload_ids: list[int],
        hash_workers: int,
        upload_workers: int
    ):
        """
        Pipelined hash + upload:
        - Hash new files in batches of ~1000, queue for upload immediately
        - Also queue existing pending files for upload
        - Upload workers run concurrently with hashing
        """
        logger.info(f"Job {job_id}: {len(files_to_hash)} to hash, {len(pending_upload_ids)} pending upload")

        # Initialize upload pipeline (task queue, uploader, worker pool)
        try:
            await self._init_upload_pipeline(job_id)
        except ValueError as e:
            logger.error(str(e))
            # Still hash files even if we can't upload
            await self._hash_all_files(job_id, files_to_hash, hash_workers)
            return

        batch_size = self._task_queue.batch_size  # Default 100

        # First, queue all pending files for upload (already have hashes)
        if pending_upload_ids:
            logger.info(f"Job {job_id}: Queueing {len(pending_upload_ids)} pending files for upload")
            await self._task_queue.create_work_batches(job_id, pending_upload_ids, TaskType.UPLOAD)

        # Process new files in batches (hash then upload)
        total_hashed = 0
        total_to_hash = len(files_to_hash)
        for batch_start in range(0, total_to_hash, batch_size):
            batch_end = min(batch_start + batch_size, total_to_hash)
            batch_files = files_to_hash[batch_start:batch_end]
            batch_num = batch_start // batch_size + 1

            logger.info(f"Job {job_id}: Hashing batch {batch_num} ({len(batch_files)} files)")

            # Hash this batch
            file_paths = [f.path for f in batch_files]
            hashes = await hash_files(file_paths, workers=hash_workers)

            # Insert into DB and collect file IDs
            file_ids = []
            for file_info in batch_files:
                full_path = str(file_info.path)
                file_hash = hashes.get(file_info.path)

                if not file_hash:
                    continue

                relative_path = file_info.path.name
                source_name = "default"

                for source_dir in self._source_dirs:
                    if full_path.startswith(source_dir):
                        source_name = Path(source_dir).name or "photos"
                        relative_path = full_path[len(source_dir):].lstrip("/\\")
                        break

                cursor = await self.db.execute("""
                    INSERT INTO files (source_name, relative_path, filename, local_path, extension, size, mtime, sha256, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    ON CONFLICT(source_name, relative_path) DO UPDATE SET
                        sha256 = excluded.sha256,
                        size = excluded.size,
                        mtime = excluded.mtime,
                        local_path = excluded.local_path
                    RETURNING id
                """, (
                    source_name,
                    relative_path,
                    file_info.filename,
                    full_path,
                    file_info.extension,
                    file_info.size,
                    file_info.mtime,
                    file_hash
                ))
                row = await cursor.fetchone()
                if row:
                    file_ids.append(row[0])

            await self.db.commit()
            total_hashed += len(file_ids)

            # Create upload work batch immediately
            if file_ids:
                await self._task_queue.create_work_batches(job_id, file_ids, TaskType.UPLOAD)
                logger.info(f"Job {job_id}: Batch {batch_num} queued for upload ({len(file_ids)} files)")

            await self._update_job_progress(job_id, hashed=total_hashed)

        if total_to_hash > 0:
            logger.info(f"Job {job_id}: Hashed {total_hashed} files")
        await self._update_job_status(job_id, 'running', 'uploading')
        logger.info(f"Job {job_id}: Uploading ({len(pending_upload_ids)} pending + {total_hashed} new)")

        # Wait for all uploads to complete
        await self._wait_for_work_batches(job_id)
        await self._worker_pool.stop()

        progress = await self._task_queue.get_job_progress(job_id)
        await self._update_job_progress(
            job_id,
            uploaded=progress["total_succeeded"],
            errors=progress["total_failed"]
        )
        logger.info(f"Job {job_id}: Complete - {progress['total_succeeded']} uploaded, {progress['total_failed']} failed")

    async def _hash_all_files(self, job_id: int, files: list, num_workers: int):
        """Fallback: hash all files without uploading (no credentials)."""
        logger.info(f"Job {job_id}: Hashing {len(files)} files (upload disabled)")
        file_paths = [f.path for f in files]
        hashes = await hash_files(file_paths, workers=num_workers)

        for file_info in files:
            full_path = str(file_info.path)
            file_hash = hashes.get(file_info.path)
            if not file_hash:
                continue

            relative_path = file_info.path.name
            source_name = "default"
            for source_dir in self._source_dirs:
                if full_path.startswith(source_dir):
                    source_name = Path(source_dir).name or "photos"
                    relative_path = full_path[len(source_dir):].lstrip("/\\")
                    break

            await self.db.execute("""
                INSERT INTO files (source_name, relative_path, filename, local_path, extension, size, mtime, sha256, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                ON CONFLICT(source_name, relative_path) DO UPDATE SET
                    sha256 = excluded.sha256, size = excluded.size, mtime = excluded.mtime, local_path = excluded.local_path
            """, (source_name, relative_path, file_info.filename, full_path, file_info.extension, file_info.size, file_info.mtime, file_hash))

        await self.db.commit()
        await self._update_job_progress(job_id, hashed=len(files))


    async def _wait_for_work_batches(self, job_id: int):
        """Wait for all work batches in a job to complete."""
        while True:
            # Update queue metrics for dashboard
            await self._task_queue.update_queue_metrics()

            async with self.db.execute("""
                SELECT COUNT(*) FROM work_batches
                WHERE job_id = ? AND status IN ('pending', 'running')
            """, (job_id,)) as cursor:
                pending = (await cursor.fetchone())[0]

            if pending == 0:
                break

            # Update job progress periodically
            progress = await self._task_queue.get_job_progress(job_id)
            await self._update_job_progress(
                job_id,
                uploaded=progress["total_succeeded"]
            )

            await asyncio.sleep(1)

    async def _update_job_status(self, job_id: int, status: str, phase: str):
        """Update job status in database."""
        if status in ('completed', 'failed', 'cancelled'):
            await self.db.execute(
                "UPDATE jobs SET status = ?, current_phase = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, phase, job_id)
            )
        else:
            await self.db.execute(
                "UPDATE jobs SET status = ?, current_phase = ? WHERE id = ?",
                (status, phase, job_id)
            )
        await self.db.commit()

    async def _update_job_progress(
        self,
        job_id: int,
        scanned: int = None,
        hashed: int = None,
        uploaded: int = None,
        deduplicated: int = None,
        errors: int = None,
        total_bytes: int = None
    ):
        """Update job progress in database."""
        await self.db.execute("""
            UPDATE jobs SET
                files_scanned = COALESCE(?, files_scanned),
                files_hashed = COALESCE(?, files_hashed),
                files_uploaded = COALESCE(?, files_uploaded),
                files_deduplicated = COALESCE(?, files_deduplicated),
                files_errored = COALESCE(?, files_errored),
                bytes_hashed = COALESCE(?, bytes_hashed)
            WHERE id = ?
        """, (scanned, hashed, uploaded, deduplicated, errors, total_bytes, job_id))
        await self.db.commit()


# Global orchestrator instance (set by app startup)
_orchestrator: Optional[SyncOrchestrator] = None


def get_orchestrator() -> Optional[SyncOrchestrator]:
    return _orchestrator


def set_orchestrator(orchestrator: SyncOrchestrator):
    global _orchestrator
    _orchestrator = orchestrator
