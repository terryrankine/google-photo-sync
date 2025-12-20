"""
Host Manager

Handles multi-host operation:
- Register current host on startup
- Map logical source names to local paths
- Convert between local paths and relative paths
"""

import socket
import platform
import logging
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HostInfo:
    """Information about a host."""
    id: int
    hostname: str
    description: Optional[str] = None


@dataclass
class PathMapping:
    """Maps a logical source to a local path."""
    source_name: str
    local_path: Path


class HostManager:
    """
    Manages host registration and path mappings.

    Allows the same database to be used from multiple machines:
    - Windows dev machine with NAS mounted as Z:\
    - NAS itself with local paths like /volume1/photos

    Example:
        # On Windows:
        host_manager.register_host()
        host_manager.add_path_mapping('photos', 'Z:\\photos')

        # On NAS:
        host_manager.register_host()
        host_manager.add_path_mapping('photos', '/volume1/photos')

        # Both see the same relative paths:
        # 'photos/2024/01/IMG_001.jpg' -> same file, same hash, one upload
    """

    def __init__(self, db):
        self.db = db
        self._host_id: Optional[int] = None
        self._hostname: Optional[str] = None
        self._path_mappings: dict[str, Path] = {}

    @property
    def host_id(self) -> int:
        if self._host_id is None:
            raise RuntimeError("Host not registered. Call register_host() first.")
        return self._host_id

    @property
    def hostname(self) -> str:
        if self._hostname is None:
            self._hostname = socket.gethostname()
        return self._hostname

    async def register_host(self, description: Optional[str] = None) -> int:
        """
        Register current host in database.
        Creates new entry if hostname doesn't exist, otherwise returns existing ID.
        """
        hostname = self.hostname

        # Try to get existing
        async with self.db.execute(
            "SELECT id FROM hosts WHERE hostname = ?",
            (hostname,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                self._host_id = row['id']
                await self.db.execute(
                    "UPDATE hosts SET last_seen_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (self._host_id,)
                )
                await self.db.commit()
                logger.info(f"Using existing host: {hostname} (id={self._host_id})")
                return self._host_id

        # Create new
        if description is None:
            description = f"{platform.system()} {platform.release()}"

        async with self.db.execute(
            "INSERT INTO hosts (hostname, description) VALUES (?, ?)",
            (hostname, description)
        ) as cursor:
            self._host_id = cursor.lastrowid

        await self.db.commit()
        logger.info(f"Registered new host: {hostname} (id={self._host_id})")
        return self._host_id

    async def add_path_mapping(
        self,
        source_name: str,
        local_path: str | Path
    ) -> None:
        """
        Add a path mapping for the current host.

        Args:
            source_name: Logical name for this source (e.g., 'photos', 'archive')
            local_path: Full path on this host (e.g., 'Z:\\photos' or '/volume1/photos')
        """
        local_path = Path(local_path)

        if not local_path.exists():
            logger.warning(f"Path does not exist: {local_path}")

        await self.db.execute("""
            INSERT INTO path_mappings (host_id, source_name, local_path)
            VALUES (?, ?, ?)
            ON CONFLICT(host_id, source_name) DO UPDATE SET
                local_path = excluded.local_path,
                is_active = 1
        """, (self.host_id, source_name, str(local_path)))
        await self.db.commit()

        self._path_mappings[source_name] = local_path
        logger.info(f"Path mapping: {source_name} -> {local_path}")

    async def load_path_mappings(self) -> dict[str, Path]:
        """Load all path mappings for current host."""
        async with self.db.execute("""
            SELECT source_name, local_path FROM path_mappings
            WHERE host_id = ? AND is_active = 1
        """, (self.host_id,)) as cursor:
            async for row in cursor:
                self._path_mappings[row['source_name']] = Path(row['local_path'])

        return self._path_mappings

    def get_local_path(self, source_name: str) -> Optional[Path]:
        """Get local path for a source name on current host."""
        return self._path_mappings.get(source_name)

    def to_relative_path(self, local_path: Path | str) -> tuple[str, str]:
        """
        Convert a local path to (source_name, relative_path).

        Args:
            local_path: Full path on current host

        Returns:
            Tuple of (source_name, relative_path)

        Example:
            # On Windows with mapping: photos -> Z:\photos
            to_relative_path('Z:\\photos\\2024\\01\\IMG_001.jpg')
            # Returns: ('photos', '2024/01/IMG_001.jpg')

            # On NAS with mapping: photos -> /volume1/photos
            to_relative_path('/volume1/photos/2024/01/IMG_001.jpg')
            # Returns: ('photos', '2024/01/IMG_001.jpg')
        """
        local_path = Path(local_path)

        for source_name, base_path in self._path_mappings.items():
            try:
                relative = local_path.relative_to(base_path)
                # Normalize to forward slashes for cross-platform consistency
                relative_str = relative.as_posix()
                return source_name, relative_str
            except ValueError:
                continue

        raise ValueError(f"Path not under any mapped source: {local_path}")

    def to_local_path(self, source_name: str, relative_path: str) -> Path:
        """
        Convert (source_name, relative_path) to local path on current host.

        Args:
            source_name: Logical source name
            relative_path: Path relative to source root (forward slashes)

        Returns:
            Full path on current host

        Example:
            # On Windows with mapping: photos -> Z:\photos
            to_local_path('photos', '2024/01/IMG_001.jpg')
            # Returns: Path('Z:/photos/2024/01/IMG_001.jpg')

            # On NAS with mapping: photos -> /volume1/photos
            to_local_path('photos', '2024/01/IMG_001.jpg')
            # Returns: Path('/volume1/photos/2024/01/IMG_001.jpg')
        """
        base_path = self._path_mappings.get(source_name)
        if not base_path:
            raise ValueError(f"No mapping for source: {source_name}")

        return base_path / relative_path

    async def get_all_hosts(self) -> list[HostInfo]:
        """Get all registered hosts."""
        hosts = []
        async with self.db.execute(
            "SELECT id, hostname, description FROM hosts ORDER BY hostname"
        ) as cursor:
            async for row in cursor:
                hosts.append(HostInfo(
                    id=row['id'],
                    hostname=row['hostname'],
                    description=row['description']
                ))
        return hosts

    async def get_host_mappings(self, host_id: int) -> list[PathMapping]:
        """Get path mappings for a specific host."""
        mappings = []
        async with self.db.execute("""
            SELECT source_name, local_path FROM path_mappings
            WHERE host_id = ? AND is_active = 1
        """, (host_id,)) as cursor:
            async for row in cursor:
                mappings.append(PathMapping(
                    source_name=row['source_name'],
                    local_path=Path(row['local_path'])
                ))
        return mappings


def normalize_path(path: str | Path) -> str:
    """
    Normalize a path to forward slashes for storage.
    This ensures cross-platform compatibility.
    """
    return Path(path).as_posix()


def get_relative_path(full_path: Path, base_path: Path) -> str:
    """
    Get relative path with forward slashes.
    Works regardless of OS.
    """
    return full_path.relative_to(base_path).as_posix()
