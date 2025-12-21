"""
Tests for filesystem scanner.
"""

import pytest
from pathlib import Path
import time


class TestScanner:
    """Test filesystem scanning functionality."""

    @pytest.mark.asyncio
    async def test_scan_finds_all_photos(self, sample_structure):
        """Scanner should find all photo files."""
        from src.scanner import scan_directory

        result = await scan_directory(sample_structure)

        # Should find 7 photos (excluding .thumbnails)
        assert len(result.files) == 7

    @pytest.mark.asyncio
    async def test_scan_ignores_thumbnails(self, sample_structure):
        """Scanner should ignore .thumbnails directory."""
        from src.scanner import scan_directory

        result = await scan_directory(
            sample_structure,
            ignore_patterns=[".thumbnails"]
        )

        # Check no files from .thumbnails
        for f in result.files:
            assert ".thumbnails" not in str(f.path)

    @pytest.mark.asyncio
    async def test_scan_filters_extensions(self, sample_structure):
        """Scanner should filter by file extension."""
        from src.scanner import scan_directory

        result = await scan_directory(
            sample_structure,
            extensions=["jpg", "jpeg"]
        )

        # Should only find .jpg files
        for f in result.files:
            assert f.path.suffix.lower() in [".jpg", ".jpeg"]

    @pytest.mark.asyncio
    async def test_scan_detects_unchanged_files(self, sample_photos, test_db):
        """Scanner should detect files that haven't changed."""
        from src.scanner import scan_directory, FileInfo

        # First scan
        result1 = await scan_directory(sample_photos[0].parent)

        # Simulate storing in DB with correct column names (including sha256 to mark as hashed)
        for f in result1.files:
            await test_db.execute(
                """INSERT INTO files (source_name, relative_path, filename, local_path, extension, mtime, size, status, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test", f.path.name, f.path.name, str(f.path), f.extension, f.mtime, f.size, "uploaded", "fakehash123")
            )
        await test_db.commit()

        # Second scan with DB check
        result2 = await scan_directory(
            sample_photos[0].parent,
            db=test_db
        )

        # All files should be marked as unchanged
        assert result2.unchanged_count == len(sample_photos)
        assert len(result2.needs_hash) == 0

    @pytest.mark.asyncio
    async def test_scan_detects_modified_files(self, sample_photos, test_db):
        """Scanner should detect files that have been modified."""
        from src.scanner import scan_directory

        # First scan and store with correct column names (including sha256 to mark as hashed)
        result1 = await scan_directory(sample_photos[0].parent)
        for f in result1.files:
            await test_db.execute(
                """INSERT INTO files (source_name, relative_path, filename, local_path, extension, mtime, size, status, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test", f.path.name, f.path.name, str(f.path), f.extension, f.mtime, f.size, "uploaded", "fakehash123")
            )
        await test_db.commit()

        # Modify one file
        time.sleep(0.1)  # Ensure mtime changes
        sample_photos[0].write_bytes(b'\xff\xd8\xff\xe0' + b'modified')

        # Second scan
        result2 = await scan_directory(
            sample_photos[0].parent,
            db=test_db
        )

        # One file should need rehashing
        assert len(result2.needs_hash) == 1
        assert result2.needs_hash[0].path == sample_photos[0]

    @pytest.mark.asyncio
    async def test_scan_performance(self, temp_dir):
        """Scanner should be fast for large directories."""
        # Create 1000 files
        for i in range(1000):
            (temp_dir / f"photo_{i:04d}.jpg").write_bytes(b'\xff\xd8' + bytes(100))

        from src.scanner import scan_directory
        import time

        start = time.time()
        result = await scan_directory(temp_dir)
        elapsed = time.time() - start

        assert len(result.files) == 1000
        # Should complete in under 1 second
        assert elapsed < 1.0, f"Scan took {elapsed:.2f}s, expected <1s"
