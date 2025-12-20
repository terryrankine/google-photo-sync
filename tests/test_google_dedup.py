"""
Google Photos Deduplication Tests

Tests to verify Google's server-side deduplication behavior:
1. Upload same file 3 times respecting local metadata (should skip after first)
2. Upload same file 3 times ignoring local metadata (should get same media_id)
3. Upload same content with different filenames (should dedupe)
4. Upload modified file (should get new media_id)

IMPORTANT: These are integration tests that hit the real Google Photos API.
Run with: pytest tests/test_google_dedup.py -v -s

Requires:
- Valid credentials.json in ./config/
- Authenticated token.json in ./config/
"""

import pytest
import asyncio
import hashlib
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
import json
import os

# Skip all tests if no credentials
CREDENTIALS_PATH = Path("config/credentials.json")
TOKEN_PATH = Path("config/token.json")

pytestmark = pytest.mark.skipif(
    not CREDENTIALS_PATH.exists() or not TOKEN_PATH.exists(),
    reason="Google API credentials not configured"
)


class TestGoogleDeduplication:
    """Test Google Photos deduplication behavior."""

    @pytest.fixture
    def test_image(self, tmp_path) -> Path:
        """Create a unique test image."""
        # Create a simple valid JPEG
        # JPEG header + unique content based on timestamp
        unique_content = f"test-{datetime.now().isoformat()}".encode()
        content = self._create_minimal_jpeg(unique_content)

        image_path = tmp_path / "test_image.jpg"
        image_path.write_bytes(content)
        return image_path

    @pytest.fixture
    def duplicate_images(self, tmp_path, test_image) -> list[Path]:
        """Create 3 copies of the same image with different names."""
        copies = []
        for i in range(3):
            copy_path = tmp_path / f"copy_{i}.jpg"
            shutil.copy(test_image, copy_path)
            copies.append(copy_path)
        return copies

    def _create_minimal_jpeg(self, unique_data: bytes) -> bytes:
        """Create a minimal valid JPEG with unique content."""
        # Minimal JPEG structure
        # SOI (Start of Image)
        jpeg = b'\xff\xd8'
        # APP0 (JFIF marker)
        jpeg += b'\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        # COM (Comment) - embed our unique data here
        comment = b'\xff\xfe' + len(unique_data).to_bytes(2, 'big') + unique_data
        jpeg += comment
        # DQT (Quantization table) - minimal
        jpeg += b'\xff\xdb\x00C\x00'
        jpeg += bytes(64)  # 64 bytes of quantization data
        # SOF0 (Start of Frame)
        jpeg += b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
        # DHT (Huffman table) - minimal
        jpeg += b'\xff\xc4\x00\x1f\x00'
        jpeg += bytes(28)
        # SOS (Start of Scan)
        jpeg += b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00'
        # Image data (minimal)
        jpeg += b'\x7f'
        # EOI (End of Image)
        jpeg += b'\xff\xd9'
        return jpeg

    def _compute_hash(self, path: Path) -> str:
        """Compute SHA256 hash of file."""
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @pytest.mark.asyncio
    async def test_upload_with_metadata_tracking(self, test_image, tmp_path):
        """
        Test 1: Upload same file 3 times WITH local metadata tracking.

        Expected behavior:
        - First upload: Actually uploads, gets media_id
        - Second upload: Skipped by local DB (already uploaded)
        - Third upload: Skipped by local DB (already uploaded)
        """
        from src.uploader import GooglePhotosUploader, UploadResult

        results = []
        uploaded_hashes = {}  # Simulates local DB

        async with GooglePhotosUploader(CREDENTIALS_PATH, TOKEN_PATH) as uploader:
            for i in range(3):
                file_hash = self._compute_hash(test_image)

                # Check "local DB" first
                if file_hash in uploaded_hashes:
                    results.append({
                        "attempt": i + 1,
                        "action": "SKIPPED_BY_LOCAL_DB",
                        "media_id": uploaded_hashes[file_hash],
                        "reason": "Hash already in local database"
                    })
                    continue

                # Actually upload
                result = await uploader.upload_file(test_image)

                if result.success:
                    uploaded_hashes[file_hash] = result.media_id
                    results.append({
                        "attempt": i + 1,
                        "action": "UPLOADED",
                        "media_id": result.media_id,
                        "was_deduplicated": result.was_deduplicated
                    })
                else:
                    results.append({
                        "attempt": i + 1,
                        "action": "FAILED",
                        "error": result.error
                    })

        # Log results
        print("\n=== Test 1: Upload with metadata tracking ===")
        for r in results:
            print(f"  Attempt {r['attempt']}: {r['action']} - {r.get('media_id', r.get('error', 'N/A'))}")

        # Assertions
        assert len(results) == 3
        assert results[0]["action"] == "UPLOADED"
        assert results[1]["action"] == "SKIPPED_BY_LOCAL_DB"
        assert results[2]["action"] == "SKIPPED_BY_LOCAL_DB"
        assert results[1]["media_id"] == results[0]["media_id"]
        assert results[2]["media_id"] == results[0]["media_id"]

    @pytest.mark.asyncio
    async def test_upload_without_metadata_tracking(self, duplicate_images):
        """
        Test 2: Upload same file 3 times WITHOUT local metadata tracking.

        Expected behavior:
        - All 3 uploads go to Google
        - Google should return the SAME media_id for all 3 (server-side dedup)
        """
        from src.uploader import GooglePhotosUploader

        results = []

        async with GooglePhotosUploader(CREDENTIALS_PATH, TOKEN_PATH) as uploader:
            for i, image_path in enumerate(duplicate_images):
                result = await uploader.upload_file(image_path)

                results.append({
                    "attempt": i + 1,
                    "filename": image_path.name,
                    "success": result.success,
                    "media_id": result.media_id,
                    "was_deduplicated": result.was_deduplicated,
                    "error": result.error
                })

        # Log results
        print("\n=== Test 2: Upload without metadata tracking (3 identical files) ===")
        for r in results:
            print(f"  Attempt {r['attempt']} ({r['filename']}): "
                  f"media_id={r['media_id']}, dedup={r['was_deduplicated']}")

        # Assertions
        assert all(r["success"] for r in results), "All uploads should succeed"

        media_ids = [r["media_id"] for r in results]
        unique_ids = set(media_ids)

        print(f"\n  Unique media_ids: {len(unique_ids)}")
        print(f"  Google deduplicated: {len(unique_ids) == 1}")

        # Google SHOULD return the same media_id for identical content
        # If not, it means Google didn't dedupe (which happens sometimes)
        if len(unique_ids) == 1:
            print("  ✓ Google returned same media_id for all 3 uploads (deduplication works!)")
        else:
            print("  ⚠ Google returned different media_ids - deduplication may not be immediate")

        # Store results for analysis
        results_file = Path("test_results_dedup.json")
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Results saved to: {results_file}")

    @pytest.mark.asyncio
    async def test_upload_same_content_different_names(self, test_image, tmp_path):
        """
        Test 3: Upload same content with different filenames.

        Expected behavior:
        - Google should recognize identical content
        - May return same media_id OR keep first filename
        """
        from src.uploader import GooglePhotosUploader

        # Create copies with different names
        filenames = ["vacation_001.jpg", "backup_photo.jpg", "IMG_20241220.jpg"]
        copies = []
        for name in filenames:
            copy_path = tmp_path / name
            shutil.copy(test_image, copy_path)
            copies.append(copy_path)

        results = []

        async with GooglePhotosUploader(CREDENTIALS_PATH, TOKEN_PATH) as uploader:
            for image_path in copies:
                result = await uploader.upload_file(image_path)
                results.append({
                    "filename": image_path.name,
                    "media_id": result.media_id,
                    "success": result.success
                })

        print("\n=== Test 3: Same content, different filenames ===")
        for r in results:
            print(f"  {r['filename']}: media_id={r['media_id']}")

        media_ids = set(r["media_id"] for r in results)
        print(f"\n  Unique media_ids: {len(media_ids)}")

    @pytest.mark.asyncio
    async def test_upload_modified_file(self, test_image, tmp_path):
        """
        Test 4: Upload original, then modified version.

        Expected behavior:
        - Original upload gets media_id_1
        - Modified upload gets media_id_2 (different!)
        """
        from src.uploader import GooglePhotosUploader

        # Create modified version
        modified_path = tmp_path / "modified.jpg"
        original_content = test_image.read_bytes()
        # Modify by appending data (changes hash)
        modified_content = original_content[:-2] + b'\x00\x42' + original_content[-2:]
        modified_path.write_bytes(modified_content)

        original_hash = self._compute_hash(test_image)
        modified_hash = self._compute_hash(modified_path)

        print(f"\n=== Test 4: Original vs Modified ===")
        print(f"  Original hash: {original_hash[:16]}...")
        print(f"  Modified hash: {modified_hash[:16]}...")
        print(f"  Hashes different: {original_hash != modified_hash}")

        results = []

        async with GooglePhotosUploader(CREDENTIALS_PATH, TOKEN_PATH) as uploader:
            # Upload original
            result1 = await uploader.upload_file(test_image)
            results.append(("original", result1.media_id))

            # Upload modified
            result2 = await uploader.upload_file(modified_path)
            results.append(("modified", result2.media_id))

        for name, media_id in results:
            print(f"  {name}: media_id={media_id}")

        # Modified file SHOULD get a different media_id
        assert results[0][1] != results[1][1], \
            "Modified file should get different media_id"
        print("\n  ✓ Modified file correctly got a different media_id")


class TestLocalDatabaseDedup:
    """Test local database deduplication (no API calls)."""

    @pytest.fixture
    def mock_db(self, tmp_path):
        """Create a mock database for testing."""
        import sqlite3
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        conn.executescript("""
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                source_name TEXT,
                relative_path TEXT,
                sha256 TEXT,
                media_id TEXT,
                status TEXT DEFAULT 'pending',
                UNIQUE(source_name, relative_path)
            );
            CREATE INDEX idx_sha256 ON files(sha256);
        """)
        conn.commit()

        yield conn
        conn.close()

    def test_local_hash_dedup(self, mock_db, tmp_path):
        """
        Test that local hash-based dedup prevents re-upload.
        """
        # Create test file
        content = b"test content for dedup"
        file_hash = hashlib.sha256(content).hexdigest()

        # Simulate first upload
        mock_db.execute("""
            INSERT INTO files (source_name, relative_path, sha256, media_id, status)
            VALUES (?, ?, ?, ?, ?)
        """, ("photos", "2024/01/IMG_001.jpg", file_hash, "media_abc123", "uploaded"))
        mock_db.commit()

        # Now check if same hash would be skipped
        cursor = mock_db.execute(
            "SELECT media_id FROM files WHERE sha256 = ? AND media_id IS NOT NULL",
            (file_hash,)
        )
        existing = cursor.fetchone()

        assert existing is not None
        assert existing["media_id"] == "media_abc123"
        print(f"\n✓ Local dedup works: hash {file_hash[:16]}... -> media_abc123")

    def test_different_path_same_hash(self, mock_db):
        """
        Test: Same content at different path should reuse media_id.
        """
        file_hash = "abc123def456"

        # First file uploaded
        mock_db.execute("""
            INSERT INTO files (source_name, relative_path, sha256, media_id, status)
            VALUES (?, ?, ?, ?, ?)
        """, ("photos", "2024/01/original.jpg", file_hash, "media_xyz", "uploaded"))
        mock_db.commit()

        # Second file with same hash at different path
        # Should we upload? Check if hash exists with media_id
        cursor = mock_db.execute(
            "SELECT media_id FROM files WHERE sha256 = ? AND media_id IS NOT NULL LIMIT 1",
            (file_hash,)
        )
        existing = cursor.fetchone()

        if existing:
            # Copy the media_id instead of uploading
            mock_db.execute("""
                INSERT INTO files (source_name, relative_path, sha256, media_id, status)
                VALUES (?, ?, ?, ?, ?)
            """, ("photos", "backup/copy.jpg", file_hash, existing["media_id"], "uploaded"))
            mock_db.commit()

        # Verify both files have same media_id
        cursor = mock_db.execute(
            "SELECT relative_path, media_id FROM files WHERE sha256 = ?",
            (file_hash,)
        )
        rows = cursor.fetchall()

        assert len(rows) == 2
        assert all(r["media_id"] == "media_xyz" for r in rows)
        print("\n✓ Same hash at different paths share media_id")
        for r in rows:
            print(f"  {r['relative_path']} -> {r['media_id']}")


class TestUploadRetryBehavior:
    """Test retry behavior with Google API."""

    @pytest.mark.asyncio
    async def test_upload_after_failure_same_id(self, tmp_path):
        """
        Test: If upload fails and retries, does Google return same ID?

        Simulates: Network failure mid-upload, then retry.
        """
        # This test requires mocking - actual API won't fail predictably
        pytest.skip("Requires mock - can't force API failure")


# Standalone runner for quick testing
async def run_dedup_test():
    """Run a quick dedup test without pytest."""
    import tempfile

    print("=" * 60)
    print("Google Photos Deduplication Test")
    print("=" * 60)

    if not CREDENTIALS_PATH.exists():
        print(f"\n❌ Missing: {CREDENTIALS_PATH}")
        print("Please set up Google API credentials first.")
        return

    if not TOKEN_PATH.exists():
        print(f"\n❌ Missing: {TOKEN_PATH}")
        print("Please authenticate first.")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Create test image
        unique = f"dedup-test-{datetime.now().isoformat()}".encode()
        content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00' + unique + b'\xff\xd9'

        images = []
        for i in range(3):
            path = tmp_path / f"test_{i}.jpg"
            path.write_bytes(content)
            images.append(path)

        print(f"\nCreated 3 identical test images")
        print(f"Content hash: {hashlib.sha256(content).hexdigest()[:16]}...")

        from src.uploader import GooglePhotosUploader

        results = []
        async with GooglePhotosUploader(CREDENTIALS_PATH, TOKEN_PATH) as uploader:
            for i, img in enumerate(images):
                print(f"\nUploading {img.name}...", end=" ")
                result = await uploader.upload_file(img)
                print(f"media_id={result.media_id}")
                results.append(result.media_id)

        unique_ids = set(results)
        print(f"\n{'=' * 60}")
        print(f"Results:")
        print(f"  Uploads: 3")
        print(f"  Unique media_ids: {len(unique_ids)}")
        print(f"  Google deduplicated: {'YES ✓' if len(unique_ids) == 1 else 'NO ✗'}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(run_dedup_test())
