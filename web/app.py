"""
FastAPI Web Application

Main entry point for the web dashboard.
Serves Svelte SPA frontend with JSON API.
"""

import asyncio
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.gzip import GZipMiddleware
import aiosqlite

from .api import router as api_router
from src.sync import SyncOrchestrator, set_orchestrator
from src.log_buffer import get_log_buffer

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.getenv('DATA_DIR', './data'))
CONFIG_DIR = Path(os.getenv('CONFIG_DIR', './config'))

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# Database connection
async def get_db():
    """Get database connection."""
    db_path = DATA_DIR / "gphoto_sync.db"
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row

    # Initialize schema if needed
    schema_path = Path(__file__).parent.parent / "src" / "schema.sql"
    if schema_path.exists() and not (DATA_DIR / ".initialized").exists():
        logger.info("Initializing database schema...")
        schema = schema_path.read_text()
        await db.executescript(schema)
        await db.commit()
        (DATA_DIR / ".initialized").touch()

    return db


async def recover_interrupted_jobs(db: aiosqlite.Connection, orchestrator: SyncOrchestrator):
    """Reset orphaned work batches and auto-resume interrupted jobs."""
    # First, reset ALL orphaned running batches across ALL jobs
    # This handles batches from old jobs that were never cleaned up
    cursor = await db.execute("""
        UPDATE work_batches
        SET status = 'pending', worker_id = NULL, started_at = NULL
        WHERE status = 'running'
    """)
    if cursor.rowcount > 0:
        logger.info(f"Reset {cursor.rowcount} orphaned running batches to pending")

    # Reset orphaned running tasks
    cursor = await db.execute("""
        UPDATE tasks
        SET status = 'pending'
        WHERE status = 'running'
    """)
    if cursor.rowcount > 0:
        logger.info(f"Reset {cursor.rowcount} orphaned running tasks to pending")

    await db.commit()

    # Find the most recent running job
    async with db.execute("""
        SELECT id, current_phase, source_dirs
        FROM jobs WHERE status = 'running'
        ORDER BY id DESC LIMIT 1
    """) as cursor:
        most_recent = await cursor.fetchone()

    if not most_recent:
        return

    job_id = most_recent[0]
    logger.info(f"Found interrupted job {job_id}")

    # Cancel any OTHER running jobs (shouldn't happen, but clean up)
    await db.execute("""
        UPDATE jobs SET status = 'cancelled'
        WHERE status = 'running' AND id != ?
    """, (job_id,))
    await db.commit()

    # Auto-resume the most recent interrupted job
    logger.info(f"Auto-resuming job {job_id}")
    asyncio.create_task(orchestrator.resume_sync(job_id))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Install log buffer handler to capture all logs
    log_buffer = get_log_buffer()
    log_buffer.install_handler()

    logger.info("Starting Google Photos Sync...")

    # Initialize database
    app.state.db = await get_db()

    # Initialize sync orchestrator
    orchestrator = SyncOrchestrator(app.state.db, CONFIG_DIR, DATA_DIR)
    set_orchestrator(orchestrator)
    app.state.orchestrator = orchestrator
    logger.info("Sync orchestrator initialized")

    # Check for and resume interrupted jobs
    await recover_interrupted_jobs(app.state.db, orchestrator)

    yield

    # Cleanup
    if hasattr(app.state, 'db'):
        await app.state.db.close()

    logger.info("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Google Photos Sync",
    description="NAS-native photo sync with intelligent deduplication",
    version="0.1.0",
    lifespan=lifespan,
)

# Add gzip compression for responses > 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# Serve Svelte SPA - mount assets first, then catch-all for SPA routing
if STATIC_DIR.exists():
    # Mount the assets subdirectory for JS/CSS bundles
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/{path:path}")
async def serve_spa(path: str):
    """Serve Svelte SPA for all non-API routes."""
    # Check if requested file exists in static dir
    file_path = STATIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)

    # Serve index.html for SPA routing
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    return {"error": "Frontend not built. Run 'npm run build' in frontend/"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
