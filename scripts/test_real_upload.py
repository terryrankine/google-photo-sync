#!/usr/bin/env python3
"""
Real Integration Test for Google Photos Upload

This script tests actual uploading to Google Photos.
Run from project root: python scripts/test_real_upload.py [path_to_image]

Prerequisites:
1. OAuth credentials in config/credentials.json
2. Token in config/token.json (run auth.py first if needed)
3. A test image file

What this tests:
- OAuth token loading and refresh
- Upload bytes to Google Photos
- Create media item from upload token
- Deduplication detection
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.uploader import GooglePhotosUploader, UploadResult


async def test_single_upload(image_path: Path):
    """Test uploading a single file."""
    print(f"\n{'='*60}")
    print("Google Photos Upload Integration Test")
    print(f"{'='*60}\n")

    config_dir = project_root / "config"
    credentials_path = config_dir / "credentials.json"
    token_path = config_dir / "token.json"

    # Check prerequisites
    print("Checking prerequisites...")

    if not credentials_path.exists():
        print(f"ERROR: credentials.json not found at {credentials_path}")
        print("  Download from Google Cloud Console > APIs & Services > Credentials")
        return False

    if not token_path.exists():
        print(f"ERROR: token.json not found at {token_path}")
        print("  Run: python scripts/auth.py")
        return False

    if not image_path.exists():
        print(f"ERROR: Image file not found: {image_path}")
        return False

    print(f"  credentials.json: OK")
    print(f"  token.json: OK")
    print(f"  Test image: {image_path} ({image_path.stat().st_size / 1024:.1f} KB)")

    # Test upload
    print(f"\nUploading to Google Photos...")

    try:
        async with GooglePhotosUploader(credentials_path, token_path) as uploader:
            result = await uploader.upload_file(image_path)

            if result.success:
                print(f"\n SUCCESS!")
                print(f"  Media ID: {result.media_id}")
                if result.was_deduplicated:
                    print(f"  Note: Image was deduplicated (already exists in Google Photos)")
                print(f"\n  View at: https://photos.google.com/search/{image_path.stem}")
                return True
            else:
                print(f"\n FAILED!")
                print(f"  Error: {result.error}")
                return False

    except Exception as e:
        print(f"\n ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_batch_upload(image_paths: list[Path]):
    """Test uploading multiple files."""
    print(f"\n{'='*60}")
    print("Batch Upload Test")
    print(f"{'='*60}\n")

    config_dir = project_root / "config"
    credentials_path = config_dir / "credentials.json"
    token_path = config_dir / "token.json"

    valid_paths = [p for p in image_paths if p.exists()]
    if not valid_paths:
        print("ERROR: No valid image files found")
        return False

    print(f"Uploading {len(valid_paths)} files...")

    try:
        async with GooglePhotosUploader(credentials_path, token_path) as uploader:
            results = await uploader.upload_batch(valid_paths, concurrency=2)

            success_count = sum(1 for r in results.values() if r.success)
            dedup_count = sum(1 for r in results.values() if r.was_deduplicated)
            fail_count = len(results) - success_count

            print(f"\nResults:")
            print(f"  Successful: {success_count}")
            print(f"  Deduplicated: {dedup_count}")
            print(f"  Failed: {fail_count}")

            for path, result in results.items():
                status = "OK" if result.success else "FAIL"
                extra = " (dedup)" if result.was_deduplicated else ""
                error = f" - {result.error}" if result.error else ""
                print(f"  {status}: {path.name}{extra}{error}")

            return fail_count == 0

    except Exception as e:
        print(f"\n ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_test_image(output_path: Path):
    """Create a simple test image if PIL is available."""
    try:
        from PIL import Image

        # Create a simple test image with unique content (timestamp)
        import time
        img = Image.new('RGB', (100, 100), color=(
            int(time.time()) % 256,
            (int(time.time()) >> 8) % 256,
            (int(time.time()) >> 16) % 256
        ))

        # Add some text to make it unique
        try:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            draw.text((10, 40), f"{time.time():.0f}", fill='white')
        except:
            pass

        img.save(output_path, 'JPEG', quality=85)
        print(f"Created test image: {output_path}")
        return True
    except ImportError:
        print("PIL not installed. Cannot create test image.")
        print("Install with: pip install Pillow")
        return False


def find_test_images(directory: Path, limit: int = 5) -> list[Path]:
    """Find image files in a directory."""
    extensions = {'.jpg', '.jpeg', '.png', '.heic', '.gif', '.webp'}
    images = []

    for ext in extensions:
        images.extend(directory.glob(f'*{ext}'))
        images.extend(directory.glob(f'*{ext.upper()}'))

    return images[:limit]


async def main():
    """Main entry point."""
    print("\nGoogle Photos Upload Integration Test")
    print("="*60)

    # Determine test image
    if len(sys.argv) > 1:
        # Use provided path
        test_path = Path(sys.argv[1])
        if test_path.is_dir():
            # Find images in directory
            images = find_test_images(test_path)
            if images:
                print(f"Found {len(images)} images in {test_path}")
                success = await test_batch_upload(images)
            else:
                print(f"No images found in {test_path}")
                success = False
        else:
            success = await test_single_upload(test_path)
    else:
        # Create or use default test image
        test_dir = project_root / "test_images"
        test_dir.mkdir(exist_ok=True)
        test_image = test_dir / "test_upload.jpg"

        if not test_image.exists():
            print(f"No test image specified. Creating one at {test_image}...")
            if not create_test_image(test_image):
                print("\nUsage:")
                print("  python scripts/test_real_upload.py <path_to_image>")
                print("  python scripts/test_real_upload.py <directory_with_images>")
                print("\nExamples:")
                print("  python scripts/test_real_upload.py ./photos/test.jpg")
                print("  python scripts/test_real_upload.py Y:/Photos/2024")
                return 1

        success = await test_single_upload(test_image)

    print(f"\n{'='*60}")
    if success:
        print("TEST PASSED")
        return 0
    else:
        print("TEST FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
