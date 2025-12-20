"""
Filesystem Scanner

Scans directories for photo/video files with:
- Fast stat-based change detection
- Extension filtering
- Ignore pattern support
- Database integration for incremental scans
"""

import os
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Set
import fnmatch

logger = logging.getLogger(__name__)

# Default supported extensions
DEFAULT_EXTENSIONS = {
    # Images
    'jpg', 'jpeg', 'png', 'gif', 'heic', 'heif', 'webp', 'bmp', 'tiff', 'tif',
    # RAW formats
    'raw', 'cr2', 'cr3', 'nef', 'arw', 'dng', 'orf', 'rw2',
    # Videos
    'mp4', 'mov', 'avi', 'mkv', 'm4v', 'wmv', '3gp', 'webm', 'mts', 'm2ts',
}

# Default ignore patterns
DEFAULT_IGNORE = {
    '.thumbnails', '@eaDir', '.DS_Store', 'Thumbs.db',
    '.SynologyWorkingDirectory', '@Recycle', '#recycle',
    '.git', '__pycache__', 'node_modules',
}


@dataclass
class FileInfo:
    """Information about a scanned file."""
    path: Path
    filename: str
    directory: str
    extension: str
    mtime: float
    size: int


@dataclass
class ScanResult:
    """Result of a directory scan."""
    files: List[FileInfo] = field(default_factory=list)
    needs_hash: List[FileInfo] = field(default_factory=list)
    unchanged_count: int = 0
    error_count: int = 0
    total_bytes: int = 0
    scan_duration_ms: float = 0


async def scan_directory(
    root: Path,
    extensions: Optional[Set[str]] = None,
    ignore_patterns: Optional[Set[str]] = None,
    db=None,
    recursive: bool = True,
) -> ScanResult:
    """
    Scan a directory for media files.

    Args:
        root: Directory to scan
        extensions: File extensions to include (without dots)
        ignore_patterns: Directory/file names to ignore
        db: Optional database connection for incremental scanning
        recursive: Whether to scan subdirectories

    Returns:
        ScanResult with found files and statistics
    """
    import time
    start = time.time()

    extensions = extensions or DEFAULT_EXTENSIONS
    ignore_patterns = ignore_patterns or DEFAULT_IGNORE

    # Normalize extensions (lowercase, no dots)
    extensions = {ext.lower().lstrip('.') for ext in extensions}

    result = ScanResult()

    # Use thread pool for filesystem operations
    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(
        None,
        lambda: _scan_sync(root, extensions, ignore_patterns, recursive)
    )

    # Check against database for changes (batch query for performance)
    if db:
        # Get all known files in one query
        paths = [str(f.path) for f in files]
        known_files = {}

        # Query in batches of 500 to avoid SQLite limits
        batch_size = 500
        for i in range(0, len(paths), batch_size):
            batch = paths[i:i + batch_size]
            placeholders = ','.join('?' * len(batch))
            async with db.execute(
                f"SELECT local_path, mtime, size, sha256 FROM files WHERE local_path IN ({placeholders})",
                batch
            ) as cursor:
                async for row in cursor:
                    # Store (mtime, size, has_hash)
                    known_files[row[0]] = (row[1], row[2], row[3] is not None)

        # Compare against known files - needs hash if:
        # 1. Not in DB (new file)
        # 2. mtime or size changed
        # 3. sha256 is NULL (scanned but never hashed)
        for file_info in files:
            path_str = str(file_info.path)
            known = known_files.get(path_str)
            if not known:
                result.needs_hash.append(file_info)  # New file
            elif known[0] != file_info.mtime or known[1] != file_info.size:
                result.needs_hash.append(file_info)  # Changed file
            elif not known[2]:
                result.needs_hash.append(file_info)  # Has no hash
            else:
                result.unchanged_count += 1
    else:
        result.needs_hash = files

    result.files = files
    result.total_bytes = sum(f.size for f in files)
    result.scan_duration_ms = (time.time() - start) * 1000

    logger.info(
        f"Scanned {len(files)} files in {result.scan_duration_ms:.1f}ms "
        f"({result.unchanged_count} unchanged, {len(result.needs_hash)} need hash)"
    )

    return result


def _scan_sync(
    root: Path,
    extensions: Set[str],
    ignore_patterns: Set[str],
    recursive: bool,
) -> List[FileInfo]:
    """Synchronous directory scan (runs in thread pool)."""
    files = []

    def should_ignore(name: str) -> bool:
        for pattern in ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    def scan_dir(path: Path):
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if recursive and not should_ignore(entry.name):
                                scan_dir(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            if should_ignore(entry.name):
                                continue

                            ext = Path(entry.name).suffix.lower().lstrip('.')
                            if ext not in extensions:
                                continue

                            stat = entry.stat()
                            files.append(FileInfo(
                                path=Path(entry.path),
                                filename=entry.name,
                                directory=str(path),
                                extension=ext,
                                mtime=stat.st_mtime,
                                size=stat.st_size,
                            ))
                    except (PermissionError, OSError) as e:
                        logger.debug(f"Cannot access {entry.path}: {e}")
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot scan {path}: {e}")

    scan_dir(root)
    return files


async def _check_file_changed(db, file_info: FileInfo) -> bool:
    """Check if file has changed since last scan."""
    async with db.execute(
        "SELECT mtime, size FROM files WHERE local_path = ?",
        (str(file_info.path),)
    ) as cursor:
        row = await cursor.fetchone()

        if not row:
            return True  # New file

        # Compare mtime and size
        if row['mtime'] != file_info.mtime or row['size'] != file_info.size:
            return True  # File changed

        return False  # Unchanged


async def get_scan_stats(db) -> dict:
    """Get statistics about scanned files."""
    stats = {}

    async with db.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'uploaded' THEN 1 END) as uploaded,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
            COUNT(CASE WHEN status = 'error' THEN 1 END) as errors,
            SUM(size) as total_bytes
        FROM files
    """) as cursor:
        row = await cursor.fetchone()
        stats['total_files'] = row['total']
        stats['uploaded_files'] = row['uploaded']
        stats['pending_files'] = row['pending']
        stats['error_files'] = row['errors']
        stats['total_bytes'] = row['total_bytes'] or 0

    # Files by extension
    async with db.execute("""
        SELECT extension, COUNT(*) as count, SUM(size) as bytes
        FROM files
        GROUP BY extension
        ORDER BY count DESC
        LIMIT 10
    """) as cursor:
        stats['by_extension'] = [dict(row) async for row in cursor]

    # Files by directory
    async with db.execute("""
        SELECT directory, COUNT(*) as count
        FROM files
        GROUP BY directory
        ORDER BY count DESC
        LIMIT 20
    """) as cursor:
        stats['by_directory'] = [dict(row) async for row in cursor]

    return stats
