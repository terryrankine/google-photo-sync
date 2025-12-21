"""
Pytest configuration and fixtures.
"""

import pytest
import pytest_asyncio
import tempfile
import shutil
from pathlib import Path
import aiosqlite


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest_asyncio.fixture
async def test_db(temp_dir):
    """Create a test database with schema."""
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
def sample_photos(temp_dir):
    """Create sample photo files for testing."""
    photos = []

    for i in range(10):
        # Create fake JPEG files (just random bytes with JPEG header)
        photo_path = temp_dir / f"photo_{i:03d}.jpg"
        # JPEG magic bytes + random content
        content = b'\xff\xd8\xff\xe0' + bytes([i] * 1000)
        photo_path.write_bytes(content)
        photos.append(photo_path)

    return photos


@pytest.fixture
def sample_structure(temp_dir):
    """Create a realistic directory structure."""
    structure = {
        "2024": {
            "01": ["IMG_001.jpg", "IMG_002.jpg", "video.mp4"],
            "02": ["IMG_003.jpg", "IMG_004.heic"],
        },
        "2023": {
            "12": ["holiday_001.jpg", "holiday_002.jpg"],
        },
        ".thumbnails": ["thumb1.jpg"],  # Should be ignored
    }

    def create_files(base: Path, items: dict | list, level=0):
        for name, content in (items.items() if isinstance(items, dict) else enumerate(items)):
            if isinstance(content, dict):
                subdir = base / name
                subdir.mkdir(parents=True, exist_ok=True)
                create_files(subdir, content, level + 1)
            elif isinstance(content, list):
                subdir = base / name if isinstance(name, str) else base
                subdir.mkdir(parents=True, exist_ok=True)
                for filename in content:
                    file_path = subdir / filename
                    file_path.write_bytes(b'\xff\xd8\xff\xe0' + filename.encode())
            else:
                file_path = base / content
                file_path.write_bytes(b'\xff\xd8\xff\xe0' + content.encode())

    create_files(temp_dir, structure)
    return temp_dir


class MockGooglePhotosAPI:
    """Mock Google Photos API for testing."""

    def __init__(self):
        self.uploaded_files = {}
        self.upload_count = 0
        self.should_fail = False
        self.fail_count = 0
        self.rate_limited = False

    async def upload(self, filepath: Path) -> str:
        """Mock upload - returns fake media ID."""
        if self.rate_limited:
            self.rate_limited = False  # Reset after one failure
            raise Exception("Rate limited")

        if self.should_fail and self.fail_count > 0:
            self.fail_count -= 1
            raise Exception("Simulated failure")

        # Simulate deduplication based on content hash
        content = filepath.read_bytes()
        content_hash = hash(content)

        if content_hash in self.uploaded_files:
            # Return existing media ID (deduplicated)
            return self.uploaded_files[content_hash]

        # New upload
        media_id = f"media_{self.upload_count:06d}"
        self.upload_count += 1
        self.uploaded_files[content_hash] = media_id

        return media_id


@pytest.fixture
def mock_api():
    """Create mock Google Photos API."""
    return MockGooglePhotosAPI()
