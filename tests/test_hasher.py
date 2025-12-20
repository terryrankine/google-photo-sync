"""
Tests for file hashing.
"""

import pytest
from pathlib import Path
import hashlib


class TestHasher:
    """Test file hashing functionality."""

    @pytest.mark.asyncio
    async def test_hash_single_file(self, sample_photos):
        """Should compute correct SHA256 hash."""
        from src.hasher import hash_file

        result = await hash_file(sample_photos[0])

        # Verify hash manually
        expected = hashlib.sha256(sample_photos[0].read_bytes()).hexdigest()
        assert result == expected

    @pytest.mark.asyncio
    async def test_hash_multiple_files(self, sample_photos):
        """Should hash multiple files in parallel."""
        from src.hasher import hash_files

        results = await hash_files(sample_photos, workers=4)

        assert len(results) == len(sample_photos)
        for path, file_hash in results.items():
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            assert file_hash == expected

    @pytest.mark.asyncio
    async def test_hash_detects_duplicates(self, temp_dir):
        """Should produce same hash for identical content."""
        from src.hasher import hash_file

        # Create two files with identical content
        content = b'\xff\xd8\xff\xe0' + b'identical content'
        file1 = temp_dir / "photo1.jpg"
        file2 = temp_dir / "photo2.jpg"
        file1.write_bytes(content)
        file2.write_bytes(content)

        hash1 = await hash_file(file1)
        hash2 = await hash_file(file2)

        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_hash_different_for_different_content(self, temp_dir):
        """Should produce different hashes for different content."""
        from src.hasher import hash_file

        file1 = temp_dir / "photo1.jpg"
        file2 = temp_dir / "photo2.jpg"
        file1.write_bytes(b'\xff\xd8\xff\xe0' + b'content A')
        file2.write_bytes(b'\xff\xd8\xff\xe0' + b'content B')

        hash1 = await hash_file(file1)
        hash2 = await hash_file(file2)

        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_hash_performance(self, temp_dir):
        """Hashing should be reasonably fast."""
        from src.hasher import hash_files
        import time

        # Create 100 files of 1MB each
        files = []
        for i in range(100):
            path = temp_dir / f"large_{i:03d}.jpg"
            path.write_bytes(b'\xff\xd8' + bytes(1024 * 1024))  # 1MB
            files.append(path)

        start = time.time()
        results = await hash_files(files, workers=4)
        elapsed = time.time() - start

        assert len(results) == 100
        # 100MB should hash in under 5 seconds on modern hardware
        assert elapsed < 5.0, f"Hash took {elapsed:.2f}s, expected <5s"

    @pytest.mark.asyncio
    async def test_hash_handles_missing_file(self, temp_dir):
        """Should handle missing files gracefully."""
        from src.hasher import hash_file

        missing = temp_dir / "nonexistent.jpg"

        with pytest.raises(FileNotFoundError):
            await hash_file(missing)

    @pytest.mark.asyncio
    async def test_hash_streaming_large_file(self, temp_dir):
        """Should stream large files to avoid memory issues."""
        from src.hasher import hash_file
        import tracemalloc

        # Create 50MB file
        large_file = temp_dir / "large.jpg"
        large_file.write_bytes(b'\xff\xd8' + bytes(50 * 1024 * 1024))

        tracemalloc.start()
        result = await hash_file(large_file)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert result is not None
        # Peak memory should be well under file size (streaming works)
        assert peak < 20 * 1024 * 1024, f"Peak memory {peak / 1024 / 1024:.1f}MB too high"
