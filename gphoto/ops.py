"""The running side: the flow, the first-run checklist, requests, backups, samples."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from gphoto import metrics
from gphoto.status import Status

logger = logging.getLogger(__name__)

ACTIONS = ("retry", "dismiss")
REQUEST_MOST = 4096
REQUESTS_WAITING = 50
BACKUPS_KEPT = 7
SAMPLES_KEPT = 24 * 60


# --- requests: the page asks, the owner of the database acts ----------------------


def write_request(folder: Path, action: str, path: str) -> None:
    temp = folder / f".{uuid.uuid4().hex}"
    temp.write_text(json.dumps({"action": action, "path": path}))
    os.replace(temp, folder / f"{uuid.uuid4().hex}.json")


def waiting_requests(folder: Path) -> int:
    try:
        return sum(1 for _ in folder.glob("*.json"))
    except OSError:
        return 0


def read_requests(folder: Path) -> list[tuple[str, str]]:
    """Take every request, good or bad. Whatever cannot be understood is dropped."""
    taken = []
    try:
        files = sorted(folder.glob("*.json"))[: REQUESTS_WAITING * 2]
    except OSError:
        return []
    for file in files:
        try:
            if not file.is_symlink() and file.is_file() and file.stat().st_size <= REQUEST_MOST:
                asked = json.loads(file.read_text())
                action, path = asked["action"], asked["path"]
                if action in ACTIONS and isinstance(path, str) and path:
                    taken.append((action, path))
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("Dropped a request that could not be read")
        try:
            file.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove a request")
    return taken


# --- backups ------------------------------------------------------------------------


def backup(db: sqlite3.Connection, folder: Path, name: str, day: str) -> None:
    """One consistent copy a day. The newest few are kept."""
    folder.mkdir(exist_ok=True)
    target = folder / f"{name}-{day}.db"
    if target.exists():
        return
    temp = folder / f".{name}.tmp"
    temp.unlink(missing_ok=True)
    copy = sqlite3.connect(temp)
    try:
        db.backup(copy)
    finally:
        copy.close()
    os.replace(temp, target)
    for old in sorted(folder.glob(f"{name}-*.db"))[:-BACKUPS_KEPT]:
        old.unlink()


def last_backup(state: Path) -> float | None:
    try:
        return max((p.stat().st_mtime for p in (state / "backup").glob("*.db")), default=None)
    except OSError:
        return None


# --- the flow -------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    key: str
    name: str
    what: str
    count: str
    state: str  # 'good', 'bad', or 'idle' when it is not known yet


def flow(s: Status) -> list[Step]:
    """Where photos go, and where they are stuck. A step shows only its own trouble."""
    areas = {p.area for p in s.problems}

    def state(*mine: str) -> str:
        return "bad" if areas & set(mine) else "good"

    def some(count: int) -> str:
        return f"{count:,}"

    c = s.counts
    stuck = c["failed"] + c["needs a look"]
    return [
        Step("nas", "NAS", "Photos land here", "", state("nas")),
        Step("wait", "Wait", "Time to delete bad shots", some(c["waiting"]), state("wait")),
        Step("scrub", "Scrub", "A copy is cleaned", some(stuck) if stuck else "",
             state("scrub")),
        Step("staging", "Staging", "Chrome may read it", "", state("staging")),
        Step("chrome", "Chrome", "Uploads it", some(c["on the way"]), state("chrome")),
        Step("google", "Google Photos", "Seen there", some(c["in Google"]), state("google", "search")),
    ]


# --- first run --------------------------------------------------------------------------


@dataclass(frozen=True)
class Todo:
    name: str
    done: bool
    how: str


def checklist(s: Status) -> list[Todo]:
    areas = {p.area for p in s.problems}
    reached = s.last_check is not None and not s.chrome_lost
    return [
        Todo("The NAS can be read", s.last_pass is not None and "nas" not in areas,
             "Set PHOTOS in .env to the share, which must hold year folders such as 2026."),
        Todo("Chrome is running", reached, "Run docker compose up -d on the Docker host."),
        Todo("Signed in to Google Photos", reached and s.signed_in,
             "Open Chrome, sign in, and choose Storage saver in Google Photos settings."),
        Todo("Google Photos may read the folder", reached and s.folder == "granted",
             "In Google Photos click +, Back up folders, pick /staging. Restart Chrome once,"
             " then +, Folder backup, Update permissions, Allow on every visit."),
        Todo("First photo seen in Google", s.last_arrival is not None,
             "Copy one new camera photo to the NAS and wait."),
    ]


# --- samples for the small charts -----------------------------------------------------------

SERIES = {
    "pass": ("incoming", "gphoto.pass.duration", {}),
    "waiting": ("incoming", "gphoto.waiting", {}),
    "way": ("google", "gphoto.on_the_way", {}),
    "check": ("google", "gphoto.check.duration", {}),
    "staging": ("google", "gphoto.staging.bytes", {}),
    "free": ("incoming", "gphoto.disk.free", {"mount": "state"}),
}


class Samples:
    """The last day, one reading a minute, in memory only."""

    def __init__(self, state: Path) -> None:
        self._state = state
        self._kept: dict[str, deque[tuple[float, float | None]]] = {
            name: deque(maxlen=SAMPLES_KEPT) for name in SERIES
        }

    def take(self, now: float) -> None:
        saved = {job: metrics.load(self._state, job) for job in ("incoming", "google")}
        for name, (job, metric, attributes) in SERIES.items():
            self._kept[name].append((now, metrics.value(saved[job], metric, **attributes)))

    def series(self, name: str) -> list[tuple[float, float | None]]:
        return list(self._kept[name])

    def start(self) -> None:
        def run() -> None:
            while True:
                try:
                    self.take(time.time())
                except Exception:
                    logger.exception("Could not take a sample")
                time.sleep(60)

        threading.Thread(target=run, name="samples", daemon=True).start()
