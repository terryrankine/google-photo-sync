"""Incoming photos: wait, scrub, hand over to staging.

Google Photos keeps a D7100 JPEG at full size while it carries an MPF block.
With the block gone the same photo is stored as Storage saver. A browser signed
in to Google Photos watches the staging folder and does the upload.

Phone files also carry MPF, but theirs is an HDR gain map. They are never touched.

scrub.py says which tags may go. This checks that nothing else did.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from PIL import Image

from gphoto import events, ops, scrub
from gphoto.metrics import Metrics
from gphoto.scrub import StripError

logger = logging.getLogger(__name__)

EXTENSIONS = {".jpg", ".jpeg"}
IGNORED_DIRS = {"@eaDir", "#recycle", "@Recycle", "$RECYCLE.BIN"}
TEMP_PREFIX = ".gphoto-"
EXIFTOOL_TIMEOUT = 120
RETRY_AFTER = 15 * 60
BEAT_EVERY = 60
REQUEST_EVERY = 5
FULL_PASS_EVERY = 24 * 3600
# Longer than the 60 s an NFS client may keep a folder's old attributes.
SETTLED_AFTER = 120
FORGETTABLE = ("waiting", "failed", "look", "skipped", "dismissed")


class RootUnavailable(RuntimeError):
    """The photo folder has no year folders, so the mount is probably down."""


class Action(Enum):
    STRIP = "strip"
    SEND = "send"
    SKIP = "skip"


@dataclass(frozen=True)
class PhotoInfo:
    make: str
    taken: datetime | None
    mpf_types: tuple[str, ...]
    found: frozenset[str] = frozenset()  # scrub groups that have something to remove

    def made_by(self, cameras: tuple[str, ...]) -> bool:
        return self.make.upper().startswith(tuple(prefix.upper() for prefix in cameras))


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str


def _exiftool(*args: str) -> bytes:
    result = subprocess.run(["exiftool", *args], capture_output=True, timeout=EXIFTOOL_TIMEOUT)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout[:500]).decode("utf-8", "replace").strip()
        raise RuntimeError(f"exiftool failed: {detail}")
    return result.stdout


def _tags(path: Path, *options: str) -> dict[scrub.Tag, tuple[str, ...]]:
    return scrub.read_tags(json.loads(_exiftool("-j", "-a", "-G0:1:4", *options, str(path)))[0])


def _first(tags: scrub.Tags, *tag: str) -> str:
    return next(iter(tags.get(scrub.Tag(*tag), ())), "")


def inspect(path: Path) -> PhotoInfo:
    """Read what the rules need from one JPEG."""
    tags = _tags(path)
    if _first(tags, "File", "File", "FileType") not in ("JPEG", "MPO"):
        raise ValueError(f"not a JPEG: {path}")
    taken = None
    raw = _first(tags, "EXIF", "ExifIFD", "DateTimeOriginal")
    if raw:
        try:
            taken = datetime.strptime(raw[:19], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            logger.warning("Unreadable capture date %r in %s", raw, path)
    return PhotoInfo(
        make=_first(tags, "EXIF", "IFD0", "Make"),
        taken=taken,
        mpf_types=scrub.mpf_types(tags),
        found=frozenset(scrub.Rules(tuple(scrub.GROUPS)).found(tags)),
    )


def decide(
    info: PhotoInfo,
    since: date,
    cameras: tuple[str, ...] = scrub.DEFAULT_CAMERAS,
    rules: scrub.Rules = scrub.DEFAULT_RULES,
) -> Decision:
    """Strip, send or skip. Anything not understood is skipped."""
    if not info.made_by(cameras):
        wanted = " or ".join(prefix.capitalize() for prefix in cameras)
        return Decision(Action.SKIP, f"not a {wanted} ({info.make or 'no make'})")
    if info.taken is None:
        return Decision(Action.SKIP, "no capture date")
    if info.taken.date() < since:
        return Decision(Action.SKIP, f"taken before {since}")
    unknown = scrub.unknown_mpf(info.mpf_types)
    if unknown:
        return Decision(Action.SKIP, f"unknown MPF content: {', '.join(unknown)}")
    work = [name for name in rules.names if name in info.found]
    if work == ["mpf"]:
        return Decision(Action.STRIP, f"{info.make.split()[0].capitalize()} MPF preview")
    if work:
        return Decision(Action.STRIP, f"removing {', '.join(work)}")
    nothing = "no MPF" if rules == scrub.DEFAULT_RULES else "nothing to remove"
    return Decision(Action.SEND, nothing)


def _remove(src: Path, dst: Path, arguments: list[str]) -> None:
    # Through a pipe, because exiftool expands % codes in an output file name.
    dst.write_bytes(_exiftool(*arguments, "-o", "-", str(src)))


def _remove_mpf(src: Path, dst: Path) -> None:
    _remove(src, dst, scrub.MPF_ARGUMENTS)


def _pixels(path: Path) -> str:
    with Image.open(path) as image:
        return hashlib.sha256(image.tobytes()).hexdigest()


def _fingerprint(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def scrub_to(
    path: Path, target: Path, rules: scrub.Rules = scrub.DEFAULT_RULES
) -> list[str]:
    """Write a copy of path without what the rules name. Returns the groups removed.

    Raises, and leaves no file, if anything else would differ. With nothing to remove
    the copy is the same bytes, because Google matches a photo on its bytes.
    """
    before = path.stat()
    target.unlink(missing_ok=True)
    try:
        old = _tags(path, "-b")
        unknown = scrub.unknown_mpf(scrub.mpf_types(old))
        if unknown:
            raise StripError(f"unknown MPF content: {', '.join(unknown)}")
        done = rules.found(old)
        if done:
            _scrub_checked(path, target, scrub.Rules(tuple(done)), old)
        else:
            shutil.copyfile(path, target)
        with target.open("rb+") as handle:
            os.fsync(handle.fileno())
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        if _fingerprint(path) != (before.st_size, before.st_mtime_ns):
            raise StripError("file changed while stripping")
        return done
    except StripError as error:
        target.unlink(missing_ok=True)
        raise StripError(f"{error}: {path}") from error
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _scrub_checked(path: Path, target: Path, rules: scrub.Rules, old: scrub.Tags) -> None:
    arguments = rules.arguments(old)
    only_mpf = arguments == scrub.MPF_ARGUMENTS
    if only_mpf:
        _remove_mpf(path, target)
    else:
        _remove(path, target, arguments)
    if _pixels(target) != _pixels(path):
        raise StripError("pixels would change")
    new = _tags(target, "-b")
    rules.check_gone(new)
    rules.check(old, new)
    if not only_mpf:
        # Unknown tags and embedded images too, where a leftover would go unseen.
        rules.check_gone(_tags(target, "-u", "-U", "-ee"))
        rules.check_serial_text(old, target.read_bytes())


def strip_in_place(path: Path, rules: scrub.Rules = scrub.DEFAULT_RULES) -> list[str]:
    """Scrub the file itself. Replaces it only if the photo is provably unchanged.

    Permissions are not copied. chmod on a Synology share would replace the
    inherited ACL, and a new file in the folder inherits the right one.
    """
    temp = path.with_name(f"{TEMP_PREFIX}{path.name}")
    try:
        done = scrub_to(path, temp, rules)
        if done:
            os.replace(temp, path)
        return done
    finally:
        temp.unlink(missing_ok=True)


def _sha1(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha1").hexdigest()


def _ctime(path: Path) -> float:
    # mtime is the capture time, because copying keeps it. ctime is set when the
    # file lands on the NAS and is never earlier than that.
    return path.stat().st_ctime


@dataclass
class _Folder:
    """What one listing found, kept so an unchanged folder need not be listed again."""

    mtime_ns: int
    subfolders: list[str]


class Runner:
    """One pass per tick over the photo folder. State lives in SQLite.

    Statuses: waiting, sent, duplicate, skipped (a phone or too old to matter), look (a
    camera photo that was left out), failed (the file itself is bad), dismissed.
    """

    def __init__(
        self,
        root: Path,
        staging: Path,
        db_path: Path,
        since: date,
        wait_seconds: float,
        clock: Callable[[], float] = time.time,
        landed_at: Callable[[Path], float] = _ctime,
        dry_run: bool = False,
        in_place: bool = False,
        requests: Path | None = None,
        rules: scrub.Rules = scrub.DEFAULT_RULES,
        cameras: tuple[str, ...] = scrub.DEFAULT_CAMERAS,
    ) -> None:
        self.root = root
        self.staging = staging
        self.since = since
        self.wait_seconds = wait_seconds
        self.clock = clock
        self.landed_at = landed_at
        self.dry_run = dry_run
        self.in_place = in_place
        self.requests = requests
        self.rules = rules
        self.cameras = cameras
        self._state = db_path.parent
        self.metrics = Metrics("incoming", self._state, clock)
        self._listed = self._checked = 0
        self._cutoff = datetime.combine(since, datetime.min.time()).timestamp()
        self._folders: dict[str, _Folder] = {}
        self._full_at = float("-inf")
        self._beat_at = float("-inf")
        self._announced = False
        self._work = db_path.parent / "work"
        self._work.mkdir(exist_ok=True)
        self._db = sqlite3.connect(db_path, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._prepare()

    def _prepare(self) -> None:
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS incoming (
                   path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                   landed REAL NOT NULL, status TEXT NOT NULL, reason TEXT, sha1 TEXT)"""
        )
        have = {r["name"] for r in self._db.execute("PRAGMA table_info(incoming)")}
        for column, kind in (
            ("taken", "TEXT"), ("staged", "TEXT"), ("sent_at", "REAL"), ("retry_at", "REAL"),
        ):
            if column not in have:
                self._db.execute(f"ALTER TABLE incoming ADD COLUMN {column} {kind}")
        # Rows from before sent_at existed. Queries rely on it being set.
        self._db.execute(
            "UPDATE incoming SET sent_at = landed WHERE status = 'sent' AND sent_at IS NULL"
        )
        for name, columns in (
            ("landed", "status, landed"), ("sent", "status, sent_at"),
            ("day", "status, taken"), ("sha1", "sha1"),
        ):
            self._db.execute(f"CREATE INDEX IF NOT EXISTS incoming_{name} ON incoming ({columns})")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS heartbeat"
            " (id INTEGER PRIMARY KEY CHECK (id = 1), at REAL NOT NULL, error TEXT)"
        )
        events.prepare(self._db)
        self._db.commit()

    def _event(self, kind: str, path: str | None = None, detail: str | None = None,
               at: float | None = None) -> None:
        if not self.dry_run:
            events.add(self._db, self.clock() if at is None else at, kind, path, detail)

    # --- what the owner can do -------------------------------------------------

    def status(self, relative: str) -> str | None:
        row = self._row(relative)
        return row["status"] if row else None

    def retry(self, relative: str) -> bool:
        """Send this photo again at the next pass."""
        return self._set("retry", relative, "waiting", landed=0)

    def dismiss(self, relative: str) -> bool:
        """Stop showing this photo as a problem."""
        return self._set("dismiss", relative, "dismissed")

    def take_requests(self) -> bool:
        """Act on what was asked on the page. Returns whether anything was done."""
        if self.requests is None:
            return False
        act = {"retry": self.retry, "dismiss": self.dismiss}
        return any([act[action](path) for action, path in ops.read_requests(self.requests)])

    def _set(self, kind: str, relative: str, status: str, landed: float | None = None) -> bool:
        done = self._db.execute(
            "UPDATE incoming SET status = ?, landed = COALESCE(?, landed), reason = NULL,"
            " retry_at = NULL, sha1 = NULL WHERE path = ?",
            (status, landed, relative),
        ).rowcount
        if done:
            self._event(kind, relative)
        self._db.commit()
        return bool(done)

    def refuse(self, why: str) -> None:
        """Say on the page that the settings are wrong."""
        self._beat(why)

    # --- one pass ----------------------------------------------------------------

    def tick(self) -> None:
        began = time.perf_counter()
        self._listed = self._checked = 0
        try:
            problems = self._pass()
        except Exception as error:
            self._note("nas" if isinstance(error, RootUnavailable) else "pass", str(error))
            self._beat(str(error) or type(error).__name__)
            self._measure(began, 1)
            raise
        text = f"{len(problems)} not read, first: {problems[0]}" if problems else None
        self._note("pass", text)
        self._beat(text)
        self._measure(began, len(problems))
        self._housekeeping()

    def _note(self, what: str, trouble: str | None) -> None:
        """Record trouble and the end of it once each, also across restarts."""
        if what == "nas":
            if events.last_kind(self._db, "nas_down", "nas_up") != "nas_down":
                self._event("nas_down", detail=trouble)
            return
        if events.last_kind(self._db, "nas_down", "nas_up") == "nas_down":
            self._event("nas_up")
        last = events.last_kind(self._db, "pass_error", "pass_ok")
        if trouble and last != "pass_error":
            self._event("pass_error", detail=trouble)
        elif not trouble and last == "pass_error":
            self._event("pass_ok")
        if not self._announced:
            self._announced = True
            self._event("started")

    def _measure(self, began: float, problems: int) -> None:
        m = self.metrics
        m.set("gphoto.pass.duration", time.perf_counter() - began, "s", "Time of the last pass")
        m.set("gphoto.pass.folders_listed", self._listed, "{folder}", "Folders listed in it")
        m.set("gphoto.pass.photos_checked", self._checked, "{photo}", "Photos asked about in it")
        m.set("gphoto.pass.folders_known", len(self._folders), "{folder}", "Folders remembered")
        m.set("gphoto.pass.problems", problems, "{folder}", "Places it could not read")
        waiting = self._db.execute("SELECT COUNT(*) FROM incoming WHERE status = 'waiting'")
        m.set("gphoto.waiting", waiting.fetchone()[0], "{photo}", "Photos waiting")
        m.disk("state", self._state)
        m.disk("staging", self.staging)
        m.save()

    def _housekeeping(self) -> None:
        if self.dry_run:
            return
        try:
            events.prune(self._db, self.clock())
            self._db.commit()
            day = datetime.fromtimestamp(self.clock()).strftime("%Y%m%d")
            ops.backup(self._db, self._state / "backup", "state", day)
        except (OSError, sqlite3.Error):
            logger.exception("Backup failed")

    def _beat(self, error: str | None) -> None:
        self._beat_at = self.clock()
        self._db.execute(
            "INSERT OR REPLACE INTO heartbeat VALUES (1, ?, ?)", (self._beat_at, error)
        )
        self._db.commit()

    def _still_alive(self) -> None:
        """Move the heartbeat during a long pass. Keeps the last error, if any."""
        if self.clock() - self._beat_at >= BEAT_EVERY:
            self._beat_at = self.clock()
            self._db.execute(
                "INSERT INTO heartbeat VALUES (1, ?, NULL)"
                " ON CONFLICT (id) DO UPDATE SET at = excluded.at",
                (self._beat_at,),
            )
            self._db.commit()

    def _pass(self) -> list[str]:
        """Walk the share. Returns what could not be read.

        NFS does not report changes made by other machines, so this polls. A folder's
        mtime moves when a file is added, removed or renamed in it, so a folder whose
        mtime stands still is not listed, which keeps a pass to one stat per folder.
        """
        if not self._mounted():
            raise RootUnavailable(f"{self.root} is missing or has no year folders")
        for leftover in self._work.iterdir():
            leftover.unlink()  # from a pass that was killed
        now = self.clock()
        full = now - self._full_at >= FULL_PASS_EVERY
        busy = {
            row["path"].rpartition("/")[0]
            for row in self._db.execute("SELECT path FROM incoming WHERE status = 'waiting'")
        }
        problems: list[str] = []
        seen: set[str] = set()
        todo = [""]
        while todo:
            relative = todo.pop()
            self._still_alive()
            try:
                subfolders = self._visit(relative, full or relative in busy, problems)
            except FileNotFoundError:
                continue  # went between being listed and being visited
            except OSError as error:
                problems.append(f"{relative or self.root}: {error}")
                self._folders.pop(relative, None)
                continue
            seen.add(relative)
            todo.extend(f"{relative}/{name}" if relative else name for name in subfolders)
        if not problems:
            self._forget_gone(seen)
            if full:
                self._full_at = now
        return problems

    def _mounted(self) -> bool:
        """An unmounted share is an empty folder, or one with a stray file in it."""
        try:
            with os.scandir(self.root) as entries:
                return any(
                    len(e.name) == 4 and e.name.isdigit() and e.is_dir() for e in entries
                )
        except OSError:
            return False

    def _visit(self, relative: str, always: bool, problems: list[str]) -> list[str]:
        folder = self.root / relative
        # Read before listing, so a change made while listing is seen next time.
        mtime_ns = folder.stat().st_mtime_ns
        known = self._folders.get(relative)
        if known and not always and known.mtime_ns == mtime_ns:
            return known.subfolders
        names, subfolders = self._list(folder)
        self._listed += 1
        self._checked += len(names)
        if not relative:
            subfolders = [n for n in subfolders if not self._is_old_year(n)]
        self._look_at(folder, relative, names, problems)
        if self.clock() - mtime_ns / 1e9 >= SETTLED_AFTER:
            self._folders[relative] = _Folder(mtime_ns, subfolders)
        else:
            # Too fresh to trust: the NFS cache can hide a second change in this moment.
            self._folders.pop(relative, None)
        return subfolders

    def _list(self, folder: Path) -> tuple[list[str], list[str]]:
        names, subfolders = [], []
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.name in IGNORED_DIRS:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    subfolders.append(entry.name)
                elif Path(entry.name).suffix.lower() in EXTENSIONS:
                    names.append(entry.name)
        return sorted(names), sorted(subfolders, reverse=True)

    def _is_old_year(self, name: str) -> bool:
        return len(name) == 4 and name.isdigit() and int(name) < self.since.year

    def _look_at(
        self, folder: Path, relative: str, names: list[str], problems: list[str]
    ) -> None:
        rows = self._rows_in(relative)
        present = set()
        for name in names:
            path = f"{relative}/{name}" if relative else name
            try:
                path.encode()
            except UnicodeEncodeError:
                problems.append(f"{relative}: a file name that is not valid text")
                continue
            present.add(path)
            self._still_alive()
            self._safely(folder / name, path, rows.get(path))
        self._db.commit()
        gone = [p for p, r in rows.items() if p not in present and r["status"] in FORGETTABLE]
        self._delete(gone)

    def _rows_in(self, relative: str) -> dict[str, sqlite3.Row]:
        """Rows for the files directly in one folder."""
        if not relative:
            found = self._db.execute("SELECT * FROM incoming WHERE path NOT LIKE '%/%'")
            return {r["path"]: r for r in found}
        # '0' is the character after '/', so this is every path below the folder.
        found = self._db.execute(
            "SELECT * FROM incoming WHERE path > ? AND path < ?", (f"{relative}/", f"{relative}0")
        )
        start = len(relative) + 1
        return {r["path"]: r for r in found if "/" not in r["path"][start:]}

    def _forget_gone(self, seen: set[str]) -> None:
        """Rows of folders that no longer exist. Only after a pass without errors."""
        marks = ",".join("?" * len(FORGETTABLE))
        found = self._db.execute(
            f"SELECT path FROM incoming WHERE status IN ({marks})", FORGETTABLE
        )
        self._delete([r["path"] for r in found if r["path"].rpartition("/")[0] not in seen])

    def _delete(self, paths: list[str]) -> None:
        if paths and not self.dry_run:
            for path in paths:
                row = self._row(path)
                if row and row["status"] in ("waiting", "failed", "look"):
                    self._event("gone", path)
            self._db.executemany("DELETE FROM incoming WHERE path = ?", [(p,) for p in paths])
            self._db.commit()

    def _row(self, relative: str) -> sqlite3.Row | None:
        return self._db.execute("SELECT * FROM incoming WHERE path = ?", (relative,)).fetchone()

    # --- one photo -----------------------------------------------------------------

    def _safely(self, path: Path, relative: str, row: sqlite3.Row | None) -> None:
        """One bad file must not stop the rest."""
        try:
            self._handle(path, relative, row)
        except Exception as error:
            self._db.rollback()
            if not path.exists():
                logger.info("Gone before it was handled: %s", relative)
                return
            passing = self._is_passing(path, error)
            logger.error("%s: %s", "Will retry" if passing else "Failed", relative, exc_info=error)
            if self.dry_run:
                return
            reason = str(error) or type(error).__name__
            try:
                if passing:
                    known = self._row(relative)
                    if known and known["reason"] != reason:
                        self._event("retrying", relative, reason)
                    self._db.execute(
                        "UPDATE incoming SET reason = ?, retry_at = ?"
                        " WHERE path = ? AND status = 'waiting'",
                        (reason, self.clock() + RETRY_AFTER, relative),
                    )
                    self._db.commit()
                else:
                    self._finish(path, relative, "failed", reason)
            except (OSError, sqlite3.OperationalError):
                logger.exception("Could not record the fault for %s", relative)

    def _is_passing(self, path: Path, error: Exception) -> bool:
        """A full disk, a stalled NAS or a busy database passes. A bad file does not."""
        if isinstance(error, OSError | subprocess.TimeoutExpired | sqlite3.OperationalError):
            return True
        try:
            _sha1(path)
        except OSError:
            return True  # exiftool only said it failed, but the NAS cannot read the file
        return False

    def _handle(self, path: Path, relative: str, row: sqlite3.Row | None) -> None:
        size, mtime_ns = _fingerprint(path)
        now = self.clock()
        if row is None:
            landed = self.landed_at(path)
            if landed < self._cutoff:
                return
            self._db.execute(
                "INSERT INTO incoming (path, size, mtime_ns, landed, status)"
                " VALUES (?, ?, ?, ?, 'waiting')",
                (relative, size, mtime_ns, landed),
            )
            self._event("landed", relative, at=landed)
            # Saved once per folder. A bulk copy would otherwise save once per file.
            retry_at = 0.0
        else:
            if row["status"] in ("sent", "duplicate") and row["taken"] is None:
                self._fill_in(path, relative, row)
                return
            if (row["size"], row["mtime_ns"]) != (size, mtime_ns):
                if not self._is_new_photo(path, relative, row, size, mtime_ns):
                    return
                self._db.execute(
                    "UPDATE incoming SET size = ?, mtime_ns = ?, landed = ?, status = 'waiting',"
                    " reason = NULL, retry_at = NULL, sha1 = NULL, taken = NULL, staged = NULL,"
                    " sent_at = NULL WHERE path = ?",
                    (size, mtime_ns, now, relative),
                )
                self._event("changed", relative)
                self._db.commit()
                return
            if row["status"] != "waiting":
                return
            landed, retry_at = row["landed"], row["retry_at"] or 0.0
        if now - landed >= self.wait_seconds and now >= retry_at:
            self._db.commit()
            self._process(path, relative)

    def _is_new_photo(
        self, path: Path, relative: str, row: sqlite3.Row, size: int, mtime_ns: int
    ) -> bool:
        """The file at this path changed. An edit of a sent photo is not sent again."""
        if row["status"] not in ("sent", "duplicate"):
            return row["status"] != "dismissed"
        taken = inspect(path).taken
        if taken is not None and taken.isoformat() != row["taken"]:
            return True
        self._db.execute(
            "UPDATE incoming SET size = ?, mtime_ns = ? WHERE path = ?", (size, mtime_ns, relative)
        )
        self._db.commit()
        return False

    def _fill_in(self, path: Path, relative: str, row: sqlite3.Row) -> None:
        """Rows written before these columns existed."""
        try:
            taken = inspect(path).taken
        except Exception:
            # It was sent. Not being able to read it now does not change that.
            logger.exception("Cannot read the capture time of %s", relative)
            taken = None
        self._db.execute(
            "UPDATE incoming SET taken = ?, staged = COALESCE(staged, ?),"
            " sent_at = COALESCE(sent_at, ?) WHERE path = ?",
            (taken.isoformat() if taken else "", path.name, row["landed"], relative),
        )
        self._db.commit()

    def _process(self, path: Path, relative: str) -> None:
        # A pass over many photos takes longer than the status page allows for.
        self._still_alive()
        info = inspect(path)
        decision = decide(info, self.since, self.cameras, self.rules)
        if self.dry_run:
            logger.info("Would %s %s (%s)", decision.action.value, relative, decision.reason)
            return
        if decision.action is Action.SKIP:
            logger.info("Skip %s (%s)", relative, decision.reason)
            status = "look" if info.made_by(self.cameras) else "skipped"
            self._finish(path, relative, status, decision.reason)
            return
        source = path
        began = time.perf_counter()
        try:
            if decision.action is Action.STRIP and self.in_place:
                done = strip_in_place(path, self.rules)
            elif decision.action is Action.STRIP:
                source = self._work / path.name
                done = scrub_to(path, source, self.rules)
            if decision.action is Action.STRIP:
                took = time.perf_counter() - began
                self.metrics.record("gphoto.scrub.duration", took, "s", "Time to clean a copy")
                # The event carries the time cleaning began, so that its length can be seen.
                self._event("scrubbed", relative, ", ".join(done), at=self.clock() - took)
            self._send(path, relative, source, info, decision.reason)
        finally:
            if source is not path:
                source.unlink(missing_ok=True)

    def _send(
        self, path: Path, relative: str, source: Path, info: PhotoInfo, reason: str
    ) -> None:
        sha1 = _sha1(source)
        twin = self._db.execute(
            "SELECT path FROM incoming WHERE sha1 = ? AND status = 'sent'", (sha1,)
        ).fetchone()
        if twin:
            self._finish(path, relative, "duplicate", f"same as {twin['path']}", sha1)
            return
        staged = self._stage(source, sha1)
        self._db.execute(
            "UPDATE incoming SET taken = ?, staged = ?, sent_at = ? WHERE path = ?",
            (info.taken.isoformat() if info.taken else "", staged, self.clock(), relative),
        )
        self._finish(path, relative, "sent", reason, sha1)
        logger.info("Sent %s (%s)", relative, reason)

    def _stage(self, path: Path, sha1: str) -> str:
        target = self.staging / path.name
        if target.exists() and _sha1(target) != sha1:
            target = target.with_name(f"{path.stem}-{sha1[:8]}{path.suffix}")
        # The browser watches for photos, so the partial copy must not look like one.
        partial = target.with_name(f"{TEMP_PREFIX}{target.name}.part")
        try:
            shutil.copy2(path, partial)
            if _sha1(partial) != sha1:
                raise OSError(f"copy to staging does not match: {path}")
            # The browser runs as another user. NAS files can be owner-only.
            partial.chmod(0o644)
            with partial.open("rb+") as handle:
                os.fsync(handle.fileno())
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
        return target.name

    def _finish(
        self, path: Path, relative: str, status: str, reason: str, sha1: str | None = None
    ) -> None:
        size, mtime_ns = _fingerprint(path)
        self._db.execute(
            "UPDATE incoming SET size = ?, mtime_ns = ?, status = ?, reason = ?, sha1 = ?,"
            " retry_at = NULL WHERE path = ?",
            (size, mtime_ns, status, reason, sha1, relative),
        )
        kind = "skipped" if status == "duplicate" else status
        self._event(kind, relative, reason)
        self._db.commit()
        self.metrics.add("gphoto.photos", 1, "{photo}", "Photos handled", outcome=status)


def wait(runner: Runner, seconds: float) -> None:
    """Sleep until the next pass, or until something asked on the page has been done."""
    for _ in range(max(1, int(seconds / REQUEST_EVERY))):
        time.sleep(REQUEST_EVERY)
        if runner.take_requests():
            return


def _photos_access() -> str:
    """PHOTOS_ACCESS: ro sends a cleaned copy, rw cleans the NAS file too. Blank is ro."""
    access = os.getenv("PHOTOS_ACCESS", "").strip() or "ro"
    if access not in ("ro", "rw"):
        raise ValueError(f"PHOTOS_ACCESS must be ro or rw, not {access!r}")
    return access


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True, help="photo folder on the NAS")
    parser.add_argument("--staging", type=Path, required=True, help="folder the browser watches")
    parser.add_argument("--db", type=Path, required=True, help="state database")
    parser.add_argument("--since", type=date.fromisoformat, required=True, help="first capture day")
    parser.add_argument("--wait-hours", type=float, default=4.0)
    parser.add_argument("--interval", type=float, help="seconds between passes, default one pass")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--in-place", action="store_true", help="strip the NAS file too, needs write access"
    )
    parser.add_argument("--requests", type=Path, help="folder the status page writes to")
    parser.add_argument("--retry", metavar="PATH", help="send this photo again, then exit")
    parser.add_argument("--dismiss", metavar="PATH", help="stop flagging this photo, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
    )
    runner = Runner(
        root=args.root, staging=args.staging, db_path=args.db, since=args.since,
        wait_seconds=args.wait_hours * 3600, dry_run=args.dry_run, in_place=args.in_place,
        requests=args.requests,
    )
    try:
        settings = scrub.from_env()
        runner.in_place = args.in_place or _photos_access() == "rw"
        if runner.in_place and not os.access(args.root, os.W_OK):
            raise ValueError(
                f"PHOTOS_ACCESS is rw but {args.root} cannot be written."
                " Check the mount and the NAS permissions"
            )
    except ValueError as error:
        # Shown on the page, because a container that keeps stopping says nothing there.
        logger.error("%s", error)
        runner.refuse(str(error))
        return 1
    runner.rules, runner.cameras = settings.rules, settings.cameras
    if args.retry or args.dismiss:
        known = runner.retry(args.retry) if args.retry else runner.dismiss(args.dismiss)
        if not known:
            logger.error("No such photo: %s", args.retry or args.dismiss)
        return 0 if known else 1
    while True:
        try:
            runner.tick()
        except RootUnavailable:
            # Exit so that Docker restarts the container and binds the mount afresh.
            logger.exception("Photo folder unavailable, nothing done")
            return 1
        if not args.interval:
            return 0
        wait(runner, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
