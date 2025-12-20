"""
Tests for REST API endpoints.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil


@pytest.fixture
async def temp_dir():
    """Create a temporary directory for test files."""
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
async def test_db(temp_dir):
    """Create a test database with schema."""
    import aiosqlite

    db_path = temp_dir / "test.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Read and execute schema
        schema_path = Path(__file__).parent.parent / "src" / "schema.sql"
        if schema_path.exists():
            schema = schema_path.read_text()
            await db.executescript(schema)
            await db.commit()

        yield db


@pytest.fixture
def sample_image(temp_dir):
    """Create a sample image file."""
    img_path = temp_dir / "test_image.jpg"
    # JPEG magic bytes + some content
    img_path.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 100)
    return img_path


class TestFilePreviewEndpoint:
    """Tests for /api/files/{id}/preview endpoint."""

    @pytest.mark.asyncio
    async def test_preview_returns_image(self, test_db, sample_image):
        """Should serve image file for preview."""
        from web.api import get_file_preview
        from fastapi import Request

        # Insert a test file record
        await test_db.execute("""
            INSERT INTO files (source_name, relative_path, filename, local_path, extension, size, mtime, status)
            VALUES ('test', 'test_image.jpg', 'test_image.jpg', ?, 'jpg', 100, 0, 'pending')
        """, (str(sample_image),))
        await test_db.commit()

        # Get the file ID
        async with test_db.execute("SELECT id FROM files WHERE filename = 'test_image.jpg'") as cursor:
            row = await cursor.fetchone()
            file_id = row['id']

        # Mock the request
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        # Call the endpoint
        response = await get_file_preview(mock_request, file_id)

        # Should return FileResponse
        assert response.path == sample_image
        assert response.media_type == 'image/jpeg'

    @pytest.mark.asyncio
    async def test_preview_returns_404_for_missing_file(self, test_db, temp_dir):
        """Should return 404 if file doesn't exist on disk."""
        from web.api import get_file_preview
        from fastapi import Request, HTTPException

        # Insert a file record pointing to nonexistent file
        missing_path = temp_dir / "missing.jpg"
        await test_db.execute("""
            INSERT INTO files (source_name, relative_path, filename, local_path, extension, size, mtime, status)
            VALUES ('test', 'missing.jpg', 'missing.jpg', ?, 'jpg', 100, 0, 'pending')
        """, (str(missing_path),))
        await test_db.commit()

        async with test_db.execute("SELECT id FROM files WHERE filename = 'missing.jpg'") as cursor:
            row = await cursor.fetchone()
            file_id = row['id']

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        with pytest.raises(HTTPException) as exc_info:
            await get_file_preview(mock_request, file_id)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_returns_404_for_unknown_id(self, test_db):
        """Should return 404 for unknown file ID."""
        from web.api import get_file_preview
        from fastapi import Request, HTTPException

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        with pytest.raises(HTTPException) as exc_info:
            await get_file_preview(mock_request, 99999)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_correct_media_types(self, test_db, temp_dir):
        """Should return correct media types for different extensions."""
        from web.api import get_file_preview
        from fastapi import Request

        extensions = {
            'jpg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'mp4': 'video/mp4',
            'mov': 'video/quicktime',
        }

        for ext, expected_type in extensions.items():
            # Create file
            file_path = temp_dir / f"test.{ext}"
            file_path.write_bytes(b'\x00' * 100)

            # Insert record
            await test_db.execute("""
                INSERT INTO files (source_name, relative_path, filename, local_path, extension, size, mtime, status)
                VALUES ('test', ?, ?, ?, ?, 100, 0, 'pending')
            """, (f"test.{ext}", f"test.{ext}", str(file_path), ext))
            await test_db.commit()

            async with test_db.execute(f"SELECT id FROM files WHERE filename = 'test.{ext}'") as cursor:
                row = await cursor.fetchone()
                file_id = row['id']

            mock_request = MagicMock(spec=Request)
            mock_request.app.state.db = test_db

            response = await get_file_preview(mock_request, file_id)
            assert response.media_type == expected_type, f"Expected {expected_type} for .{ext}"


class TestDeleteJobEndpoint:
    """Tests for DELETE /api/jobs/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_completed_job(self, test_db):
        """Should delete a completed job."""
        from web.api import delete_job
        from fastapi import Request

        # Insert a completed job
        await test_db.execute("""
            INSERT INTO jobs (source_dirs, status, current_phase)
            VALUES ('[]', 'completed', 'done')
        """)
        await test_db.commit()

        async with test_db.execute("SELECT id FROM jobs LIMIT 1") as cursor:
            row = await cursor.fetchone()
            job_id = row['id']

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        result = await delete_job(mock_request, job_id)

        assert result['deleted'] == job_id

        # Verify job is gone
        async with test_db.execute("SELECT COUNT(*) as count FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            assert row['count'] == 0

    @pytest.mark.asyncio
    async def test_cannot_delete_running_job(self, test_db):
        """Should not delete an active job."""
        from web.api import delete_job
        from fastapi import Request, HTTPException

        await test_db.execute("""
            INSERT INTO jobs (source_dirs, status, current_phase)
            VALUES ('[]', 'running', 'scanning')
        """)
        await test_db.commit()

        async with test_db.execute("SELECT id FROM jobs LIMIT 1") as cursor:
            row = await cursor.fetchone()
            job_id = row['id']

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        with pytest.raises(HTTPException) as exc_info:
            await delete_job(mock_request, job_id)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_nonexistent_job(self, test_db):
        """Should return 404 for nonexistent job."""
        from web.api import delete_job
        from fastapi import Request, HTTPException

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        with pytest.raises(HTTPException) as exc_info:
            await delete_job(mock_request, 99999)

        assert exc_info.value.status_code == 404


class TestCleanupJobsEndpoint:
    """Tests for DELETE /api/jobs/cleanup endpoint."""

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs(self, test_db):
        """Should delete old completed jobs."""
        from web.api import cleanup_old_jobs
        from fastapi import Request

        # Insert some old completed jobs
        await test_db.execute("""
            INSERT INTO jobs (source_dirs, status, started_at)
            VALUES ('[]', 'completed', datetime('now', '-10 days'))
        """)
        await test_db.execute("""
            INSERT INTO jobs (source_dirs, status, started_at)
            VALUES ('[]', 'failed', datetime('now', '-10 days'))
        """)
        # Recent job that should NOT be deleted
        await test_db.execute("""
            INSERT INTO jobs (source_dirs, status, started_at)
            VALUES ('[]', 'completed', datetime('now'))
        """)
        await test_db.commit()

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        result = await cleanup_old_jobs(mock_request, days=7, status='all')

        assert result['deleted'] == 2

        # Verify recent job still exists
        async with test_db.execute("SELECT COUNT(*) as count FROM jobs") as cursor:
            row = await cursor.fetchone()
            assert row['count'] == 1

    @pytest.mark.asyncio
    async def test_cleanup_does_not_delete_active_jobs(self, test_db):
        """Should not delete active jobs even if old."""
        from web.api import cleanup_old_jobs
        from fastapi import Request

        await test_db.execute("""
            INSERT INTO jobs (source_dirs, status, started_at)
            VALUES ('[]', 'running', datetime('now', '-10 days'))
        """)
        await test_db.commit()

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        result = await cleanup_old_jobs(mock_request, days=7, status='all')

        assert result['deleted'] == 0


class TestFileSearchEndpoint:
    """Tests for /api/files search functionality."""

    @pytest.mark.asyncio
    async def test_search_by_filename(self, test_db):
        """Should find files by filename."""
        from web.api import list_files
        from fastapi import Request

        await test_db.execute("""
            INSERT INTO files (source_name, relative_path, filename, extension, size, mtime, status)
            VALUES
                ('test', '2024/vacation/beach.jpg', 'beach.jpg', 'jpg', 100, 0, 'pending'),
                ('test', '2024/work/meeting.jpg', 'meeting.jpg', 'jpg', 100, 0, 'pending'),
                ('test', '2024/vacation/sunset.jpg', 'sunset.jpg', 'jpg', 100, 0, 'pending')
        """)
        await test_db.commit()

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        result = await list_files(mock_request, page=1, limit=50, search='beach', status='')

        assert result['total'] == 1
        assert result['files'][0]['filename'] == 'beach.jpg'

    @pytest.mark.asyncio
    async def test_search_by_path(self, test_db):
        """Should find files by relative path."""
        from web.api import list_files
        from fastapi import Request

        await test_db.execute("""
            INSERT INTO files (source_name, relative_path, filename, extension, size, mtime, status)
            VALUES
                ('test', '2024/vacation/beach.jpg', 'beach.jpg', 'jpg', 100, 0, 'pending'),
                ('test', '2024/work/meeting.jpg', 'meeting.jpg', 'jpg', 100, 0, 'pending'),
                ('test', '2024/vacation/sunset.jpg', 'sunset.jpg', 'jpg', 100, 0, 'pending')
        """)
        await test_db.commit()

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        result = await list_files(mock_request, page=1, limit=50, search='vacation', status='')

        assert result['total'] == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(self, test_db):
        """Should filter files by status."""
        from web.api import list_files
        from fastapi import Request

        await test_db.execute("""
            INSERT INTO files (source_name, relative_path, filename, extension, size, mtime, status)
            VALUES
                ('test', 'a.jpg', 'a.jpg', 'jpg', 100, 0, 'pending'),
                ('test', 'b.jpg', 'b.jpg', 'jpg', 100, 0, 'uploaded'),
                ('test', 'c.jpg', 'c.jpg', 'jpg', 100, 0, 'error')
        """)
        await test_db.commit()

        mock_request = MagicMock(spec=Request)
        mock_request.app.state.db = test_db

        result = await list_files(mock_request, page=1, limit=50, search='', status='error')

        assert result['total'] == 1
        assert result['files'][0]['status'] == 'error'
