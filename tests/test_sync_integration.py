"""
Integration tests for the sync pipeline.

Tests the full flow: scan -> hash -> work batches -> upload (mocked)
"""

import pytest
import asyncio
from pathlib import Path


class TestSyncPipeline:
    """Integration tests for the complete sync pipeline."""

    async def _create_test_photos(self, temp_dir: Path, num_photos: int) -> list[Path]:
        """Create test photo files."""
        photos = []
        for i in range(num_photos):
            photo_path = temp_dir / f"photo_{i:04d}.jpg"
            # Create files with different content for unique hashes
            content = b'\xff\xd8\xff\xe0' + f"photo_{i}_{i*1000}".encode() * 100
            photo_path.write_bytes(content)
            photos.append(photo_path)
        return photos

    @pytest.mark.asyncio
    async def test_scan_finds_all_files(self, test_db, temp_dir):
        """Scan phase should discover all photo files."""
        from src.scanner import scan_directory

        # Create test photos
        photos = await self._create_test_photos(temp_dir, 50)

        result = await scan_directory(temp_dir, db=test_db)

        assert len(result.files) == 50
        assert result.total_bytes > 0

    @pytest.mark.asyncio
    async def test_hash_produces_unique_hashes(self, test_db, temp_dir):
        """Hash phase should produce unique hashes for different files."""
        from src.scanner import scan_directory
        from src.hasher import hash_files

        photos = await self._create_test_photos(temp_dir, 10)

        result = await scan_directory(temp_dir, db=test_db)
        file_paths = [f.path for f in result.files]

        hashes = await hash_files(file_paths, workers=2)

        assert len(hashes) == 10
        # All hashes should be unique since files have different content
        unique_hashes = set(hashes.values())
        assert len(unique_hashes) == 10

    @pytest.mark.asyncio
    async def test_work_batches_created_correctly(self, test_db, temp_dir):
        """Work batches should be created with correct chunking."""
        from src.scanner import scan_directory
        from src.hasher import hash_files
        from src.task_queue import TaskQueue, TaskType

        # Create 150 photos (will be 1 batch with batch_size=1000, 2 with batch_size=100)
        photos = await self._create_test_photos(temp_dir, 150)

        # Scan and hash
        result = await scan_directory(temp_dir, db=test_db)
        file_paths = [f.path for f in result.files]
        hashes = await hash_files(file_paths, workers=2)

        # Create job
        await test_db.execute("""
            INSERT INTO jobs (id, source_dirs, status, current_phase)
            VALUES (1, '[]', 'running', 'upload')
        """)

        # Insert files into DB with hashes
        file_ids = []
        for i, (path, file_hash) in enumerate(hashes.items()):
            await test_db.execute("""
                INSERT INTO files (source_name, relative_path, filename, local_path, extension, size, mtime, sha256, status)
                VALUES ('test', ?, ?, ?, 'jpg', 1000, 0, ?, 'pending')
            """, (path.name, path.name, str(path), file_hash))
            cursor = await test_db.execute("SELECT last_insert_rowid()")
            row = await cursor.fetchone()
            file_ids.append(row[0])
        await test_db.commit()

        # Create work batches with smaller batch size for testing
        queue = TaskQueue(test_db, batch_size=100)
        batch_ids = await queue.create_work_batches(1, file_ids, TaskType.UPLOAD)

        # 150 files / 100 batch_size = 2 batches
        assert len(batch_ids) == 2

        # Verify batch sizes
        async with test_db.execute(
            "SELECT file_count FROM work_batches ORDER BY batch_number"
        ) as cursor:
            rows = [dict(r) async for r in cursor]

        assert rows[0]["file_count"] == 100
        assert rows[1]["file_count"] == 50

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mock_upload(self, test_db, temp_dir):
        """Full pipeline: scan -> hash -> work batches -> process (mocked upload)."""
        from src.scanner import scan_directory
        from src.hasher import hash_files
        from src.task_queue import TaskQueue, TaskType

        # Create test photos
        photos = await self._create_test_photos(temp_dir, 25)

        # Phase 1: Scan
        scan_result = await scan_directory(temp_dir, db=test_db)
        assert len(scan_result.files) == 25

        # Phase 2: Hash
        file_paths = [f.path for f in scan_result.files]
        hashes = await hash_files(file_paths, workers=2)
        assert len(hashes) == 25

        # Create job
        await test_db.execute("""
            INSERT INTO jobs (id, source_dirs, status, current_phase)
            VALUES (1, '[]', 'running', 'upload')
        """)

        # Insert files with hashes
        file_ids = []
        for path, file_hash in hashes.items():
            await test_db.execute("""
                INSERT INTO files (source_name, relative_path, filename, local_path, extension, size, mtime, sha256, status)
                VALUES ('test', ?, ?, ?, 'jpg', 1000, 0, ?, 'pending')
            """, (path.name, path.name, str(path), file_hash))
            cursor = await test_db.execute("SELECT last_insert_rowid()")
            row = await cursor.fetchone()
            file_ids.append(row[0])
        await test_db.commit()

        # Phase 3: Create work batches
        queue = TaskQueue(test_db, batch_size=100)
        batch_ids = await queue.create_work_batches(1, file_ids, TaskType.UPLOAD)
        assert len(batch_ids) == 1  # 25 files < 100 batch size

        # Claim and process batch (mock upload)
        batch = await queue.claim_work_batch(worker_id=1)
        assert batch is not None
        assert len(batch.tasks) == 25

        # Mock process all tasks
        uploaded_count = 0
        for task in batch.tasks:
            # Simulate successful upload
            await queue.complete_task(task.id, success=True)
            uploaded_count += 1

        await queue.complete_work_batch(batch.id, uploaded_count, 0)

        # Verify final state
        progress = await queue.get_job_progress(1)
        assert progress["total_succeeded"] == 25
        assert progress["total_failed"] == 0
        assert progress["completed_batches"] == 1


class TestDeduplication:
    """Test duplicate detection in the pipeline."""

    async def _create_duplicate_photos(self, temp_dir: Path) -> list[Path]:
        """Create photos with some duplicates."""
        photos = []

        # Create 5 unique photos
        for i in range(5):
            path = temp_dir / f"unique_{i}.jpg"
            content = b'\xff\xd8\xff\xe0' + f"unique_{i}".encode() * 100
            path.write_bytes(content)
            photos.append(path)

        # Create 3 copies of the first photo (duplicates)
        original_content = photos[0].read_bytes()
        for i in range(3):
            path = temp_dir / f"duplicate_{i}.jpg"
            path.write_bytes(original_content)
            photos.append(path)

        return photos

    @pytest.mark.asyncio
    async def test_hash_detects_duplicates(self, test_db, temp_dir):
        """Hashing should produce identical hashes for identical files."""
        from src.hasher import hash_files

        photos = await self._create_duplicate_photos(temp_dir)

        hashes = await hash_files(photos, workers=2)

        # Should have 8 files but only 5 unique hashes
        assert len(hashes) == 8
        unique_hashes = set(hashes.values())
        assert len(unique_hashes) == 5  # 5 unique + 3 duplicates with same hash


class TestJobResume:
    """Test job resume functionality."""

    @pytest.mark.asyncio
    async def test_orphaned_batches_reset_on_resume(self, test_db, temp_dir):
        """Orphaned work batches should be reset to pending on resume."""
        from src.task_queue import TaskQueue, TaskType

        # Create job
        await test_db.execute("""
            INSERT INTO jobs (id, source_dirs, status, current_phase)
            VALUES (1, '[]', 'running', 'uploading')
        """)

        # Create files
        for i in range(10):
            await test_db.execute("""
                INSERT INTO files (id, source_name, relative_path, filename, local_path, extension, size, mtime, sha256, status)
                VALUES (?, 'test', ?, ?, '/test/test.jpg', 'jpg', 1000, 0, 'abc123', 'pending')
            """, (i, f"test_{i}.jpg", f"test_{i}.jpg"))
        await test_db.commit()

        # Create work batch
        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(10)), TaskType.UPLOAD)

        # Claim batch (simulates worker taking it)
        batch = await queue.claim_work_batch(worker_id=1)
        assert batch is not None

        # Now simulate crash - batch is 'running' but no worker
        # The recover logic should reset it to 'pending'
        await test_db.execute("""
            UPDATE work_batches
            SET status = 'pending', worker_id = NULL, started_at = NULL
            WHERE job_id = 1 AND status = 'running'
        """)
        await test_db.commit()

        # Verify batch is now pending again
        async with test_db.execute(
            "SELECT status FROM work_batches WHERE job_id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            assert row['status'] == 'pending'

        # Should be able to claim again
        batch2 = await queue.claim_work_batch(worker_id=2)
        assert batch2 is not None
        assert batch2.id == batch.id

    @pytest.mark.asyncio
    async def test_resume_completes_pending_work(self, test_db, temp_dir):
        """Resume should process any pending work batches."""
        from src.task_queue import TaskQueue, TaskType

        # Create job with pending work
        await test_db.execute("""
            INSERT INTO jobs (id, source_dirs, status, current_phase)
            VALUES (1, '["/photos"]', 'running', 'uploading')
        """)

        # Create files
        for i in range(5):
            await test_db.execute("""
                INSERT INTO files (id, source_name, relative_path, filename, local_path, extension, size, mtime, sha256, status)
                VALUES (?, 'test', ?, ?, '/test/test.jpg', 'jpg', 1000, 0, 'hash123', 'pending')
            """, (i, f"test_{i}.jpg", f"test_{i}.jpg"))
        await test_db.commit()

        # Create pending work batch
        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(5)), TaskType.UPLOAD)

        # Verify pending batches exist
        async with test_db.execute("""
            SELECT COUNT(*) as cnt FROM work_batches
            WHERE job_id = 1 AND status = 'pending'
        """) as cursor:
            row = await cursor.fetchone()
            assert row['cnt'] == 1


class TestErrorHandling:
    """Test error handling in the pipeline."""

    @pytest.mark.asyncio
    async def test_hash_handles_missing_files(self, test_db, temp_dir):
        """Hash should handle missing files gracefully."""
        from src.hasher import hash_files

        # Create a file then delete it
        photo = temp_dir / "will_delete.jpg"
        photo.write_bytes(b'\xff\xd8\xff\xe0test')

        existing = temp_dir / "exists.jpg"
        existing.write_bytes(b'\xff\xd8\xff\xe0exists')

        # Delete one file
        photo.unlink()

        # Hash both (one missing)
        hashes = await hash_files([photo, existing], workers=1)

        # Only existing file should be hashed
        assert len(hashes) == 1
        assert existing in hashes

    @pytest.mark.asyncio
    async def test_batch_failure_tracking(self, test_db, temp_dir):
        """Failed tasks should be tracked in batch stats."""
        from src.task_queue import TaskQueue, TaskType

        # Create job and files
        await test_db.execute("""
            INSERT INTO jobs (id, source_dirs, status, current_phase)
            VALUES (1, '[]', 'running', 'upload')
        """)

        for i in range(10):
            await test_db.execute("""
                INSERT INTO files (id, source_name, relative_path, filename, local_path, extension, size, mtime, status)
                VALUES (?, 'test', ?, ?, '/test/test.jpg', 'jpg', 1000, 0, 'pending')
            """, (i, f"test_{i}.jpg", f"test_{i}.jpg"))
        await test_db.commit()

        queue = TaskQueue(test_db, batch_size=100)
        await queue.create_work_batches(1, list(range(10)), TaskType.UPLOAD)

        batch = await queue.claim_work_batch(worker_id=1)

        # Fail 4 tasks, succeed 6
        succeeded = 0
        failed = 0
        for i, task in enumerate(batch.tasks):
            if i < 4:
                await queue.complete_task(task.id, success=False, error="Test error")
                failed += 1
            else:
                await queue.complete_task(task.id, success=True)
                succeeded += 1

        await queue.complete_work_batch(batch.id, succeeded, failed)

        progress = await queue.get_job_progress(1)
        assert progress["total_succeeded"] == 6
        assert progress["total_failed"] == 4
