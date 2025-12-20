"""
File Hasher

Computes SHA256 hashes with:
- Streaming for memory efficiency
- Parallel processing via ProcessPoolExecutor
- Progress tracking
"""

import asyncio
import hashlib
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Callable, Optional
import os

logger = logging.getLogger(__name__)

# Chunk size for reading files
# 4MB is optimal for NAS/network storage with high latency
# (reduces syscall overhead, better sequential read performance)
CHUNK_SIZE = 4 * 1024 * 1024  # 4MB

# Default number of worker processes
DEFAULT_WORKERS = min(4, os.cpu_count() or 1)


@dataclass
class HashResult:
    """Result of hashing operation."""
    path: Path
    sha256: str
    size: int
    duration_ms: float


def _hash_file_sync(filepath: str) -> tuple[str, str, int]:
    """
    Compute SHA256 hash of a file (synchronous, for process pool).

    Uses Python 3.11's file_digest() which is optimized for file hashing:
    - Uses sendfile() on Linux for zero-copy I/O
    - Optimal buffer sizes chosen automatically
    - Significantly faster than manual chunk reading
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    size = path.stat().st_size

    with open(path, 'rb') as f:
        # Python 3.11+ file_digest is optimized - uses sendfile on Linux
        digest = hashlib.file_digest(f, 'sha256')

    return filepath, digest.hexdigest(), size


async def hash_file(filepath: Path) -> str:
    """
    Compute SHA256 hash of a single file.

    Args:
        filepath: Path to file

    Returns:
        Hex-encoded SHA256 hash

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    loop = asyncio.get_event_loop()
    _, file_hash, _ = await loop.run_in_executor(
        None,
        _hash_file_sync,
        str(filepath)
    )
    return file_hash


async def hash_files(
    filepaths: List[Path],
    workers: int = DEFAULT_WORKERS,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[Path, str]:
    """
    Hash multiple files in parallel using process pool.

    Args:
        filepaths: List of file paths to hash
        workers: Number of parallel workers
        progress_callback: Optional callback(completed, total) for progress updates

    Returns:
        Dict mapping file paths to their SHA256 hashes
    """
    import time

    if not filepaths:
        return {}

    results = {}
    total = len(filepaths)
    completed = 0

    start = time.time()
    logger.info(f"Hashing {total} files with {workers} workers")

    # Use ProcessPoolExecutor for CPU-bound hashing
    loop = asyncio.get_event_loop()

    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks
        futures = {
            loop.run_in_executor(executor, _hash_file_sync, str(path)): path
            for path in filepaths
        }

        # Collect results as they complete
        for coro in asyncio.as_completed(futures.keys()):
            try:
                filepath, file_hash, size = await coro
                results[Path(filepath)] = file_hash
                completed += 1

                if progress_callback:
                    progress_callback(completed, total)

                if completed % 100 == 0:
                    logger.debug(f"Hashed {completed}/{total} files")

            except Exception as e:
                # Find which file failed
                for future, path in futures.items():
                    if future == coro:
                        logger.error(f"Failed to hash {path}: {e}")
                        break

    elapsed = time.time() - start
    total_bytes = sum(p.stat().st_size for p in results.keys() if p.exists())
    speed_mbps = (total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0

    logger.info(
        f"Hashed {len(results)} files in {elapsed:.1f}s "
        f"({speed_mbps:.1f} MB/s)"
    )

    return results


async def hash_and_dedupe(
    filepaths: List[Path],
    db,
    workers: int = DEFAULT_WORKERS,
) -> tuple[Dict[Path, str], List[Path]]:
    """
    Hash files and identify duplicates based on existing DB entries.

    Args:
        filepaths: List of file paths to hash
        db: Database connection
        workers: Number of parallel workers

    Returns:
        Tuple of (new_hashes, duplicate_paths)
        - new_hashes: Dict of path -> hash for files not in DB
        - duplicate_paths: List of paths that are duplicates
    """
    hashes = await hash_files(filepaths, workers)

    new_hashes = {}
    duplicates = []

    for path, file_hash in hashes.items():
        # Check if hash exists in DB with a media_id (already uploaded)
        async with db.execute(
            "SELECT media_id FROM files WHERE sha256 = ? AND media_id IS NOT NULL LIMIT 1",
            (file_hash,)
        ) as cursor:
            row = await cursor.fetchone()

            if row:
                # This is a duplicate - same content already uploaded
                duplicates.append(path)
                logger.debug(f"Duplicate detected: {path}")
            else:
                new_hashes[path] = file_hash

    logger.info(
        f"Found {len(new_hashes)} new files, {len(duplicates)} duplicates"
    )

    return new_hashes, duplicates


async def verify_hash(filepath: Path, expected_hash: str) -> bool:
    """
    Verify a file matches its expected hash.

    Useful for detecting file corruption or changes.
    """
    try:
        actual_hash = await hash_file(filepath)
        return actual_hash == expected_hash
    except Exception:
        return False
