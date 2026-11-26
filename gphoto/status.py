"""Turn the two state databases into one answer: is it working, and if not, why?"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from gphoto import metrics

PASS_STALE = 15 * 60
CHECK_STALE = 10 * 60
ARRIVAL_LATE = 2 * 3600
WAITING_LATE = 3600
LOW_DISK = 2e9  # about 200 photos of staging
CLOCK_SLACK = 5 * 60
RECENT = 200

STAGES = ("waiting", "on the way", "in Google", "skipped", "needs a look", "failed")
RESTART = "On the Docker host run: docker compose up -d"

# Proof made before a photo was sent belongs to an earlier photo at the same path.
# The checker notes the time before which every sent photo is proved.
ON_THE_WAY = """
    FROM incoming i LEFT JOIN goo.confirmed c ON c.path = i.path AND c.at >= i.sent_at
    WHERE i.status = 'sent' AND i.sent_at >= (SELECT settled FROM goo.done) AND c.path IS NULL
"""
STAGE_OF = {"waiting": "waiting", "failed": "failed", "look": "needs a look"}


@dataclass(frozen=True)
class Problem:
    title: str
    fix: str
    area: str  # the step of the flow it belongs to


@dataclass(frozen=True)
class Photo:
    name: str
    folder: str
    stage: str
    taken: str | None
    landed: float
    due: float | None
    sent_at: float | None
    confirmed_at: float | None
    reason: str | None


@dataclass(frozen=True)
class Status:
    now: float
    problems: list[Problem]
    counts: dict[str, int]
    photos: list[Photo] = field(default_factory=list)
    last_pass: float | None = None
    last_check: float | None = None
    last_arrival: float | None = None
    chrome_lost: bool = False
    signed_in: bool = False
    folder: str | None = None

    @property
    def ok(self) -> bool:
        return not self.problems


def _stale(now: float, then: float, limit: float) -> bool:
    return now - then > limit or then - now > CLOCK_SLACK


def _tool_problems(beat: sqlite3.Row | None, now: float) -> list[Problem]:
    if beat is None or _stale(now, beat["at"], PASS_STALE):
        return [
            Problem(
                "The NAS check has not run",
                f"Check the NAS is up, because a stalled NAS stops the check. Then: {RESTART}",
                "nas",
            )
        ]
    if beat["error"]:
        return [
            Problem(
                f"Some NAS photos cannot be read: {beat['error']}",
                "Check the NAS is up, and that the share is mounted and readable.",
                "nas",
            )
        ]
    return []


def _google_problems(health: sqlite3.Row | None, now: float) -> list[Problem]:
    if health is None or _stale(now, health["checked_at"], CHECK_STALE):
        return [Problem("Google has not been checked", RESTART, "chrome")]
    if health["error"]:
        return [Problem(f"Chrome cannot be reached: {health['error']}", RESTART, "chrome")]
    problems = []
    if not health["signed_in"]:
        problems.append(
            Problem(
                "Google Photos is signed out",
                "Open Chrome on the Docker host and sign in to Google.",
                "chrome",
            )
        )
    elif health["folder"] != "granted":
        problems.append(
            Problem(
                "Google Photos has lost permission to the folder",
                "Open Chrome on the Docker host. Click +, Folder backup, Update permissions,"
                " Allow on every visit.",
                "staging",
            )
        )
    if health["search_error"]:
        problems.append(
            Problem(
                f"Arrival cannot be checked: {health['search_error']}",
                "Photos may still be going. Google may have changed its page or its language.",
                "search",
            )
        )
    return problems


def _disk_problems(state: Path) -> list[Problem]:
    """Said early. A full disk otherwise shows only as photos overdue, hours later."""
    saved = metrics.load(state, "incoming")
    free = [
        v for v in (metrics.value(saved, "gphoto.disk.free", mount=m) for m in ("state", "staging"))
        if v is not None
    ]
    if not free or min(free) >= LOW_DISK:
        return []
    return [
        Problem(
            f"Disk space is low on the Docker host: {min(free) / 1e9:.1f} GB free",
            "Free some space. Photos wait while it is full and go by themselves after.",
            "staging",
        )
    ]


def _some(count: int, one: str, many: str) -> str:
    return f"1 photo {one}" if count == 1 else f"{count} photos {many}"


def _photo_problems(
    db: sqlite3.Connection, counts: dict[str, int], now: float, wait_seconds: float
) -> list[Problem]:
    problems = []
    if counts["failed"]:
        problems.append(
            Problem(
                _some(counts["failed"], "failed", "failed"),
                "The reason is beside each one. Fix or delete the file, or dismiss it.",
                "scrub",
            )
        )
    if counts["needs a look"]:
        problems.append(
            Problem(
                _some(counts["needs a look"], "needs a look", "need a look"),
                "A camera photo was left out, often because the camera clock is wrong."
                " The reason is beside it. Fix the date, or dismiss it.",
                "scrub",
            )
        )
    overdue = db.execute(
        "SELECT COUNT(*) FROM incoming WHERE status = 'waiting' AND landed < ?",
        (now - wait_seconds - WAITING_LATE,),
    ).fetchone()[0]
    if overdue:
        problems.append(
            Problem(
                _some(overdue, "is overdue", "are overdue"),
                "The reason is beside each one. A full disk or a slow NAS is retried by itself.",
                "wait",
            )
        )
    late = db.execute(
        f"SELECT COUNT(*) {ON_THE_WAY} AND i.sent_at < ?", (now - ARRIVAL_LATE,)
    ).fetchone()[0]
    if late:
        problems.append(
            Problem(
                _some(late, "has not arrived in Google", "have not arrived in Google"),
                "Open Chrome on the Docker host and check Folder backup for an error.",
                "google",
            )
        )
    return problems


def _photo(row: sqlite3.Row, stage: str, confirmed: float | None, wait_seconds: float) -> Photo:
    folder, _, name = row["path"].rpartition("/")
    due = max(row["landed"] + wait_seconds, row["retry_at"] or 0)
    return Photo(
        name=name, folder=folder, stage=stage, taken=row["taken"] or None,
        landed=row["landed"], due=due if stage == "waiting" else None,
        sent_at=row["sent_at"], confirmed_at=confirmed, reason=row["reason"],
    )


def _recent(db: sqlite3.Connection, wait_seconds: float) -> list[Photo]:
    """What needs attention first, then the newest. Every query is indexed and limited."""
    photos: list[Photo] = []

    def newest(*statuses: str) -> list[sqlite3.Row]:
        rows: list[sqlite3.Row] = []
        for status in statuses:
            rows += db.execute(
                "SELECT * FROM incoming WHERE status = ? ORDER BY landed DESC LIMIT ?",
                (status, RECENT),
            ).fetchall()
        return sorted(rows, key=lambda r: (-r["landed"], r["path"]))

    def add(rows: list[sqlite3.Row], stage: Callable[[sqlite3.Row], str]) -> None:
        photos.extend(_photo(r, stage(r), None, wait_seconds) for r in rows)

    add(newest("failed", "look"), lambda r: STAGE_OF[r["status"]])
    add(newest("waiting"), lambda r: "waiting")
    way = db.execute(
        f"SELECT i.* {ON_THE_WAY} ORDER BY i.landed DESC, i.path LIMIT ?", (RECENT,)
    ).fetchall()
    add(way, lambda r: "on the way")
    on_the_way = {r["path"] for r in way}
    for row in newest("sent"):
        proof = db.execute(
            "SELECT at FROM goo.confirmed WHERE path = ? AND at >= ?", (row["path"], row["sent_at"])
        ).fetchone()
        if proof and row["path"] not in on_the_way:
            photos.append(_photo(row, "in Google", proof["at"], wait_seconds))
    add(newest("skipped", "duplicate", "dismissed"), lambda r: "skipped")
    return photos[:RECENT]


def read(state: Path, now: float, wait_seconds: float) -> Status:
    """Read only. A missing or older database is a problem to show, not a crash."""
    counts = dict.fromkeys(STAGES, 0)
    beat = health = None
    photos: list[Photo] = []
    photo_problems: list[Problem] = []
    last_arrival = None
    try:
        db = sqlite3.connect(f"{(state / 'incoming.db').absolute().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return Status(now, _tool_problems(None, now) + _google_problems(None, now), counts)
    db.row_factory = sqlite3.Row
    try:
        beat = db.execute("SELECT * FROM heartbeat").fetchone()
        db.execute("ATTACH ? AS goo", (f"{(state / 'google.db').absolute().as_uri()}?mode=ro",))
        health = db.execute("SELECT * FROM goo.health").fetchone()
        last_arrival = db.execute("SELECT MAX(at) FROM goo.confirmed").fetchone()[0]
        for row in db.execute("SELECT status, COUNT(*) AS n FROM incoming GROUP BY status"):
            sent = "in Google" if row["status"] == "sent" else "skipped"
            counts[STAGE_OF.get(row["status"], sent)] += row["n"]
        counts["on the way"] = db.execute(f"SELECT COUNT(*) {ON_THE_WAY}").fetchone()[0]
        counts["in Google"] -= counts["on the way"]
        photos = _recent(db, wait_seconds)
        photo_problems = _photo_problems(db, counts, now, wait_seconds)
    except (sqlite3.Error, IndexError):
        pass  # whatever is missing is shown as not run or not checked
    finally:
        db.close()
    return Status(
        now=now,
        problems=_tool_problems(beat, now) + _google_problems(health, now) + photo_problems
        + _disk_problems(state),
        counts=counts,
        photos=photos,
        last_pass=beat["at"] if beat else None,
        last_check=health["checked_at"] if health else None,
        last_arrival=last_arrival,
        chrome_lost=health is None or bool(health["error"]),
        signed_in=bool(health and health["signed_in"]),
        folder=health["folder"] if health else None,
    )


@dataclass(frozen=True)
class Page:
    items: list[Photo]
    total: int
    page: int
    pages: int


_PROOF = "goo.confirmed c ON c.path = i.path AND c.at >= i.sent_at"
_NOT_SEEN = "i.sent_at >= (SELECT settled FROM goo.done) AND c.path IS NULL"
# In the order they are shown: what needs attention first.
_GROUPS = (
    ("failed", "i.status = 'failed'"),
    ("needs a look", "i.status = 'look'"),
    ("waiting", "i.status = 'waiting'"),
    ("on the way", f"i.status = 'sent' AND {_NOT_SEEN}"),
    ("in Google", f"i.status = 'sent' AND NOT ({_NOT_SEEN})"),
    ("skipped", "i.status IN ('skipped', 'duplicate', 'dismissed')"),
)


def photos(
    state: Path, wait_seconds: float, page: int = 1, search: str = "", stage: str = "",
    size: int = 50,
) -> Page:
    """One page of photos. Each group is counted and read on its own, so a page deep in
    a long list does not sort everything."""
    groups = [g for g in _GROUPS if not stage or g[0] == stage]
    extra, values = "", []
    if search:
        literal = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        extra, values = " AND i.path LIKE ? ESCAPE '\\'", [f"%{literal}%"]
    found: list[Photo] = []
    try:
        db = sqlite3.connect(f"{(state / 'incoming.db').absolute().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return Page([], 0, 1, 1)
    db.row_factory = sqlite3.Row
    try:
        db.execute("ATTACH ? AS goo", (f"{(state / 'google.db').absolute().as_uri()}?mode=ro",))
        base = f"FROM incoming i LEFT JOIN {_PROOF} WHERE "
        counts = [
            db.execute(f"SELECT COUNT(*) {base}{where}{extra}", values).fetchone()[0]
            for _, where in groups
        ]
        total = sum(counts)
        pages = max(1, -(-total // size))
        page = min(max(1, page), pages)
        skip = (page - 1) * size
        for (name, where), count in zip(groups, counts, strict=True):
            if skip >= count:
                skip -= count
                continue
            rows = db.execute(
                f"SELECT i.*, c.at AS seen {base}{where}{extra}"
                " ORDER BY i.landed DESC, i.path LIMIT ? OFFSET ?",
                (*values, size - len(found), skip),
            ).fetchall()
            found += [_photo(r, name, r["seen"], wait_seconds) for r in rows]
            skip = 0
            if len(found) >= size:
                break
        return Page(found, total, page, pages)
    except (sqlite3.Error, IndexError):
        return Page([], 0, 1, 1)
    finally:
        db.close()


def known(state: Path, path: str) -> bool:
    try:
        db = sqlite3.connect(f"{(state / 'incoming.db').absolute().as_uri()}?mode=ro", uri=True)
        try:
            return bool(db.execute("SELECT 1 FROM incoming WHERE path = ?", (path,)).fetchone())
        finally:
            db.close()
    except sqlite3.Error:
        return False


def per_day(state: Path, now: float, zone: ZoneInfo, days: int = 30) -> list[tuple[str, int]]:
    """Photos seen in Google on each of the last days, oldest first."""
    today = datetime.fromtimestamp(now, zone).date()
    counts = {(today - timedelta(days=n)).isoformat(): 0 for n in range(days - 1, -1, -1)}
    try:
        db = sqlite3.connect(f"{(state / 'google.db').absolute().as_uri()}?mode=ro", uri=True)
        try:
            for (at,) in db.execute(
                "SELECT at FROM confirmed WHERE at >= ?", (now - (days + 1) * 86400,)
            ):
                day = datetime.fromtimestamp(at, zone).date().isoformat()
                if day in counts:
                    counts[day] += 1
        finally:
            db.close()
    except sqlite3.Error:
        pass
    return list(counts.items())
