"""What happened, and when. One table in each database, written by its owner."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

KEEP = 90 * 24 * 3600

TROUBLE = (
    "failed", "look", "retrying", "nas_down", "pass_error", "chrome_down", "signed_out",
    "folder_lost", "search_broken",
)
WORDS = {
    "landed": "Landed on the NAS", "scrubbed": "Scrubbed", "sent": "Handed to Chrome",
    "skipped": "Skipped", "look": "Left out, needs a look", "failed": "Failed",
    "retrying": "Will try again", "gone": "Deleted before it was sent",
    "changed": "Changed on the NAS", "retry": "You asked to send it again",
    "dismiss": "You dismissed it", "seen": "Seen in Google", "tidied": "Staged copy removed",
    "nas_down": "NAS lost", "nas_up": "NAS back", "pass_error": "Some folders not read",
    "pass_ok": "All folders read again", "started": "Started",
    "chrome_down": "Chrome lost", "chrome_up": "Chrome back",
    "signed_out": "Google signed out", "signed_in": "Google signed in",
    "folder_lost": "Folder permission lost", "folder_ok": "Folder permission back",
    "search_broken": "Arrival check broken", "search_ok": "Arrival check working",
    "reloaded": "Google Photos reloaded",
}


@dataclass(frozen=True)
class Event:
    at: float
    kind: str
    path: str | None
    detail: str | None
    job: str
    id: int = 0

    @property
    def words(self) -> str:
        return WORDS.get(self.kind, self.kind)

    @property
    def trouble(self) -> bool:
        return self.kind in TROUBLE


def prepare(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " at REAL NOT NULL, kind TEXT NOT NULL, path TEXT, detail TEXT)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS events_at ON events (at)")
    db.execute("CREATE INDEX IF NOT EXISTS events_path ON events (path)")


def add(
    db: sqlite3.Connection, at: float, kind: str, path: str | None = None, detail: str | None = None
) -> None:
    """The caller commits, so that an event and what it describes are saved together."""
    db.execute(
        "INSERT INTO events (at, kind, path, detail) VALUES (?, ?, ?, ?)",
        (at, kind, path, detail[:500] if detail else None),
    )


def prune(db: sqlite3.Connection, now: float) -> None:
    db.execute("DELETE FROM events WHERE at < ?", (now - KEEP,))


def last_kind(db: sqlite3.Connection, *kinds: str) -> str | None:
    marks = ",".join("?" * len(kinds))
    row = db.execute(
        f"SELECT kind FROM events WHERE kind IN ({marks}) ORDER BY id DESC LIMIT 1", kinds
    ).fetchone()
    return row[0] if row else None


def page(
    state: Path, size: int, path: str | None = None, trouble: bool = False,
    after: str | None = None,
) -> tuple[list[Event], str | None]:
    """Newest first, one page at a time. Returns the events and the cursor of the next page.

    Order is time, then database, then row, so events in the same second are neither
    lost nor shown twice. A cursor that cannot be read starts from the newest.
    """
    mark = _cursor(after)
    found: list[Event] = []
    for job in ("google", "incoming"):
        where, values = _where(path, trouble)
        if mark:
            at, last_job, last_id = mark
            if job == last_job:
                where.append("(at < ? OR (at = ? AND id < ?))")
                values += [at, at, last_id]
            else:
                where.append("at < ?" if job < last_job else "at <= ?")
                values.append(at)
        found += _read(state, job, where, values, size + 1)
    found.sort(key=lambda e: (-e.at, e.job, -e.id))
    more = len(found) > size
    found = found[:size]
    return found, f"{found[-1].at!r}:{found[-1].job}:{found[-1].id}" if more else None


def _cursor(text: str | None) -> tuple[float, str, int] | None:
    try:
        at, job, row = (text or "").split(":")
        return (float(at), job, int(row)) if job in ("google", "incoming") else None
    except ValueError:
        return None


def _where(path: str | None, trouble: bool) -> tuple[list[str], list]:
    where, values = ["1 = 1"], []
    if path is not None:
        where.append("path = ?")
        values.append(path)
    if trouble:
        where.append(f"kind IN ({','.join('?' * len(TROUBLE))})")
        values += TROUBLE
    return where, values


def _read(state: Path, job: str, where: list[str], values: list, limit: int) -> list[Event]:
    """A missing database is simply not there yet."""
    try:
        db = sqlite3.connect(f"{(state / f'{job}.db').absolute().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        return [
            Event(at, kind, about, detail, job, row)
            for row, at, kind, about, detail in db.execute(
                f"SELECT id, at, kind, path, detail FROM events WHERE {' AND '.join(where)}"
                " ORDER BY at DESC, id DESC LIMIT ?",
                (*values, limit),
            )
        ]
    except sqlite3.Error:
        return []
    finally:
        db.close()


def history(
    state: Path, limit: int = 200, path: str | None = None, trouble: bool = False
) -> list[Event]:
    """Newest first, from both databases."""
    return page(state, limit, path, trouble)[0]
