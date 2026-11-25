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


def history(
    state: Path, limit: int = 200, path: str | None = None, trouble: bool = False
) -> list[Event]:
    """Newest first, from both databases. A missing one is simply not there yet."""
    where, values = ["1 = 1"], []
    if path is not None:
        where.append("path = ?")
        values.append(path)
    if trouble:
        where.append(f"kind IN ({','.join('?' * len(TROUBLE))})")
        values += TROUBLE
    found: list[Event] = []
    for job in ("incoming", "google"):
        try:
            db = sqlite3.connect(f"{(state / f'{job}.db').absolute().as_uri()}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            found += [
                Event(at, kind, about, detail, job)
                for at, kind, about, detail in db.execute(
                    f"SELECT at, kind, path, detail FROM events WHERE {' AND '.join(where)}"
                    " ORDER BY at DESC, id DESC LIMIT ?",
                    (*values, limit),
                )
            ]
        except sqlite3.Error:
            pass
        finally:
            db.close()
    return sorted(found, key=lambda e: -e.at)[:limit]
