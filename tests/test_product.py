"""State, arrival proof, status rules and access control."""

import hashlib
import os
import sqlite3
import time
from collections import Counter
from datetime import datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from gphoto import google, incoming, status, web
from tests.test_incoming import Box, make_jpeg

NOW = 1_795_600_000.0
MIN, HOUR, DAY = 60, 3600, 86400


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# --- what incoming records -------------------------------------------------


def row(box, name):
    db = sqlite3.connect(box.db)
    db.row_factory = sqlite3.Row
    return db.execute("SELECT * FROM incoming WHERE path LIKE ?", (f"%{name}",)).fetchone()


def test_sent_row_records_capture_time_staged_name_and_send_time(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    r = row(box, "DSC_1.JPG")
    assert r["taken"] == "2026-11-24T18:04:46"
    assert r["staged"] == "DSC_1.JPG"
    assert r["sent_at"] == box.clock.now


def test_waiting_row_records_capture_time_only_when_processed(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.runner().tick()
    assert row(box, "DSC_1.JPG")["status"] == "waiting"


def test_old_database_is_upgraded_and_sent_rows_get_their_capture_time(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    db = sqlite3.connect(box.db)
    db.execute(
        "CREATE TABLE incoming (path TEXT PRIMARY KEY, size INTEGER NOT NULL,"
        " mtime_ns INTEGER NOT NULL, landed REAL NOT NULL, status TEXT NOT NULL,"
        " reason TEXT, sha1 TEXT)"
    )
    stat = p.stat()
    db.execute(
        "INSERT INTO incoming VALUES (?, ?, ?, ?, 'sent', 'x', 'abc')",
        ("2026/20261124-dance/DSC_1.JPG", stat.st_size, stat.st_mtime_ns, NOW - DAY),
    )
    db.commit()
    db.close()
    box.runner().tick()
    r = row(box, "DSC_1.JPG")
    assert r["taken"] == "2026-11-24T18:04:46"
    assert r["staged"] == "DSC_1.JPG"
    assert r["status"] == "sent"


def test_unreadable_old_row_stays_sent(box, monkeypatch):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    db = sqlite3.connect(box.db)
    db.execute("UPDATE incoming SET taken = NULL")
    db.commit()
    db.close()

    def unreadable(path):
        raise RuntimeError("cannot read")

    monkeypatch.setattr(incoming, "inspect", unreadable)
    box.runner().tick()
    assert row(box, "DSC_1.JPG")["status"] == "sent"


def test_heartbeat_moves_during_a_long_pass(box, monkeypatch):
    make_jpeg(box.folder / "DSC_1.JPG")
    make_jpeg(box.folder / "DSC_2.JPG", seed=2)
    box.landed_long_ago("DSC_1.JPG", "DSC_2.JPG")
    beats = []
    real = incoming.scrub_to

    def slow(path, target, rules):
        db = sqlite3.connect(box.db)
        beats.append(db.execute("SELECT at FROM heartbeat").fetchone())
        db.close()
        box.clock.now += 20 * MIN
        return real(path, target, rules)

    monkeypatch.setattr(incoming, "scrub_to", slow)
    box.runner().tick()
    assert beats == [(NOW,), (NOW + 20 * MIN,)]


def test_heartbeat_records_a_good_pass(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    r.tick()
    beat = sqlite3.connect(box.db).execute("SELECT at, error FROM heartbeat").fetchone()
    assert beat == (box.clock.now, None)


def test_heartbeat_records_a_lost_mount(box):
    (box.root / "2026").rmdir()
    r = box.runner()
    with pytest.raises(incoming.RootUnavailable):
        r.tick()
    assert "no year folders" in sqlite3.connect(box.db).execute(
        "SELECT error FROM heartbeat"
    ).fetchone()[0]


# --- proof of arrival -------------------------------------------------------


@pytest.mark.parametrize(
    "label, expected",
    [
        ("Photo – Landscape – 24 Nov 2026, 18:04:46", datetime(2026, 11, 24, 18, 4, 46)),
        ("Photo – Portrait – 1 Sept 2026, 08:00:01", datetime(2026, 9, 1, 8, 0, 1)),
        ("Video – Landscape – 3 May 2025, 19:46:02", datetime(2025, 5, 3, 19, 46, 2)),
        ("Album – Holiday", None),
    ],
)
def test_read_google_label(label, expected):
    assert google.read_label(label) == expected


T1, T2 = datetime(2026, 11, 24, 17, 10, 32), datetime(2026, 11, 24, 17, 10, 36)


def test_photo_is_confirmed_when_google_shows_its_second():
    assert google.arrived([("a", T1), ("b", T2)], Counter({T1: 1})) == {"a"}


def test_burst_needs_every_frame():
    assert google.arrived([("a", T1), ("b", T1)], Counter({T1: 1})) == set()
    assert google.arrived([("a", T1), ("b", T1)], Counter({T1: 2})) == {"a", "b"}


class FakeChrome:
    def __init__(self, **kw):
        self.state = google.ChromeState(tab=True, signed_in=True, folder="granted")
        self.labels = {}
        self.searched, self.reloaded = [], 0
        for k, v in kw.items():
            setattr(self, k, v)

    async def check(self):
        if isinstance(self.state, Exception):
            raise self.state
        return self.state

    async def labels_on(self, day):
        self.searched.append(day)
        return self.labels.get(day, [])

    async def reload_photos(self):
        self.reloaded += 1


class Google:
    """A checker over a real incoming database with one sent photo."""

    def __init__(self, box):
        self.box = box
        self.photo = make_jpeg(box.folder / "DSC_1.JPG")
        box.landed_long_ago("DSC_1.JPG")
        box.runner().tick()
        self.staged = box.staging / "DSC_1.JPG"
        self.chrome = FakeChrome()
        self.day = datetime(2026, 11, 24).date()
        self.there = ["Photo – Landscape – 24 Nov 2026, 18:04:46"]

    def checker(self):
        return google.Checker(
            chrome=self.chrome, incoming_db=self.box.db, db_path=self.box.db.parent / "google.db",
            staging=self.box.staging, clock=self.box.clock,
        )

    def confirmed(self):
        db = sqlite3.connect(self.box.db.parent / "google.db")
        return [r[0] for r in db.execute("SELECT path FROM confirmed")]

    def health(self):
        db = sqlite3.connect(self.box.db.parent / "google.db")
        db.row_factory = sqlite3.Row
        return dict(db.execute("SELECT * FROM health").fetchone())


@pytest.fixture
def g(box):
    return Google(box)


def run(coro):
    import asyncio

    return asyncio.run(coro)


def test_checker_confirms_a_photo_google_shows(g):
    g.chrome.labels[g.day] = g.there
    run(g.checker().tick())
    assert len(g.confirmed()) == 1


def test_checker_does_not_confirm_a_missing_photo(g):
    run(g.checker().tick())
    assert g.confirmed() == []


def test_checker_searches_at_most_every_ten_minutes(g):
    c = g.checker()
    run(c.tick())
    g.box.clock.now += 5 * MIN
    run(c.tick())
    assert len(g.chrome.searched) == 1
    g.box.clock.now += 6 * MIN
    run(c.tick())
    assert len(g.chrome.searched) == 2


def test_checker_stops_searching_once_confirmed(g):
    g.chrome.labels[g.day] = g.there
    c = g.checker()
    run(c.tick())
    g.box.clock.now += HOUR
    run(c.tick())
    assert len(g.chrome.searched) == 1


def test_staging_is_tidied_a_month_after_proof(g):
    g.chrome.labels[g.day] = g.there
    c = g.checker()
    run(c.tick())
    assert g.staged.exists()
    g.box.clock.now += 30 * DAY + 1
    run(c.tick())
    assert not g.staged.exists()


def test_unproven_photo_is_never_tidied(g):
    c = g.checker()
    run(c.tick())
    g.box.clock.now += 30 * DAY
    run(c.tick())
    assert g.staged.exists()


def test_a_different_file_with_the_same_name_is_never_tidied(g):
    g.chrome.labels[g.day] = g.there
    c = g.checker()
    run(c.tick())
    g.staged.write_bytes(b"someone else's file")
    g.box.clock.now += 30 * DAY + 1
    run(c.tick())
    assert g.staged.exists()


def test_tidy_never_touches_the_nas(g):
    g.chrome.labels[g.day] = g.there
    before = hashlib.sha1(g.photo.read_bytes()).hexdigest()
    c = g.checker()
    run(c.tick())
    g.box.clock.now += 30 * DAY + 1
    run(c.tick())
    assert hashlib.sha1(g.photo.read_bytes()).hexdigest() == before


def test_closed_tab_is_reopened_at_once(g):
    g.chrome.state = google.ChromeState(tab=False, signed_in=False, folder=None)
    run(g.checker().tick())
    assert g.chrome.reloaded == 1


def test_signed_out_is_recorded_and_not_searched(g):
    g.chrome.state = google.ChromeState(tab=True, signed_in=False, folder=None)
    run(g.checker().tick())
    assert g.health()["signed_in"] == 0
    assert g.chrome.searched == []


def test_unreachable_chrome_is_recorded(g):
    g.chrome.state = ConnectionRefusedError("no chrome")
    run(g.checker().tick())
    assert "no chrome" in g.health()["error"]


def test_photo_stuck_for_half_an_hour_reloads_the_page(g):
    c = g.checker()
    run(c.tick())
    assert g.chrome.reloaded == 0
    g.box.clock.now += 31 * MIN
    run(c.tick())
    run(c.tick())
    assert g.chrome.reloaded == 1


# --- status rules -----------------------------------------------------------


class State:
    """Databases as the status page finds them."""

    def __init__(self, tmp_path):
        self.dir = tmp_path
        box = tmp_path / "b"
        box.mkdir(exist_ok=True)
        incoming.Runner(
            root=box, staging=box, db_path=tmp_path / "incoming.db",
            since=datetime(2026, 11, 24).date(), wait_seconds=4 * HOUR,
        )
        google.Checker(
            chrome=None, incoming_db=tmp_path / "incoming.db", db_path=tmp_path / "google.db",
            staging=box,
        )
        self.beat()
        self.health()

    def _do(self, db, sql, *args):
        c = sqlite3.connect(self.dir / db)
        c.execute(sql, args)
        c.commit()
        c.close()

    def beat(self, at=NOW - 60, error=None):
        self._do("incoming.db", "INSERT OR REPLACE INTO heartbeat VALUES (1, ?, ?)", at, error)

    def health(self, at=NOW - 60, signed_in=1, folder="granted", error=None, search_error=None):
        self._do(
            "google.db", "INSERT OR REPLACE INTO health VALUES (1, ?, ?, ?, ?, ?)",
            at, signed_in, folder, error, search_error,
        )

    def photo(self, name, state="sent", landed=NOW - 5 * HOUR, sent_at=None, confirmed=None):
        path = f"2026/folder/{name}"
        self._do(
            "incoming.db",
            "INSERT INTO incoming (path, size, mtime_ns, landed, status, reason, sha1, taken,"
            " staged, sent_at) VALUES (?, 1, 1, ?, ?, 'why', 'x', '2026-11-24T18:04:46', ?, ?)",
            path, landed, state, name, sent_at if state != "sent" else sent_at or landed,
        )
        if confirmed:
            self._do("google.db", "INSERT INTO confirmed VALUES (?, ?)", path, confirmed)

    def event(self, db, at, kind, path=None, detail=None):
        self._do(
            db, "INSERT INTO events (at, kind, path, detail) VALUES (?, ?, ?, ?)",
            at, kind, path, detail,
        )

    def read(self):
        return status.read(self.dir, now=NOW, wait_seconds=4 * HOUR)


@pytest.fixture
def state(tmp_path):
    return State(tmp_path)


def test_all_good(state):
    state.photo("a.JPG", sent_at=NOW - HOUR, confirmed=NOW - HOUR)
    s = state.read()
    assert s.ok
    assert s.problems == []
    assert s.counts == {
        "waiting": 0, "on the way": 0, "in Google": 1, "skipped": 0,
        "needs a look": 0, "failed": 0,
    }


def test_counts_each_stage(state):
    state.photo("w.JPG", "waiting", landed=NOW - HOUR)
    state.photo("s.JPG", sent_at=NOW - MIN)
    state.photo("d.JPG", "duplicate")
    state.photo("k.JPG", "skipped")
    state.photo("f.JPG", "failed")
    assert state.read().counts == {
        "waiting": 1, "on the way": 1, "in Google": 0, "skipped": 2, "needs a look": 0,
        "failed": 1,
    }


def test_waiting_photo_shows_when_it_will_go(state):
    state.photo("w.JPG", "waiting", landed=NOW - HOUR)
    (photo,) = state.read().photos
    assert photo.due == NOW + 3 * HOUR


@pytest.mark.parametrize(
    "break_it, words",
    [
        (lambda s: s.beat(at=NOW - 16 * MIN), "has not run"),
        (lambda s: s.beat(error="gone"), "NAS"),
        (lambda s: s.health(at=NOW - 11 * MIN), "not been checked"),
        (lambda s: s.health(error="refused"), "Chrome"),
        (lambda s: s.health(signed_in=0), "signed out"),
        (lambda s: s.health(folder="prompt"), "permission"),
        (lambda s: s.health(folder=None), "permission"),
        (lambda s: s.photo("f.JPG", "failed"), "1 photo failed"),
        (lambda s: s.photo("s.JPG", sent_at=NOW - 3 * HOUR), "1 photo has not arrived"),
    ],
)
def test_each_fault_is_shown(state, break_it, words):
    break_it(state)
    s = state.read()
    assert not s.ok
    assert len(s.problems) == 1
    assert words in s.problems[0].title


def test_photos_that_need_attention_come_first_and_skipped_last(state):
    state.photo("k.JPG", "skipped", landed=NOW - 1)
    state.photo("g.JPG", sent_at=NOW - DAY, confirmed=NOW - DAY)
    state.photo("s.JPG", sent_at=NOW - MIN)
    state.photo("w.JPG", "waiting", landed=NOW - HOUR)
    state.photo("f.JPG", "failed", landed=NOW - DAY)
    assert [p.name for p in state.read().photos] == [
        "f.JPG", "w.JPG", "s.JPG", "g.JPG", "k.JPG",
    ]


def test_every_problem_says_what_to_do(state):
    state.health(signed_in=0)
    assert state.read().problems[0].fix


def test_missing_databases_are_a_problem_not_a_crash(tmp_path):
    s = status.read(tmp_path, now=NOW, wait_seconds=4 * HOUR)
    assert not s.ok


# --- only Terry -------------------------------------------------------------

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEAM, AUD, ME = "https://team.example", "aud-1", "me@example.com"


def token(key=KEY, **over):
    claims = {
        "email": ME, "aud": [AUD], "iss": TEAM, "iat": time.time(), "exp": time.time() + 60,
    }
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def client(state):
    access = web.Access(team=TEAM, audience=AUD, email=ME, key_for=lambda t: KEY.public_key())
    app = web.create_app(
        state.dir, access, clock=lambda: NOW, wait_seconds=4 * HOUR, chrome_url="https://lan",
        requests=state.dir / "requests",
    )
    return TestClient(app)


def get(client, path="/", **kw):
    return client.get(path, headers={"Cf-Access-Jwt-Assertion": token(**kw)})


def test_terry_gets_the_page(client):
    r = get(client)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_email_case_does_not_matter(client):
    assert get(client, email="ME@Example.com").status_code == 200


@pytest.mark.parametrize("path", ["/", "/api/status", "/docs", "/openapi.json", "/nothing"])
def test_no_token_is_refused_everywhere(client, path):
    assert client.get(path).status_code == 403


@pytest.mark.parametrize(
    "bad",
    [
        {"email": "other@example.com"},
        {"email": None},
        {"aud": ["other"]},
        {"iss": "https://evil.example"},
        {"exp": time.time() - 60},
        {"key": OTHER_KEY},
    ],
    ids=["other-person", "no-email", "other-app", "other-issuer", "expired", "forged"],
)
def test_bad_token_is_refused(client, bad):
    assert get(client, **bad).status_code == 403


def test_unsigned_token_is_refused(client):
    t = jwt.encode({"email": ME, "aud": [AUD], "iss": TEAM}, None, algorithm="none")
    assert client.get("/", headers={"Cf-Access-Jwt-Assertion": t}).status_code == 403


def test_health_check_is_open_and_says_nothing(client):
    r = client.get("/healthz")
    assert (r.status_code, r.text) == (200, "ok")


@pytest.mark.parametrize("missing", ["CF_ACCESS_TEAM", "CF_ACCESS_AUD", "ALLOWED_EMAIL"])
def test_refuses_to_start_without_access_settings(monkeypatch, tmp_path, missing):
    for k in ("CF_ACCESS_TEAM", "CF_ACCESS_AUD", "ALLOWED_EMAIL"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        web.from_env()


def test_page_shows_problem_and_fix(client, state):
    state.health(signed_in=0)
    html = get(client).text
    assert "signed out" in html
    assert "https://lan" in html


def test_page_escapes_file_names(client, state):
    state.photo("<script>x</script>.JPG", sent_at=NOW)
    html = get(client).text
    assert "<script>x" not in html
    assert "&lt;script&gt;x" in html


def test_page_tells_browsers_not_to_store_it(client):
    assert get(client).headers["cache-control"] == "no-store"


def test_api_gives_the_same_state(client, state):
    state.photo("a.JPG", sent_at=NOW - HOUR, confirmed=NOW)
    body = get(client, "/api/status").json()
    assert body["ok"] is True
    assert body["counts"]["in Google"] == 1


def test_web_process_only_reads(state, client):
    before = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in state.dir.glob("*.db")}
    get(client)
    after = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in state.dir.glob("*.db")}
    assert before == after
    assert not [p for p in os.listdir(state.dir) if p.endswith(("-wal", "-journal"))]
