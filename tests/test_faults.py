"""Faults found in the architecture and SRE reviews. Each one used to pass silently."""

import errno
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta

import pytest

from gphoto import google, incoming, status
from tests.test_incoming import HOUR, Box, make_jpeg
from tests.test_product import DAY, MIN, NOW, FakeChrome, Google, State, run

REL = "2026/20261124-dance"


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


@pytest.fixture
def g(box):
    return Google(box)


@pytest.fixture
def state(tmp_path):
    return State(tmp_path)


def ready(box, *names, **kw):
    paths = [make_jpeg(box.folder / n, seed=i + 1, **kw) for i, n in enumerate(names)]
    box.landed_long_ago(*names)
    return paths


def beat_error(box):
    db = sqlite3.connect(box.db)
    try:
        return db.execute("SELECT error FROM heartbeat").fetchone()[0]
    finally:
        db.close()


def rows(box):
    db = sqlite3.connect(box.db)
    db.row_factory = sqlite3.Row
    try:
        return {r["path"].rsplit("/", 1)[1]: dict(r) for r in db.execute("SELECT * FROM incoming")}
    finally:
        db.close()


# --- reading the NAS ---------------------------------------------------------


def test_unreadable_folder_is_reported_and_the_rest_still_goes(box, monkeypatch):
    ready(box, "DSC_1.JPG")
    bad = box.root / "2026" / "locked"
    bad.mkdir()
    real = os.scandir

    def scandir(path):
        if os.fspath(path) == os.fspath(bad):
            raise PermissionError(errno.EACCES, "Permission denied")
        return real(path)

    monkeypatch.setattr(incoming.os, "scandir", scandir)
    box.runner().tick()
    assert box.sent() == ["DSC_1.JPG"]
    assert "locked" in beat_error(box)


def test_unmounted_share_with_a_stray_file_is_not_a_good_pass(box):
    (box.root / "2026").rmdir()
    (box.root / "lost+found").mkdir()
    (box.root / "note.txt").write_text("x")
    with pytest.raises(incoming.RootUnavailable):
        box.runner().tick()


def test_undecodable_name_does_not_stop_the_rest(box, monkeypatch):
    ready(box, "DSC_1.JPG")
    real = incoming.Runner._list

    def with_bad_name(self, folder):
        names, dirs = real(self, folder)
        return (["DSC_\udcff.JPG", *names] if names else names), dirs

    monkeypatch.setattr(incoming.Runner, "_list", with_bad_name)
    box.runner().tick()
    assert box.sent() == ["DSC_1.JPG"]
    assert "name" in beat_error(box)


def test_heartbeat_moves_during_a_long_scan(box, monkeypatch):
    for n in range(4):
        make_jpeg(box.root / "2026" / f"f{n}" / "DSC_1.JPG", seed=n)
    real, beats = incoming.Runner._list, []

    def slow(self, folder):
        box.clock.now += 20 * MIN
        result = real(self, folder)
        db = sqlite3.connect(box.db)
        found = db.execute("SELECT at FROM heartbeat").fetchone()
        db.close()
        beats.append(box.clock.now - found[0] if found else None)
        return result

    monkeypatch.setattr(incoming.Runner, "_list", slow)
    box.runner().tick()
    assert all(b is not None and b <= 20 * MIN for b in beats)


# --- not asking about every file on every pass --------------------------------


def quiet(box, folder):
    """A folder that has not changed for a while."""
    old = box.clock.now - HOUR
    os.utime(folder, (old, old))


def count_lists(monkeypatch):
    real, seen = incoming.Runner._list, []

    def spy(self, folder):
        seen.append(folder.name)
        return real(self, folder)

    monkeypatch.setattr(incoming.Runner, "_list", spy)
    return seen


def test_unchanged_folder_is_not_listed_again(box, monkeypatch):
    ready(box, "DSC_1.JPG")
    r = box.runner()
    for f in (box.folder, box.root / "2026", box.root):
        quiet(box, f)
    r.tick()
    for f in (box.folder, box.root / "2026", box.root):
        quiet(box, f)
    seen = count_lists(monkeypatch)
    box.clock.now += 5 * MIN
    r.tick()
    assert seen == []


def test_new_file_in_a_quiet_folder_is_found(box):
    ready(box, "DSC_1.JPG")
    quiet(box, box.folder)
    r = box.runner()
    r.tick()
    make_jpeg(box.folder / "DSC_2.JPG", seed=9)
    box.landed_long_ago("DSC_2.JPG")
    box.clock.now += 5 * MIN
    r.tick()
    assert box.sent() == ["DSC_1.JPG", "DSC_2.JPG"]


def test_new_subfolder_under_a_quiet_folder_is_found(box):
    ready(box, "DSC_1.JPG")
    r = box.runner()
    for f in (box.folder, box.root / "2026", box.root):
        quiet(box, f)
    r.tick()
    make_jpeg(box.folder / "more" / "DSC_2.JPG", seed=9)
    box.landed_long_ago("DSC_2.JPG")
    box.clock.now += 5 * MIN
    r.tick()
    assert "DSC_2.JPG" in box.sent()


def test_folder_with_a_waiting_photo_is_always_looked_at(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    r.tick()
    quiet(box, box.folder)
    box.clock.now += 4 * HOUR
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_everything_is_looked_at_once_a_day(box, monkeypatch):
    ready(box, "DSC_1.JPG")
    r = box.runner()
    r.tick()
    quiet(box, box.folder)
    seen = count_lists(monkeypatch)
    box.clock.now += DAY
    r.tick()
    assert box.folder.name in seen


# --- faults that pass ----------------------------------------------------------


@pytest.mark.parametrize(
    "fault",
    [
        OSError(errno.ENOSPC, "No space left on device"),
        subprocess.TimeoutExpired("exiftool", 120),
        sqlite3.OperationalError("database is locked"),
    ],
    ids=["disk-full", "nas-stall", "db-locked"],
)
def test_passing_fault_is_retried(box, monkeypatch, fault):
    ready(box, "DSC_1.JPG")
    r = box.runner()
    real = incoming.Runner._stage

    def broken(*a, **k):
        raise fault

    monkeypatch.setattr(incoming.Runner, "_stage", broken)
    r.tick()
    assert rows(box)["DSC_1.JPG"]["status"] == "waiting"
    assert rows(box)["DSC_1.JPG"]["reason"]
    monkeypatch.setattr(incoming.Runner, "_stage", real)
    box.clock.now += 16 * MIN
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_retry_waits_a_quarter_hour(box, monkeypatch):
    ready(box, "DSC_1.JPG")
    r, tries = box.runner(), []

    def broken(*a, **k):
        tries.append(1)
        raise OSError(errno.ENOSPC, "full")

    monkeypatch.setattr(incoming.Runner, "_stage", broken)
    r.tick()
    box.clock.now += 5 * MIN
    r.tick()
    assert len(tries) == 1


def test_exiftool_error_on_a_file_the_nas_cannot_read_is_retried(box, monkeypatch):
    ready(box, "DSC_1.JPG")

    def cannot(*a, **k):
        raise RuntimeError("exiftool failed: error reading")

    def eio(path):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(incoming, "inspect", cannot)
    monkeypatch.setattr(incoming, "_sha1", eio)
    box.runner().tick()
    assert rows(box)["DSC_1.JPG"]["status"] == "waiting"


# --- photos that change or go ---------------------------------------------------


@pytest.mark.parametrize("how", ["waiting", "failed"])
def test_deleted_photo_leaves_no_row(box, how):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    make_jpeg(box.folder / "DSC_2.JPG", seed=2)
    if how == "failed":
        p.write_bytes(b"not a jpeg")
        box.landed_long_ago("DSC_1.JPG")
    r = box.runner()
    r.tick()
    assert rows(box)["DSC_1.JPG"]["status"] == how
    p.unlink()
    box.clock.now += 5 * MIN
    r.tick()
    assert "DSC_1.JPG" not in rows(box)


def test_deleted_folder_leaves_no_rows(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    make_jpeg(box.root / "2026" / "keep" / "DSC_2.JPG", seed=2)
    r = box.runner()
    r.tick()
    shutil.rmtree(box.folder)
    box.clock.now += 5 * MIN
    r.tick()
    assert list(rows(box)) == ["DSC_2.JPG"]


def test_unreadable_folder_never_loses_its_rows(box, monkeypatch):
    make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    r.tick()

    def eio(path):
        raise OSError(errno.EIO, "Input/output error")

    real = os.scandir
    monkeypatch.setattr(
        incoming.os, "scandir",
        lambda p: eio(p) if os.fspath(p) == os.fspath(box.folder) else real(p),
    )
    box.clock.now += DAY
    r.tick()
    assert "DSC_1.JPG" in rows(box)


def test_sent_photo_deleted_from_the_nas_keeps_its_row(box):
    (p,) = ready(box, "DSC_1.JPG")
    r = box.runner()
    r.tick()
    p.unlink()
    box.clock.now += DAY
    r.tick()
    assert rows(box)["DSC_1.JPG"]["status"] == "sent"


def test_new_photo_at_a_used_path_is_sent(box):
    (p,) = ready(box, "DSC_1.JPG")
    r = box.runner()
    r.tick()
    make_jpeg(p, seed=7, taken="2026:12:25 09:00:00")
    box.clock.now += DAY
    r.tick()
    box.clock.now += 5 * HOUR
    r.tick()
    assert len(box.sent()) == 2
    assert rows(box)["DSC_1.JPG"]["taken"] == "2026-12-25T09:00:00"


def test_edit_of_a_sent_photo_is_still_not_sent_again(box):
    (p,) = ready(box, "DSC_1.JPG")
    r = box.runner()
    r.tick()
    make_jpeg(p, seed=8, second_image=None)
    for _ in range(3):
        box.clock.now += DAY
        r.tick()
    assert len(box.sent()) == 1


def test_old_proof_does_not_count_for_a_new_photo_at_the_same_path(g):
    g.chrome.labels[g.day] = g.there
    c = g.checker()
    run(c.tick())
    db = sqlite3.connect(g.box.db)
    db.execute("UPDATE incoming SET sent_at = ?, taken = '2026-12-25T09:00:00'", (NOW + HOUR,))
    db.commit()
    db.close()
    g.box.clock.now += 2 * HOUR
    run(c.tick())
    assert datetime(2026, 12, 25).date() in g.chrome.searched
    assert status.read(g.box.db.parent, now=g.box.clock.now, wait_seconds=4 * HOUR).counts[
        "in Google"
    ] == 0


# --- camera photos that were left out --------------------------------------------


@pytest.mark.parametrize("kw", [{"taken": "2013:01:01 00:00:00"}, {"second_image": 0}])
def test_camera_photo_left_out_is_flagged_not_hidden(box, kw):
    ready(box, "DSC_1.JPG", **kw)
    box.runner().tick()
    assert rows(box)["DSC_1.JPG"]["status"] == "look"


def test_phone_photo_is_not_flagged(box):
    ready(box, "IMG_1.jpg", make="Xiaomi", second_image=None)
    box.runner().tick()
    assert rows(box)["IMG_1.jpg"]["status"] == "skipped"


def test_dismiss_clears_a_flag_for_good(box):
    ready(box, "DSC_1.JPG", taken="2013:01:01 00:00:00")
    r = box.runner()
    r.tick()
    assert r.dismiss(f"{REL}/DSC_1.JPG")
    box.clock.now += DAY
    r.tick()
    assert rows(box)["DSC_1.JPG"]["status"] == "dismissed"


def test_retry_sends_a_photo_again(box):
    ready(box, "DSC_1.JPG")
    r = box.runner()
    r.tick()
    (box.staging / "DSC_1.JPG").unlink()
    assert r.retry(f"{REL}/DSC_1.JPG")
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_retry_of_an_unknown_path_says_so(box):
    ready(box, "DSC_1.JPG")
    assert not box.runner().retry("nope.JPG")


# --- the browser -------------------------------------------------------------------


def health(g):
    return g.health()


def test_page_that_is_not_healthy_is_reloaded_every_half_hour(g):
    g.chrome.state = google.ChromeState(tab=True, signed_in=False, folder=None)
    c = g.checker()
    for _ in range(8):
        run(c.tick())
        g.box.clock.now += 10 * MIN
    assert g.chrome.reloaded == 2


def test_healthy_page_is_refreshed_daily(g):
    g.chrome.labels[g.day] = g.there
    c = g.checker()
    run(c.tick())
    g.box.clock.now += DAY + 1
    run(c.tick())
    run(c.tick())
    assert g.chrome.reloaded == 1


def test_photo_that_never_arrives_does_not_hammer_google(g):
    c = g.checker()
    for _ in range(7 * 24 * 30):
        run(c.tick())
        g.box.clock.now += 2 * MIN
    assert g.chrome.reloaded <= 20
    assert len(g.chrome.searched) <= 60


def test_search_fault_is_its_own_message_and_stays_until_a_search_works(g):
    async def broken(day):
        raise RuntimeError("page changed")

    good = g.chrome.labels_on
    g.chrome.labels_on = broken
    c = g.checker()
    run(c.tick())
    g.box.clock.now += 2 * MIN
    run(c.tick())
    h = health(g)
    assert h["error"] is None
    assert "page changed" in h["search_error"]
    g.chrome.labels_on = good
    g.box.clock.now += HOUR
    run(c.tick())
    assert health(g)["search_error"] is None


def test_dates_that_cannot_be_read_are_reported(g):
    g.chrome.labels[g.day] = ["Photo - Landscape - Nov 24, 2026, 6:04:46 PM"]
    run(g.checker().tick())
    assert "dates" in health(g)["search_error"]


def test_few_days_per_check_so_the_page_never_looks_stale(g):
    db = sqlite3.connect(g.box.db)
    for n in range(20):
        day = datetime(2026, 12, 1) + timedelta(days=n)
        db.execute(
            "INSERT INTO incoming (path, size, mtime_ns, landed, status, taken, staged, sent_at)"
            " VALUES (?, 1, 1, 1, 'sent', ?, 'x', ?)", (f"p{n}", day.isoformat(), NOW),
        )
    db.commit()
    db.close()
    c = g.checker()
    run(c.tick())
    assert len(g.chrome.searched) <= 3
    for _ in range(8):
        run(c.tick())
    assert len(set(g.chrome.searched)) == 21


def test_missing_incoming_database_is_not_a_chrome_fault(tmp_path):
    c = google.Checker(
        chrome=FakeChrome(), incoming_db=tmp_path / "none.db", db_path=tmp_path / "google.db",
        staging=tmp_path, clock=lambda: NOW,
    )
    run(c.tick())
    db = sqlite3.connect(tmp_path / "google.db")
    assert db.execute("SELECT error FROM health").fetchone() == (None,)


def test_nothing_is_tidied_while_the_folder_is_not_allowed(g):
    g.chrome.labels[g.day] = g.there
    c = g.checker()
    run(c.tick())
    g.chrome.state = google.ChromeState(tab=True, signed_in=True, folder="prompt")
    g.box.clock.now += 60 * DAY
    run(c.tick())
    assert g.staged.exists()


def test_nothing_is_tidied_while_a_photo_is_missing(g):
    g.chrome.labels[g.day] = g.there
    c = g.checker()
    run(c.tick())
    make_jpeg(g.box.folder / "DSC_2.JPG", seed=5, taken="2026:11:25 10:00:00")
    g.box.landed_long_ago("DSC_2.JPG")
    g.box.runner().tick()
    g.box.clock.now += 60 * DAY
    run(c.tick())
    assert g.staged.exists()


# --- the page ------------------------------------------------------------------------


def test_overdue_photo_is_a_problem(state):
    state.photo("w.JPG", "waiting", landed=NOW - 6 * HOUR)
    s = state.read()
    assert [p.title for p in s.problems] == ["1 photo is overdue"]


def test_flagged_photo_is_a_problem(state):
    state.photo("l.JPG", "look")
    s = state.read()
    assert "needs a look" in s.problems[0].title
    assert s.counts["needs a look"] == 1


def test_unreadable_google_page_is_a_problem(state):
    state.health(search_error="cannot read the dates")
    assert "cannot read the dates" in state.read().problems[0].title


def test_clock_in_the_future_is_not_fresh(state):
    state.beat(at=NOW + DAY)
    assert not state.read().ok


def test_old_database_shape_is_a_problem_not_a_crash(tmp_path):
    db = sqlite3.connect(tmp_path / "incoming.db")
    db.execute("CREATE TABLE incoming (path TEXT, status TEXT)")
    db.execute("INSERT INTO incoming VALUES ('a', 'sent')")
    db.commit()
    db.close()
    assert not status.read(tmp_path, now=NOW, wait_seconds=1).ok


def test_page_lists_at_most_two_hundred_but_counts_all(state):
    for n in range(250):
        state.photo(f"{n}.JPG", sent_at=NOW)
    s = state.read()
    assert len(s.photos) == 200
    assert s.counts["on the way"] == 250


@pytest.mark.slow
def test_a_hundred_thousand_photos_stay_quick(state):
    import time

    for db, sql in (
        ("incoming.db",
         "INSERT INTO incoming (path,size,mtime_ns,landed,status,sha1,taken,staged,sent_at)"
         " WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM n WHERE i<100000)"
         " SELECT 'p'||i,1,1,1,'sent','s'||i,'2026-11-24T18:04:46','x',1 FROM n"),
        ("google.db",
         "INSERT INTO confirmed WITH RECURSIVE n(i) AS"
         " (SELECT 1 UNION ALL SELECT i+1 FROM n WHERE i<100000) SELECT 'p'||i, 2 FROM n"),
    ):
        state._do(db, sql)
    start = time.perf_counter()
    assert state.read().counts["in Google"] == 100000
    assert time.perf_counter() - start < 1.0
