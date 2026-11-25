"""Numbers kept in memory by each process, with a snapshot file others can read."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from bisect import bisect_left
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SECONDS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
MINUTES = (60, 300, 900, 1800, 3600, 7200, 14400, 43200, 86400)


class Metrics:
    """Counters and histograms start at zero with the process. 'started' says when."""

    def __init__(
        self,
        job: str,
        state: Path,
        clock: Callable[[], float] = time.time,
        version: str | None = None,
    ) -> None:
        self.job = job
        self._path = state / f"metrics-{job}.json"
        self._clock = clock
        self._started = clock()
        self._version = version or os.getenv("GPHOTO_VERSION", "unknown")
        self._metrics: dict[str, dict[str, Any]] = {}

    def _point(self, name: str, kind: str, unit: str, help_: str, attributes: dict) -> dict:
        metric = self._metrics.setdefault(
            name, {"type": kind, "unit": unit, "help": help_, "points": []}
        )
        for point in metric["points"]:
            if point["attributes"] == attributes:
                return point
        point = {"attributes": attributes}
        metric["points"].append(point)
        return point

    def add(self, name: str, value: float, unit: str, help_: str, **attributes: str) -> None:
        point = self._point(name, "counter", unit, help_, attributes)
        point["value"] = point.get("value", 0) + value

    def set(self, name: str, value: float, unit: str, help_: str, **attributes: str) -> None:
        self._point(name, "gauge", unit, help_, attributes)["value"] = value

    def record(
        self, name: str, value: float, unit: str, help_: str,
        bounds: tuple[float, ...] = SECONDS, **attributes: str,
    ) -> None:
        point = self._point(name, "histogram", unit, help_, attributes)
        if "count" not in point:
            point.update(
                count=0, sum=0.0, min=value, max=value, bounds=list(bounds),
                buckets=[0] * (len(bounds) + 1),
            )
        point["count"] += 1
        point["sum"] += value
        point["min"] = min(point["min"], value)
        point["max"] = max(point["max"], value)
        point["buckets"][bisect_left(point["bounds"], value)] += 1

    def disk(self, name: str, folder: Path) -> None:
        try:
            usage = shutil.disk_usage(folder)
        except OSError:
            return
        self.set("gphoto.disk.free", usage.free, "By", "Free space", mount=name)
        self.set("gphoto.disk.size", usage.total, "By", "Size of the disk", mount=name)

    def save(self) -> None:
        """Replace the snapshot in one step. A fault here must never stop photos."""
        temp = self._path.with_name(f".{self._path.name}.tmp")
        try:
            temp.write_text(
                json.dumps(
                    {
                        "job": self.job, "at": self._clock(), "started": self._started,
                        "version": self._version, "metrics": self._metrics,
                    }
                )
            )
            os.replace(temp, self._path)
        except OSError:
            logger.warning("Could not save metrics", exc_info=True)
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def load(state: Path, job: str) -> dict[str, Any] | None:
    """A snapshot, or None when it is missing or cannot be understood."""
    try:
        saved = json.loads((state / f"metrics-{job}.json").read_text())
        return saved if isinstance(saved, dict) and isinstance(saved["metrics"], dict) else None
    except (OSError, ValueError, KeyError):
        return None


def value(snapshot: dict[str, Any] | None, name: str, **attributes: str) -> float | None:
    """One gauge or counter out of a snapshot."""
    try:
        for point in snapshot["metrics"][name]["points"]:
            if all(point["attributes"].get(k) == v for k, v in attributes.items()):
                return point["value"]
    except (TypeError, KeyError, AttributeError):
        pass
    return None
