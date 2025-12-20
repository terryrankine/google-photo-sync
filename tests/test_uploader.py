"""
Tests for Google Photos uploader.
"""

import pytest
from pathlib import Path
import aiohttp
from unittest.mock import AsyncMock, patch, MagicMock


class TestUploader:
    """Test uploader functionality."""

    @pytest.mark.asyncio
    async def test_upload_success(self, sample_photos, mock_api):
        """Should successfully upload a file."""
        from src.uploader import GooglePhotosUploader, UploadResult

        with patch.object(GooglePhotosUploader, '_upload_bytes') as mock_upload:
            with patch.object(GooglePhotosUploader, '_create_media_item') as mock_create:
                mock_upload.return_value = "upload_token_123"
                mock_create.return_value = ("media_id_456", False)

                uploader = GooglePhotosUploader(
                    credentials_path=Path("/fake/creds.json"),
                    token_path=Path("/fake/token.json")
                )
                uploader._session = MagicMock()
                uploader._access_token = "test_token"

                result = await uploader.upload_file(sample_photos[0])

                assert result.success is True
                assert result.media_id == "media_id_456"

    @pytest.mark.asyncio
    async def test_upload_detects_deduplication(self, sample_photos):
        """Should detect when Google deduplicates."""
        from src.uploader import GooglePhotosUploader

        with patch.object(GooglePhotosUploader, '_upload_bytes') as mock_upload:
            with patch.object(GooglePhotosUploader, '_create_media_item') as mock_create:
                mock_upload.return_value = "upload_token_123"
                mock_create.return_value = ("existing_media_id", True)  # was_deduplicated=True

                uploader = GooglePhotosUploader(
                    credentials_path=Path("/fake/creds.json"),
                    token_path=Path("/fake/token.json")
                )
                uploader._session = MagicMock()
                uploader._access_token = "test_token"

                result = await uploader.upload_file(sample_photos[0])

                assert result.success is True
                assert result.was_deduplicated is True

    @pytest.mark.asyncio
    async def test_upload_handles_rate_limit(self, sample_photos):
        """Should raise RetryableError on rate limit."""
        from src.uploader import GooglePhotosUploader
        from src.task_queue import RetryableError

        uploader = GooglePhotosUploader(
            credentials_path=Path("/fake/creds.json"),
            token_path=Path("/fake/token.json")
        )
        uploader._access_token = "test_token"

        # Mock session to return 429
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.text = AsyncMock(return_value="Rate limited")
        mock_response.headers = {"Retry-After": "60"}

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        uploader._session = mock_session

        with pytest.raises(RetryableError):
            await uploader._check_response(mock_response)

    @pytest.mark.asyncio
    async def test_upload_handles_timeout(self, sample_photos):
        """Should raise RetryableError on timeout."""
        from src.uploader import GooglePhotosUploader
        from src.task_queue import RetryableError
        import asyncio

        uploader = GooglePhotosUploader(
            credentials_path=Path("/fake/creds.json"),
            token_path=Path("/fake/token.json")
        )
        uploader._session = MagicMock()
        uploader._access_token = "test_token"

        with patch.object(uploader, '_upload_bytes', side_effect=asyncio.TimeoutError()):
            with pytest.raises(RetryableError) as exc_info:
                await uploader.upload_file(sample_photos[0])

            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_upload_handles_missing_file(self, temp_dir):
        """Should raise PermanentError for missing file."""
        from src.uploader import GooglePhotosUploader
        from src.task_queue import PermanentError

        uploader = GooglePhotosUploader(
            credentials_path=Path("/fake/creds.json"),
            token_path=Path("/fake/token.json")
        )

        missing = temp_dir / "nonexistent.jpg"

        with pytest.raises(PermanentError):
            await uploader.upload_file(missing)

    @pytest.mark.asyncio
    async def test_batch_upload_respects_concurrency(self, sample_photos):
        """Batch upload should respect concurrency limit."""
        from src.uploader import GooglePhotosUploader, UploadResult
        import asyncio

        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def mock_upload(self, filepath):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)

            await asyncio.sleep(0.1)

            async with lock:
                concurrent_count -= 1

            return UploadResult(success=True, media_id="test")

        with patch.object(GooglePhotosUploader, 'upload_file', mock_upload):
            uploader = GooglePhotosUploader(
                credentials_path=Path("/fake/creds.json"),
                token_path=Path("/fake/token.json")
            )

            await uploader.upload_batch(sample_photos, concurrency=2)

            # Should never exceed concurrency limit
            assert max_concurrent <= 2


class TestRateLimiter:
    """Test rate limiter functionality."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_burst(self):
        """Should allow burst of requests."""
        from src.uploader import RateLimiter
        import time

        limiter = RateLimiter(requests_per_second=10, burst_size=5)

        start = time.time()
        for _ in range(5):
            await limiter.acquire()
        elapsed = time.time() - start

        # Burst should be nearly instant
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_rate_limiter_throttles_after_burst(self):
        """Should throttle after burst is exhausted."""
        from src.uploader import RateLimiter
        import time

        limiter = RateLimiter(requests_per_second=10, burst_size=2)

        # Exhaust burst
        await limiter.acquire()
        await limiter.acquire()

        # Next request should be throttled
        start = time.time()
        await limiter.acquire()
        elapsed = time.time() - start

        # Should wait approximately 0.1s (1/10 rps)
        assert elapsed >= 0.05


class TestProgressTracker:
    """Test upload progress tracking."""

    @pytest.mark.asyncio
    async def test_progress_calculation(self):
        """Should calculate progress correctly."""
        from src.uploader import UploadProgressTracker

        tracker = UploadProgressTracker(
            total_files=100,
            total_bytes=1000000
        )

        await tracker.record_success(10000)
        await tracker.record_success(10000)

        assert tracker.completed_files == 2
        assert tracker.completed_bytes == 20000
        assert tracker.progress_percent == 2.0

    @pytest.mark.asyncio
    async def test_speed_calculation(self):
        """Should calculate upload speed."""
        from src.uploader import UploadProgressTracker
        import asyncio

        tracker = UploadProgressTracker(
            total_files=100,
            total_bytes=1000000
        )

        await tracker.record_success(100000)
        await asyncio.sleep(0.1)

        speed = tracker.bytes_per_second
        assert speed > 0

    @pytest.mark.asyncio
    async def test_eta_calculation(self):
        """Should estimate time remaining."""
        from src.uploader import UploadProgressTracker
        import asyncio

        tracker = UploadProgressTracker(
            total_files=100,
            total_bytes=1000000
        )

        await tracker.record_success(100000)  # 10%
        await asyncio.sleep(0.1)

        eta = tracker.eta_seconds
        assert eta > 0
        assert eta < float('inf')
