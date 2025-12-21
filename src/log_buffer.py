"""
In-memory circular log buffer for dashboard log viewing.
"""

import logging
from collections import deque
from datetime import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class LogEntry:
    timestamp: str
    level: str
    logger: str
    message: str


class LogBuffer:
    """Circular buffer that captures log messages for API access."""

    _instance: Optional['LogBuffer'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_size: int = 500):
        if self._initialized:
            return
        self._initialized = True
        self._buffer: deque[LogEntry] = deque(maxlen=max_size)
        self._handler: Optional[logging.Handler] = None

    def install_handler(self):
        """Install a logging handler to capture all logs."""
        if self._handler:
            return

        self._handler = BufferHandler(self._buffer)
        self._handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self._handler.setFormatter(formatter)

        # Add to root logger to capture everything
        logging.getLogger().addHandler(self._handler)

    def get_logs(self, limit: int = 100, level: Optional[str] = None) -> list[dict]:
        """Get recent logs, optionally filtered by level."""
        logs = list(self._buffer)

        if level:
            level_upper = level.upper()
            logs = [log for log in logs if log.level == level_upper]

        # Return most recent first
        logs = logs[-limit:]
        logs.reverse()

        return [
            {
                "timestamp": log.timestamp,
                "level": log.level,
                "logger": log.logger,
                "message": log.message,
            }
            for log in logs
        ]


class BufferHandler(logging.Handler):
    """Logging handler that writes to a circular buffer."""

    def __init__(self, buffer: deque):
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord):
        try:
            entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
                level=record.levelname,
                logger=record.name,
                message=record.getMessage(),
            )
            self._buffer.append(entry)
        except Exception:
            self.handleError(record)


def get_log_buffer() -> LogBuffer:
    """Get the singleton log buffer."""
    return LogBuffer()
