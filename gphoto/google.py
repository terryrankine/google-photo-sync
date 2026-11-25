"""Watch the Google Photos browser: is it healthy, and did each photo arrive?

Talks to Chrome's control port through a socket file. Arrival is proved by finding
the photo's capture second in a Google Photos search, because Google's page shows a
time per photo and nothing else to match on.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.client
import json
import logging
import os
import re
import socket
import sqlite3
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

logger = logging.getLogger(__name__)

PHOTOS_URL = "https://photos.google.com/"
SEARCH_EVERY = 10 * 60
SEARCH_MOST = 6 * 3600
DAYS_PER_TICK = 3
RELOAD_EVERY = 30 * 60
RELOAD_MOST = 24 * 3600
TIDY_AFTER = 30 * 24 * 3600
SETTLE_SLACK = 24 * 3600
CALL_TIMEOUT = 120
MONTHS = {
    m: i
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}
LABEL = re.compile(r"(\d{1,2}) ([A-Za-z]{3})[a-z]* (\d{4}), (\d{2}):(\d{2}):(\d{2})")


@dataclass(frozen=True)
class ChromeState:
    tab: bool
    signed_in: bool
    folder: str | None  # 'granted', 'prompt', 'denied', or None when no folder is set up


class Chrome(Protocol):
    async def check(self) -> ChromeState: ...
    async def labels_on(self, day: date) -> list[str]: ...
    async def reload_photos(self) -> None: ...


def read_label(label: str) -> datetime | None:
    """'Photo – Landscape – 24 Nov 2026, 18:04:46' to a datetime."""
    match = LABEL.search(label)
    if not match:
        return None
    day, month, year, hour, minute, second = match.groups()
    number = MONTHS.get(month.lower())
    if number is None:
        return None
    return datetime(int(year), number, int(day), int(hour), int(minute), int(second))


def arrived(sent: Iterable[tuple[str, datetime]], seen: Counter[datetime]) -> set[str]:
    """Photos Google shows. A burst counts only when Google shows every frame of it.

    A phone photo taken in the same second as a camera photo can stand in for it. The
    camera photo stays on the NAS either way.
    """
    by_second: dict[datetime, list[str]] = defaultdict(list)
    for path, taken in sent:
        by_second[taken].append(path)
    return {
        path
        for taken, paths in by_second.items()
        if seen[taken] >= len(paths)
        for path in paths
    }


def _sha1(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha1").hexdigest()


@dataclass
class _Search:
    """When to look for a day again. Backs off while nothing changes."""

    next_at: float = 0.0
    delay: float = SEARCH_EVERY
    outstanding: int = 0


class Checker:
    """One check per tick. Writes its own database and reads the incoming one."""

    def __init__(
        self,
        chrome: Chrome,
        incoming_db: Path,
        db_path: Path,
        staging: Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.chrome = chrome
        self.incoming_db = incoming_db
        self.staging = staging
        self.clock = clock
        self._searches: dict[date, _Search] = {}
        self._reload_delay = RELOAD_EVERY
        self._reloaded = clock()
        self._db = sqlite3.connect(f"{db_path.absolute().as_uri()}", uri=True, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS health (id INTEGER PRIMARY KEY CHECK (id = 1),"
            " checked_at REAL NOT NULL, signed_in INTEGER NOT NULL, folder TEXT, error TEXT)"
        )
        if "search_error" not in {r["name"] for r in self._db.execute("PRAGMA table_info(health)")}:
            self._db.execute("ALTER TABLE health ADD COLUMN search_error TEXT")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS confirmed (path TEXT PRIMARY KEY, at REAL NOT NULL)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS tidied (path TEXT PRIMARY KEY, at REAL NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS confirmed_at ON confirmed (at)")
        # Every photo sent before 'settled' is proved, and every proof before 'tidied' is
        # tidied, so neither has to be looked at again.
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS done (id INTEGER PRIMARY KEY CHECK (id = 1),"
            " settled REAL NOT NULL, tidied REAL NOT NULL)"
        )
        self._db.execute("INSERT OR IGNORE INTO done VALUES (1, 0, 0)")
        self._db.commit()

    async def tick(self) -> None:
        try:
            state = await self.chrome.check()
        except Exception as error:
            logger.exception("Check failed")
            self._health(False, None, str(error) or type(error).__name__)
            return
        self._health(state.signed_in, state.folder, None)
        try:
            if not state.tab:
                logger.warning("No page open, opening Google Photos")
                await self._reload()
            elif not state.signed_in:
                await self._reload_if_due(RELOAD_EVERY)
            elif self._attach():
                try:
                    await self._confirm()
                    self._settle()
                    await self._refresh()
                    if state.folder == "granted":
                        self._tidy()
                finally:
                    self._db.execute("DETACH inc")
        except Exception:
            # The browser answered, so this is not a browser fault. Next tick tries again.
            logger.exception("Work after the check failed")

    def _health(self, signed_in: bool, folder: str | None, error: str | None) -> None:
        self._db.execute(
            "INSERT INTO health (id, checked_at, signed_in, folder, error) VALUES (1, ?, ?, ?, ?)"
            " ON CONFLICT (id) DO UPDATE SET checked_at = excluded.checked_at,"
            " signed_in = excluded.signed_in, folder = excluded.folder, error = excluded.error",
            (self.clock(), int(signed_in), folder, error),
        )
        self._db.commit()

    def _search_health(self, error: str | None) -> None:
        """A search can take a while, so it also proves this is alive."""
        self._db.execute(
            "UPDATE health SET search_error = ?, checked_at = ? WHERE id = 1", (error, self.clock())
        )
        self._db.commit()

    def _attach(self) -> bool:
        try:
            self._db.execute(
                "ATTACH ? AS inc", (f"{self.incoming_db.absolute().as_uri()}?mode=ro",)
            )
            return True
        except sqlite3.OperationalError:
            logger.info("No incoming database yet")
            return False

    # Proof made before a photo was sent belongs to an earlier photo at the same path.
    _OUTSTANDING = (
        " FROM inc.incoming i LEFT JOIN confirmed c"
        " ON c.path = i.path AND c.at >= i.sent_at"
        " WHERE i.status = 'sent' AND i.sent_at >= (SELECT settled FROM done)"
        " AND i.taken <> '' AND c.path IS NULL"
    )

    def _settle(self) -> None:
        oldest = self._db.execute(f"SELECT MIN(i.sent_at) {self._OUTSTANDING}").fetchone()[0]
        if oldest is None:
            oldest = self._db.execute(
                "SELECT MAX(sent_at) FROM inc.incoming WHERE status = 'sent'"
            ).fetchone()[0]
        if oldest is not None:
            # A day of slack, in case the clock is set back.
            self._db.execute("UPDATE done SET settled = MAX(settled, ?)", (oldest - SETTLE_SLACK,))
            self._db.commit()

    def _outstanding(self) -> dict[date, set[str]]:
        days: dict[date, set[str]] = defaultdict(set)
        for row in self._db.execute(f"SELECT i.path, i.taken {self._OUTSTANDING}"):
            days[datetime.fromisoformat(row["taken"]).date()].add(row["path"])
        return days

    def _due(self, days: dict[date, set[str]]) -> list[date]:
        now = self.clock()
        self._searches = {d: s for d, s in self._searches.items() if d in days}
        due = []
        for day, paths in days.items():
            search = self._searches.setdefault(day, _Search())
            if len(paths) > search.outstanding:  # something new was sent
                search.next_at, search.delay = min(search.next_at, now), SEARCH_EVERY
            search.outstanding = len(paths)
            if now >= search.next_at:
                due.append(day)
        due.sort(key=lambda d: (self._searches[d].next_at, -d.toordinal()))
        return due[:DAYS_PER_TICK]

    async def _confirm(self) -> None:
        days = self._outstanding()
        for day in self._due(days):
            search = self._searches[day]
            search.next_at = self.clock() + search.delay
            search.delay = min(search.delay * 2, SEARCH_MOST)
            try:
                labels = await self.chrome.labels_on(day)
                seen = Counter(t for t in map(read_label, labels) if t)
                if labels and not seen:
                    raise RuntimeError(f"cannot read Google's dates, for example {labels[0]!r}")
            except Exception as error:
                logger.exception("Search for %s failed", day)
                self._search_health(str(error) or type(error).__name__)
                continue
            # The whole day is matched, so frames of a burst confirmed earlier still count.
            sent = [
                (row["path"], datetime.fromisoformat(row["taken"]))
                for row in self._db.execute(
                    "SELECT path, taken FROM inc.incoming WHERE status = 'sent'"
                    " AND taken >= ? AND taken < ?",
                    (day.isoformat(), (day + timedelta(days=1)).isoformat()),
                )
            ]
            found = arrived(sent, seen) & days[day]
            self._db.executemany(
                "INSERT OR REPLACE INTO confirmed VALUES (?, ?)",
                [(path, self.clock()) for path in sorted(found)],
            )
            self._search_health(None)
            logger.info("%s: Google shows %d, confirmed %d", day, sum(seen.values()), len(found))

    async def _reload(self) -> None:
        self._reloaded = self.clock()
        await self.chrome.reload_photos()

    async def _reload_if_due(self, every: float) -> bool:
        if self.clock() - self._reloaded < every:
            return False
        logger.warning("Reloading Google Photos")
        await self._reload()
        return True

    async def _refresh(self) -> None:
        """The page sometimes stops noticing new files, and can look signed in when it is not."""
        oldest = self._db.execute(f"SELECT MIN(i.sent_at) {self._OUTSTANDING}").fetchone()[0]
        if oldest is None:
            self._reload_delay = RELOAD_EVERY
            await self._reload_if_due(RELOAD_MOST)
        elif self.clock() - oldest >= RELOAD_EVERY and await self._reload_if_due(
            self._reload_delay
        ):
            # A reload can interrupt an upload, so it backs off.
            self._reload_delay = min(self._reload_delay * 2, RELOAD_MOST)

    def _tidy(self) -> None:
        """Remove old staged copies. The NAS is not involved.

        Proof of arrival is a matching second, so it is only trusted for this after a
        month in which nothing is missing.
        """
        if self._db.execute(f"SELECT 1 {self._OUTSTANDING} LIMIT 1").fetchone():
            return
        now = self.clock()
        old = self._db.execute(
            "SELECT i.path, i.staged, i.sha1, c.at FROM confirmed c CROSS JOIN inc.incoming i"
            " LEFT JOIN tidied t ON t.path = c.path AND t.at >= c.at"
            " WHERE c.at >= (SELECT tidied FROM done) AND c.at <= ? AND i.path = c.path"
            " AND i.status = 'sent' AND c.at >= i.sent_at AND t.path IS NULL"
            " ORDER BY c.at LIMIT 500",
            (now - TIDY_AFTER,),
        ).fetchall()
        for row in old:
            staged = self.staging / row["staged"] if row["staged"] else None
            if staged and staged.is_file() and _sha1(staged) == row["sha1"]:
                staged.unlink()
                logger.info("Tidied %s", staged.name)
            self._db.execute("INSERT OR REPLACE INTO tidied VALUES (?, ?)", (row["path"], now))
        if old:
            self._db.execute("UPDATE done SET tidied = ?", (old[-1]["at"],))
        self._db.commit()


class _Session:
    """One DevTools websocket."""

    def __init__(self, link) -> None:
        self._link = link
        self._next = 0

    async def call(self, method: str, **params) -> dict:
        self._next += 1
        number = self._next
        await self._link.send(json.dumps({"id": number, "method": method, "params": params}))
        async with asyncio.timeout(CALL_TIMEOUT):
            while True:
                reply = json.loads(await self._link.recv())
                if reply.get("id") == number:
                    break
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error'].get('message')}")
        return reply["result"]

    async def run(self, script: str):
        result = await self.call(
            "Runtime.evaluate", expression=script, awaitPromise=True, returnByValue=True
        )
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            raise RuntimeError(detail.get("exception", {}).get("description", detail.get("text")))
        return result["result"].get("value")


SIGNED_IN = """!!document.querySelector('a[aria-label^="Google Account"]')"""

# Google Photos keeps the folder handle in IndexedDB. Asking the handle is the only
# way to learn the live permission without opening the menu.
FOLDER = """(async () => {
  for (const info of await indexedDB.databases()) {
    if (!info.name.includes('autobackup')) continue;
    const db = await new Promise((ok, no) => {
      const r = indexedDB.open(info.name); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error);
    });
    try {
      for (const store of db.objectStoreNames) {
        const rows = await new Promise((ok, no) => {
          const r = db.transaction(store).objectStore(store).getAll(undefined, 200);
          r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error);
        });
        const queue = rows.map(v => [v, 0]), seen = new Set();
        while (queue.length) {
          const [v, depth] = queue.shift();
          if (!v || typeof v !== 'object' || seen.has(v) || depth > 4) continue;
          seen.add(v);
          if (v instanceof FileSystemDirectoryHandle) return await v.queryPermission({mode: 'read'});
          for (const x of Object.values(v)) queue.push([x, depth + 1]);
        }
      }
    } finally { db.close(); }
  }
  return null;
})()"""

# The grid only keeps rows near the viewport, so it is scrolled and collected as it goes.
# A cold browser can take many seconds to show the first row, and loads more as it scrolls.
LABELS = """(async () => {
  const pause = ms => new Promise(r => setTimeout(r, ms));
  const links = () => document.querySelectorAll('a[aria-label][href*="/photo/"]');
  for (let i = 0; i < 60 && !links().length; i++) await pause(500);
  const found = new Map();
  let still = 0;
  for (let i = 0; i < 150 && still < 10; i++) {
    const grid = [...document.querySelectorAll('*')]
      .filter(e => e.scrollHeight > e.clientHeight + 300 && e.clientHeight > 400)
      .sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
    const before = found.size, top = grid ? grid.scrollTop : 0;
    links().forEach(a => found.set(a.getAttribute('href').split('/').pop(), a.getAttribute('aria-label')));
    if (grid) grid.scrollBy(0, 600);
    await pause(400);
    still = found.size === before && (!grid || grid.scrollTop === top) ? still + 1 : 0;
  }
  return [...found.values()];
})()"""


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, host: str) -> None:
        super().__init__(host, timeout=10)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


class ChromeDevTools:
    """The real browser, through its control port, handed over as a socket file."""

    # What Chrome believes it is being called. The socket file decides where it goes.
    HOST = "127.0.0.1:9222"

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path

    def _http(self, path: str, method: str = "GET") -> str:
        connection = _UnixConnection(self.socket_path, self.HOST)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            body = response.read().decode()
        finally:
            connection.close()
        if response.status != 200:
            raise RuntimeError(f"Chrome answered {response.status} to {path}: {body[:200]}")
        return body

    async def _get(self, path: str, method: str = "GET") -> str:
        return await asyncio.to_thread(self._http, path, method)

    async def _pages(self) -> list[dict]:
        """Open pages. A search left behind by a stopped checker is closed."""
        pages = []
        for tab in json.loads(await self._get("/json/list")):
            if tab["type"] != "page":
                continue
            if tab["url"].startswith(f"{PHOTOS_URL}search/"):
                await self._get(f"/json/close/{tab['id']}")
            else:
                pages.append(tab)
        return pages

    def _connect(self, tab: dict):
        import websockets

        path = tab["webSocketDebuggerUrl"].split("/devtools/", 1)[1]
        return websockets.unix_connect(
            self.socket_path, f"ws://{self.HOST}/devtools/{path}", max_size=2**24, open_timeout=10
        )

    async def check(self) -> ChromeState:
        pages = await self._pages()
        if not pages:
            return ChromeState(tab=False, signed_in=False, folder=None)
        photos = [t for t in pages if t["url"].startswith(PHOTOS_URL)]
        if not photos:
            # Signed out, Google sends the tab to a welcome, sign-in or consent page.
            return ChromeState(tab=True, signed_in=False, folder=None)
        async with self._connect(photos[0]) as link:
            session = _Session(link)
            signed_in = bool(await session.run(SIGNED_IN))
            folder = await session.run(FOLDER) if signed_in else None
        return ChromeState(tab=True, signed_in=signed_in, folder=folder)

    async def labels_on(self, day: date) -> list[str]:
        query = quote(f"{day.day} {day:%B} {day.year}")
        version = json.loads(await self._get("/json/version"))
        async with self._connect(version) as link:
            created = await _Session(link).call(
                "Target.createTarget", url=f"{PHOTOS_URL}search/{query}", background=True
            )
        target = created["targetId"]
        try:
            async with self._connect(
                {"webSocketDebuggerUrl": f"/devtools/page/{target}"}
            ) as link:
                session = _Session(link)
                # Without focus a background tab does not draw its grid.
                await session.call("Emulation.setFocusEmulationEnabled", enabled=True)
                await asyncio.sleep(3)  # the first document is blank
                return list(await session.run(LABELS))
        finally:
            await self._get(f"/json/close/{target}")

    async def reload_photos(self) -> None:
        """Bring one existing page to Google Photos. Never piles up tabs."""
        pages = await self._pages()
        if not pages:
            await self._get(f"/json/new?{quote(PHOTOS_URL, safe='')}", "PUT")
            return
        pages.sort(key=lambda t: not t["url"].startswith(PHOTOS_URL))
        async with self._connect(pages[0]) as link:
            await _Session(link).call("Page.navigate", url=PHOTOS_URL)


async def loop(checker: Checker, interval: float) -> None:
    while True:
        await checker.tick()
        await asyncio.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--socket", required=True, help="socket file of Chrome's control port")
    parser.add_argument("--state", type=Path, required=True, help="folder with the databases")
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=120)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
    )
    checker = Checker(
        chrome=ChromeDevTools(args.socket), incoming_db=args.state / "incoming.db",
        db_path=args.state / "google.db", staging=args.staging,
    )
    asyncio.run(loop(checker, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
