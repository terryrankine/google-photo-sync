"""
Google Photos Uploader

Handles authentication and uploads to Google Photos with:
- Robust error handling
- Retry logic for transient failures
- Rate limiting
- Timeout management
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
import aiohttp
import aiofiles
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json

from .task_queue import RetryableError, PermanentError, circuit_breaker


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests."""
    pass


from .auth import TokenManager

logger = logging.getLogger(__name__)


# Error categories
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
PERMANENT_STATUSES = {400, 401, 403, 404}


@dataclass
class UploadResult:
    success: bool
    media_id: Optional[str] = None
    error: Optional[str] = None
    was_deduplicated: bool = False


@dataclass
class RateLimiter:
    """Token bucket rate limiter."""
    requests_per_second: float = 30.0  # Google Photos allows ~50/s
    burst_size: int = 50
    _tokens: float = field(default=None, init=False)
    _last_update: datetime = field(default=None, init=False)

    def __post_init__(self):
        self._tokens = float(self.burst_size)

    async def acquire(self):
        """Wait until a request token is available."""
        if self._last_update is None:
            self._last_update = datetime.now()
            self._tokens -= 1  # First call still consumes a token
            return

        now = datetime.now()
        elapsed = (now - self._last_update).total_seconds()
        self._tokens = min(
            self.burst_size,
            self._tokens + elapsed * self.requests_per_second
        )
        self._last_update = now

        if self._tokens < 1:
            wait_time = (1 - self._tokens) / self.requests_per_second
            logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            self._tokens = 0
        else:
            self._tokens -= 1


class GooglePhotosUploader:
    """
    Client for uploading to Google Photos.

    Handles:
    - OAuth2 authentication
    - Media upload (resumable for large files)
    - Error handling and retries
    - Rate limiting
    - Deduplication detection (tracks known media_ids)
    """

    UPLOAD_URL = "https://photoslibrary.googleapis.com/v1/uploads"
    CREATE_URL = "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate"
    CHUNK_SIZE = 32 * 1024 * 1024  # 32MB chunks for resumable upload
    TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(self, credentials_path: Path, token_path: Path, known_media_ids: set = None):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._session: Optional[aiohttp.ClientSession] = None
        self._token_manager = TokenManager(credentials_path, token_path)
        self._rate_limiter = RateLimiter()
        # Track known media_ids to detect deduplication
        self._known_media_ids = known_media_ids or set()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        """Initialize HTTP session and authenticate."""
        timeout = aiohttp.ClientTimeout(total=self.TIMEOUT_SECONDS)
        self._session = aiohttp.ClientSession(timeout=timeout)
        await self._token_manager.load_credentials()
        await self._token_manager.get_valid_token(self._session)

        # Verify token actually works with a test API call
        await self._verify_auth()

    async def _verify_auth(self):
        """Verify authentication by checking token info with Google."""
        token = await self._token_manager.get_valid_token(self._session)

        # Use Google's tokeninfo endpoint to verify the token is valid
        # This works regardless of scope
        async with self._session.get(
            f"https://oauth2.googleapis.com/tokeninfo?access_token={token}"
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise PermanentError(f"Google Photos authentication failed - token invalid: {body[:200]}")

            token_info = await response.json()
            scope = token_info.get('scope', '')

            if 'photoslibrary' not in scope:
                raise PermanentError(f"Token missing photoslibrary scope. Has: {scope}")

        logger.info("Google Photos authentication verified")

    async def close(self):
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _get_headers(self) -> dict:
        """Get headers with current access token."""
        token = await self._token_manager.get_valid_token(self._session)
        if not token:
            raise PermanentError("Not authenticated")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        }

    async def upload_file(self, filepath: Path) -> UploadResult:
        """
        Upload a single file to Google Photos.

        Two-step process:
        1. Upload raw bytes -> get upload token
        2. Create media item with upload token -> get media ID
        """
        if not filepath.exists():
            raise PermanentError(f"File not found: {filepath}")

        file_size = filepath.stat().st_size
        filename = filepath.name

        try:
            # Respect rate limits
            await self._rate_limiter.acquire()

            # Step 1: Upload bytes
            upload_token = await self._upload_bytes(filepath, file_size)

            # Step 2: Create media item
            await self._rate_limiter.acquire()
            media_id, was_dedup = await self._create_media_item(upload_token, filename)

            logger.info(f"Uploaded {filename} -> {media_id}" +
                       (" (deduplicated)" if was_dedup else ""))

            return UploadResult(
                success=True,
                media_id=media_id,
                was_deduplicated=was_dedup
            )

        except aiohttp.ClientError as e:
            return self._handle_client_error(e, filepath)
        except asyncio.TimeoutError:
            raise RetryableError(f"Upload timeout: {filepath}")

    async def _upload_bytes(self, filepath: Path, file_size: int) -> str:
        """Upload file bytes and return upload token."""
        headers = await self._get_headers()
        headers["X-Goog-Upload-File-Name"] = filepath.name
        headers["X-Goog-Upload-Protocol"] = "raw"

        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()

        async with self._session.post(
            self.UPLOAD_URL,
            headers=headers,
            data=data
        ) as response:
            await self._check_response(response)
            return await response.text()

    async def _create_media_item(
        self,
        upload_token: str,
        filename: str,
        album_id: Optional[str] = None
    ) -> tuple[str, bool]:
        """Create media item from upload token. Returns (media_id, was_deduplicated)."""
        results = await self._create_media_items_batch(
            [(upload_token, filename)],
            album_id
        )
        return results[0]

    async def _create_media_items_batch(
        self,
        items: list[tuple[str, str]],  # [(upload_token, filename), ...]
        album_id: Optional[str] = None
    ) -> list[tuple[str, bool]]:
        """
        Create multiple media items in a single batchCreate call.

        Google Photos API supports up to 50 items per batchCreate.
        Returns list of (media_id, was_deduplicated) tuples.
        """
        if not items:
            return []

        if len(items) > 50:
            raise ValueError("batchCreate supports max 50 items")

        headers = await self._get_headers()
        headers["Content-Type"] = "application/json"

        body = {
            "newMediaItems": [
                {
                    "simpleMediaItem": {
                        "uploadToken": token,
                        "fileName": filename
                    }
                }
                for token, filename in items
            ]
        }

        if album_id:
            body["albumId"] = album_id

        async with self._session.post(
            self.CREATE_URL,
            headers=headers,
            json=body
        ) as response:
            await self._check_response(response)
            result = await response.json()

        # Parse all results
        results = []
        for item_result in result.get("newMediaItemResults", []):
            status = item_result.get("status", {})

            if status.get("code") == 0 or status.get("message") == "Success":
                media_item = item_result.get("mediaItem", {})
                media_id = media_item.get("id")

                was_dedup = media_id in self._known_media_ids
                if not was_dedup and media_id:
                    self._known_media_ids.add(media_id)

                results.append((media_id, was_dedup))
            elif status.get("code") == 6:  # ALREADY_EXISTS
                media_id = item_result.get("mediaItem", {}).get("id")
                results.append((media_id, True))
            else:
                error_msg = status.get("message", "Unknown error")
                logger.warning(f"Batch item failed: {error_msg}")
                results.append((None, False))

        return results

    async def upload_bytes_only(self, filepath: Path) -> tuple[str, str]:
        """
        Upload file bytes only, return (upload_token, filename).

        Use with create_media_items_batch() for batched creation.
        """
        if not filepath.exists():
            raise PermanentError(f"File not found: {filepath}")

        await self._rate_limiter.acquire()
        upload_token = await self._upload_bytes(filepath, filepath.stat().st_size)
        return upload_token, filepath.name

    async def _check_response(self, response: aiohttp.ClientResponse):
        """Check response status and raise appropriate errors."""
        if response.status == 200:
            return

        if response.status in RETRYABLE_STATUSES:
            # Get retry-after header if present
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                logger.warning(f"Rate limited, retry after {retry_after}s")

            body = await response.text()
            raise RetryableError(
                f"HTTP {response.status}: {body[:200]}"
            )

        if response.status in PERMANENT_STATUSES:
            body = await response.text()
            raise PermanentError(
                f"HTTP {response.status}: {body[:200]}"
            )

        # Unknown status
        body = await response.text()
        raise RetryableError(f"HTTP {response.status}: {body[:200]}")

    def _handle_client_error(
        self,
        error: aiohttp.ClientError,
        filepath: Path
    ) -> UploadResult:
        """Convert aiohttp errors to appropriate exceptions."""
        error_str = str(error)

        if isinstance(error, aiohttp.ClientConnectionError):
            raise RetryableError(f"Connection error: {error_str}")

        if isinstance(error, aiohttp.ClientResponseError):
            if error.status in RETRYABLE_STATUSES:
                raise RetryableError(f"HTTP error: {error_str}")
            if error.status in PERMANENT_STATUSES:
                raise PermanentError(f"HTTP error: {error_str}")

        raise RetryableError(f"Client error: {error_str}")

    async def upload_batch(
        self,
        filepaths: list[Path],
        concurrency: int = 4
    ) -> dict[Path, UploadResult]:
        """
        Upload multiple files with controlled concurrency.

        Uses a semaphore to limit parallel uploads.
        """
        semaphore = asyncio.Semaphore(concurrency)
        results = {}

        async def upload_with_semaphore(path: Path) -> tuple[Path, UploadResult]:
            async with semaphore:
                try:
                    result = await self.upload_file(path)
                    return path, result
                except Exception as e:
                    return path, UploadResult(success=False, error=str(e))

        tasks = [upload_with_semaphore(p) for p in filepaths]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for item in completed:
            if isinstance(item, Exception):
                logger.error(f"Batch upload error: {item}")
            else:
                path, result = item
                results[path] = result

        return results


@dataclass
class PendingUpload:
    """A file awaiting batchCreate."""
    task_id: int
    file_id: int
    upload_token: str
    filename: str
    future: asyncio.Future  # Resolves to (media_id, was_dedup) or exception


class UploadTokenBatcher:
    """
    Batches upload tokens for efficient batchCreate calls.

    Per Google's best practices:
    - Upload bytes in parallel (workers do this)
    - Call batchCreate serially with up to 50 items per call

    Workers submit tokens, batcher accumulates them and periodically
    flushes to batchCreate. Results returned via futures.

    In pipelined mode, batcher also handles task completion directly,
    allowing workers to continue uploading without waiting.
    """

    BATCH_SIZE = 50
    FLUSH_INTERVAL = 5.0  # Max wait before flushing partial batch
    MIN_BATCH_SIZE = 20   # Flush early if we hit this and waited 2+ seconds

    def __init__(self, uploader: 'GooglePhotosUploader', db, task_queue=None):
        self.uploader = uploader
        self.db = db
        self.task_queue = task_queue  # For pipelined task completion
        self._pending: list[PendingUpload] = []
        self._lock = asyncio.Lock()
        self._batch_lock = asyncio.Lock()  # Ensures serial batchCreate
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None
        self._batch_start_time: Optional[float] = None  # Track when batch started accumulating

    async def start(self):
        """Start the periodic flush task."""
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info("UploadTokenBatcher started")

    async def stop(self):
        """Stop and flush remaining tokens."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush()
        logger.info("UploadTokenBatcher stopped")

    def submit_nowait(
        self,
        task_id: int,
        file_id: int,
        upload_token: str,
        filename: str
    ) -> asyncio.Future:
        """
        Submit an upload token for batched creation (non-blocking).
        Returns a Future that resolves to (media_id, was_deduplicated).
        Caller can await later or let batcher handle completion.
        """
        future = asyncio.get_event_loop().create_future()
        pending = PendingUpload(
            task_id=task_id,
            file_id=file_id,
            upload_token=upload_token,
            filename=filename,
            future=future
        )

        # Use synchronous append since we're not awaiting
        self._pending.append(pending)

        # Track when batch started accumulating
        if self._batch_start_time is None:
            self._batch_start_time = asyncio.get_event_loop().time()

        # Flush immediately if batch is full
        if len(self._pending) >= self.BATCH_SIZE:
            asyncio.create_task(self._flush())

        return future

    async def submit(
        self,
        task_id: int,
        file_id: int,
        upload_token: str,
        filename: str
    ) -> tuple[str, bool]:
        """
        Submit an upload token for batched creation (blocking).
        Returns (media_id, was_deduplicated) when batchCreate completes.
        """
        future = self.submit_nowait(task_id, file_id, upload_token, filename)
        return await future

    async def _periodic_flush(self):
        """Periodically flush partial batches with smart timing."""
        while self._running:
            await asyncio.sleep(1.0)  # Check every second

            if not self._pending:
                continue

            now = asyncio.get_event_loop().time()
            batch_age = now - (self._batch_start_time or now)

            # Flush if:
            # 1. Batch is full (50)
            # 2. Max wait exceeded (5 sec)
            # 3. Decent batch size (20+) and waited 2+ seconds
            should_flush = (
                len(self._pending) >= self.BATCH_SIZE or
                batch_age >= self.FLUSH_INTERVAL or
                (len(self._pending) >= self.MIN_BATCH_SIZE and batch_age >= 2.0)
            )

            if should_flush:
                await self._flush()

    async def _flush(self):
        """Flush pending tokens to batchCreate (serially)."""
        async with self._lock:
            if not self._pending:
                return
            batch = self._pending[:self.BATCH_SIZE]
            self._pending = self._pending[self.BATCH_SIZE:]
            # Reset batch timer if queue is now empty
            if not self._pending:
                self._batch_start_time = None
            else:
                self._batch_start_time = asyncio.get_event_loop().time()

        if not batch:
            return

        # Serial batchCreate - only one at a time
        async with self._batch_lock:
            succeeded = 0
            failed = 0
            try:
                await self.uploader._rate_limiter.acquire()
                items = [(p.upload_token, p.filename) for p in batch]
                # Check circuit breaker before making API call
                if not await circuit_breaker.can_execute():
                    raise CircuitBreakerOpenError("Circuit breaker is open")

                # Make the API call - circuit breaker tracks success/failure
                try:
                    results = await self.uploader._create_media_items_batch(items)
                    # Record success for circuit breaker
                    await circuit_breaker.record_success()
                except Exception:
                    # Record failure for circuit breaker
                    await circuit_breaker.record_failure()
                    raise

                # Resolve futures and update DB
                for pending, result in zip(batch, results):
                    media_id, was_dedup = result
                    if media_id:
                        await self.db.execute(
                            """UPDATE files
                               SET media_id = ?, status = 'uploaded', uploaded_at = CURRENT_TIMESTAMP
                               WHERE id = ?""",
                            (media_id, pending.file_id)
                        )
                        pending.future.set_result((media_id, was_dedup))
                        succeeded += 1

                        # Pipelined mode: batcher handles task completion
                        if self.task_queue:
                            await self.task_queue.complete_task(pending.task_id, True)
                    else:
                        error = RetryableError("batchCreate returned no media_id")
                        pending.future.set_exception(error)
                        failed += 1

                        # Pipelined mode: mark task failed for retry
                        if self.task_queue:
                            await self.task_queue.complete_task(pending.task_id, False, str(error))

                await self.db.commit()
                logger.info(f"Batched {len(batch)} media items ({succeeded} succeeded, {failed} failed)")

            except CircuitBreakerOpenError as e:
                # Circuit is open - don't hammer the failing service
                logger.warning(f"Circuit breaker open, skipping batch: {e}")
                error = RetryableError("Circuit breaker open - service unavailable")
                for pending in batch:
                    if not pending.future.done():
                        pending.future.set_exception(error)
                    if self.task_queue:
                        await self.task_queue.complete_task(pending.task_id, False, str(error))
            except Exception as e:
                logger.error(f"Batch create failed: {e}")
                for pending in batch:
                    if not pending.future.done():
                        pending.future.set_exception(e)
                    # Pipelined mode: mark all tasks as failed for retry
                    if self.task_queue:
                        await self.task_queue.complete_task(pending.task_id, False, str(e))


class UploadProgressTracker:
    """Tracks upload progress for UI updates."""

    def __init__(self, total_files: int, total_bytes: int):
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.completed_files = 0
        self.completed_bytes = 0
        self.failed_files = 0
        self.start_time = datetime.now()
        self._lock = asyncio.Lock()

    async def record_success(self, file_bytes: int):
        async with self._lock:
            self.completed_files += 1
            self.completed_bytes += file_bytes

    async def record_failure(self):
        async with self._lock:
            self.failed_files += 1

    @property
    def progress_percent(self) -> float:
        if self.total_files == 0:
            return 100.0
        return (self.completed_files / self.total_files) * 100

    @property
    def bytes_per_second(self) -> float:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed == 0:
            return 0
        return self.completed_bytes / elapsed

    @property
    def eta_seconds(self) -> float:
        bps = self.bytes_per_second
        if bps == 0:
            return float('inf')
        remaining_bytes = self.total_bytes - self.completed_bytes
        return remaining_bytes / bps

    def to_dict(self) -> dict:
        return {
            "total_files": self.total_files,
            "completed_files": self.completed_files,
            "failed_files": self.failed_files,
            "total_bytes": self.total_bytes,
            "completed_bytes": self.completed_bytes,
            "progress_percent": self.progress_percent,
            "bytes_per_second": self.bytes_per_second,
            "eta_seconds": self.eta_seconds,
        }
