"""
In-memory metrics tracking for real-time dashboard updates.
No database writes - designed for 1-2 second polling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
from collections import deque
import time

# Rolling window for throughput calculation
ROLLING_WINDOW_SIZE = 10


@dataclass
class WorkerMetrics:
    """Per-worker real-time metrics."""
    worker_id: int
    worker_type: str  # 'hash' or 'upload'

    # Current work
    current_batch_id: Optional[int] = None
    current_batch_number: Optional[int] = None
    batch_file_count: int = 0
    files_processed: int = 0

    # Throughput tracking
    bytes_processed: int = 0
    batch_start_time: float = field(default_factory=time.time)

    # Rolling window for MB/s calculation
    throughput_samples: deque = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW_SIZE))
    files_per_second_samples: deque = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW_SIZE))

    @property
    def progress_percent(self) -> float:
        if self.batch_file_count == 0:
            return 0.0
        return (self.files_processed / self.batch_file_count) * 100

    @property
    def throughput_mbps(self) -> float:
        """Rolling average MB/s."""
        if not self.throughput_samples:
            return 0.0
        return sum(self.throughput_samples) / len(self.throughput_samples)

    @property
    def files_per_second(self) -> float:
        """Rolling average files/second."""
        if not self.files_per_second_samples:
            return 0.0
        return sum(self.files_per_second_samples) / len(self.files_per_second_samples)

    def record_file_complete(self, file_bytes: int, elapsed_seconds: float):
        """Record completion of a single file."""
        self.files_processed += 1
        self.bytes_processed += file_bytes

        if elapsed_seconds > 0:
            mb_per_second = (file_bytes / (1024 * 1024)) / elapsed_seconds
            self.throughput_samples.append(mb_per_second)
            self.files_per_second_samples.append(1.0 / elapsed_seconds)

    def record_batch_complete(self, total_bytes: int, elapsed_seconds: float, files_count: int):
        """Record completion of entire batch (for hash workers)."""
        if elapsed_seconds > 0:
            mb_per_second = (total_bytes / (1024 * 1024)) / elapsed_seconds
            self.throughput_samples.append(mb_per_second)
            self.files_per_second_samples.append(files_count / elapsed_seconds)

    def start_batch(self, batch_id: int, batch_number: int, file_count: int):
        """Start processing a new batch."""
        self.current_batch_id = batch_id
        self.current_batch_number = batch_number
        self.batch_file_count = file_count
        self.files_processed = 0
        self.bytes_processed = 0
        self.batch_start_time = time.time()

    def clear_batch(self):
        """Clear batch when done."""
        self.current_batch_id = None
        self.current_batch_number = None
        self.batch_file_count = 0
        self.files_processed = 0

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "worker_type": self.worker_type,
            "batch_id": self.current_batch_id,
            "batch_number": self.current_batch_number,
            "files_total": self.batch_file_count,
            "files_processed": self.files_processed,
            "progress_percent": round(self.progress_percent, 1),
            "throughput_mbps": round(self.throughput_mbps, 2),
            "files_per_second": round(self.files_per_second, 2),
            "idle": self.current_batch_id is None,
        }


@dataclass
class QueueMetrics:
    """Queue depth tracking for hash and upload queues."""
    hash_pending_batches: int = 0
    hash_running_batches: int = 0
    hash_pending_files: int = 0
    upload_pending_batches: int = 0
    upload_running_batches: int = 0
    upload_pending_files: int = 0

    def to_dict(self) -> dict:
        return {
            "hash": {
                "pending_batches": self.hash_pending_batches,
                "running_batches": self.hash_running_batches,
                "pending_files": self.hash_pending_files,
            },
            "upload": {
                "pending_batches": self.upload_pending_batches,
                "running_batches": self.upload_running_batches,
                "pending_files": self.upload_pending_files,
            },
        }


class MetricsRegistry:
    """
    Singleton registry for all real-time metrics.
    Holds all state in memory for fast access.
    """
    _instance: Optional['MetricsRegistry'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.workers: Dict[int, WorkerMetrics] = {}
        self.queue = QueueMetrics()

        # Job-level metrics
        self.current_job_id: Optional[int] = None
        self.job_started_at: Optional[datetime] = None
        self.job_total_files: int = 0

    def get_or_create_worker(self, worker_id: int, worker_type: str) -> WorkerMetrics:
        """Get or create worker metrics."""
        if worker_id not in self.workers:
            self.workers[worker_id] = WorkerMetrics(
                worker_id=worker_id,
                worker_type=worker_type
            )
        return self.workers[worker_id]

    def update_queue_depths(
        self,
        hash_pending_batches: int = 0,
        hash_running_batches: int = 0,
        hash_pending_files: int = 0,
        upload_pending_batches: int = 0,
        upload_running_batches: int = 0,
        upload_pending_files: int = 0,
    ):
        """Update queue depth metrics."""
        self.queue.hash_pending_batches = hash_pending_batches
        self.queue.hash_running_batches = hash_running_batches
        self.queue.hash_pending_files = hash_pending_files
        self.queue.upload_pending_batches = upload_pending_batches
        self.queue.upload_running_batches = upload_running_batches
        self.queue.upload_pending_files = upload_pending_files

    def start_job(self, job_id: int, total_files: int = 0):
        """Record job start."""
        self.current_job_id = job_id
        self.job_started_at = datetime.now()
        self.job_total_files = total_files
        self.workers.clear()  # Reset worker metrics for new job

    def end_job(self):
        """Record job end."""
        self.current_job_id = None
        self.job_started_at = None
        self.job_total_files = 0

    def to_dict(self) -> dict:
        """Export all metrics for API response."""
        # Group workers by type
        hash_workers = [w.to_dict() for w in self.workers.values() if w.worker_type == 'hash']
        upload_workers = [w.to_dict() for w in self.workers.values() if w.worker_type == 'upload']

        # Calculate totals
        active_hash = sum(1 for w in hash_workers if not w["idle"])
        active_upload = sum(1 for w in upload_workers if not w["idle"])

        total_hash_mbps = sum(w["throughput_mbps"] for w in hash_workers if not w["idle"])
        total_upload_mbps = sum(w["throughput_mbps"] for w in upload_workers if not w["idle"])

        total_hash_fps = sum(w["files_per_second"] for w in hash_workers if not w["idle"])
        total_upload_fps = sum(w["files_per_second"] for w in upload_workers if not w["idle"])

        return {
            "job_id": self.current_job_id,
            "job_running": self.current_job_id is not None,
            "job_duration_seconds": (
                (datetime.now() - self.job_started_at).total_seconds()
                if self.job_started_at else 0
            ),
            "job_total_files": self.job_total_files,
            "queue": self.queue.to_dict(),
            "hash_workers": hash_workers,
            "upload_workers": upload_workers,
            "summary": {
                "hash_active": active_hash,
                "hash_total": len(hash_workers),
                "hash_throughput_mbps": round(total_hash_mbps, 2),
                "hash_files_per_second": round(total_hash_fps, 2),
                "upload_active": active_upload,
                "upload_total": len(upload_workers),
                "upload_throughput_mbps": round(total_upload_mbps, 2),
                "upload_files_per_second": round(total_upload_fps, 2),
            }
        }


# Global singleton accessor
def get_metrics() -> MetricsRegistry:
    return MetricsRegistry()
