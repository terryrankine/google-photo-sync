"""Events, metrics, requests from the page, backups, and what the pages show."""

import errno
import json
import os
import shutil
import sqlite3
from datetime import datetime

import pytest

from gphoto import charts, events, google, incoming, metrics, ops, scrub, status
from tests.test_faults import checker_on, rows
from tests.test_incoming import HOUR, Box, has_mpf, make_jpeg
from tests.test_product import DAY, MIN, NOW, Google, State, client, get, run, state  # noqa: F401

REL = "2026/20261124-dance"


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


@pytest.fixture
def g(box):
    return Google(box)


def kinds(path, **where):
    db = sqlite3.connect(path)
    try:
        found = db.execute("SELECT kind, path, detail, at FROM events ORDER BY id").fetchall()
    finally:
        db.close()
    if "about" in where:
        found = [f for f in found if f[1] and f[1].endswith(where["about"])]
    return [f[0] for f in found]


# --- metrics -----------------------------------------------------------------


def test_metrics_snapshot_has_the_agreed_shape(tmp_path):
    m = metrics.Metrics("incoming", tmp_path, clock=lambda: 50.0, version="abc")
    m.add("gphoto.photos", 2, "{photo}", "help", outcome="sent")
    m.add("gphoto.photos", 1, "{photo}", "help", outcome="sent")
    m.add("gphoto.photos", 5, "{photo}", "help", outcome="skipped")
    m.set("gphoto.pass.duration", 0.5, "s", "help")
    m.set("gphoto.pass.duration", 0.7, "s", "help")
    for v in (0.05, 0.4, 9):
        m.record("gphoto.scrub.duration", v, "s", "help", bounds=(0.1, 0.5, 1))
    m.save()
    saved = json.loads((tmp_path / "metrics-incoming.json").read_text())
    assert (saved["job"], saved["at"], saved["started"], saved["version"]) == ("incoming", 50, 50, "abc")
    photos = saved["metrics"]["gphoto.photos"]
    assert photos["type"] == "counter"
    assert {p["attributes"]["outcome"]: p["value"] for p in photos["points"]} == {
        "sent": 3, "skipped": 5,
    }
    assert saved["metrics"]["gphoto.pass.duration"]["points"] == [{"attributes": {}, "value": 0.7}]
    (h,) = saved["metrics"]["gphoto.scrub.duration"]["points"]
    assert (h["count"], h["buckets"], h["min"], h["max"]) == (3, [1, 1, 0, 1], 0.05, 9)


def test_metrics_that_cannot_be_saved_do_not_stop_the_work(tmp_path):
    m = metrics.Metrics("incoming", tmp_path / "gone")
    m.set("x", 1, "s", "h")
    m.save()


def test_metrics_file_is_never_half_written(tmp_path, monkeypatch):
    m = metrics.Metrics("incoming", tmp_path)
    m.set("x", 1, "s", "h")
    m.save()

    def full(*a):
        raise OSError(errno.ENOSPC, "full")

    monkeypatch.setattr(metrics.os, "replace", full)
    m.set("x", 2, "s", "h")
    m.save()
    assert json.loads((tmp_path / "metrics-incoming.json").read_text())["metrics"]["x"]["points"][0][
        "value"
    ] == 1
    assert [p.name for p in tmp_path.iterdir()] == ["metrics-incoming.json"]


def test_a_pass_leaves_metrics(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    saved = json.loads((box.db.parent / "metrics-incoming.json").read_text())["metrics"]
    assert saved["gphoto.photos"]["points"] == [{"attributes": {"outcome": "sent"}, "value": 1}]
    assert saved["gphoto.pass.folders_listed"]["points"][0]["value"] >= 2
    assert saved["gphoto.scrub.duration"]["points"][0]["count"] == 1
    assert "gphoto.disk.free" in saved


def test_a_check_leaves_metrics(g):
    g.chrome.labels[g.day] = g.there
    run(g.checker().tick())
    saved = json.loads((g.box.db.parent / "metrics-google.json").read_text())["metrics"]
    assert saved["gphoto.signed_in"]["points"][0]["value"] == 1
    assert saved["gphoto.staging.files"]["points"][0]["value"] == 1
    assert saved["gphoto.arrival.duration"]["points"][0]["count"] == 1


# --- events -------------------------------------------------------------------


def test_a_photos_life_is_recorded_in_order(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    assert kinds(box.db, about="DSC_1.JPG") == ["landed", "scrubbed", "sent"]


def test_landed_event_has_the_landing_time(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    db = sqlite3.connect(box.db)
    assert db.execute("SELECT at FROM events WHERE kind = 'landed'").fetchone()[0] == NOW - 5 * HOUR


@pytest.mark.parametrize(
    "kw, kind",
    [({"make": "Xiaomi", "second_image": None}, "skipped"), ({"taken": "2013:01:01 00:00:00"}, "look")],
)
def test_left_out_photo_is_recorded(box, kw, kind):
    make_jpeg(box.folder / "A.JPG", **kw)
    box.landed_long_ago("A.JPG")
    box.runner().tick()
    assert kinds(box.db, about="A.JPG")[-1] == kind


def test_culled_photo_is_recorded(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    r.tick()
    p.unlink()
    box.clock.now += 5 * MIN
    r.tick()
    assert kinds(box.db, about="DSC_1.JPG") == ["landed", "gone"]


def test_stuck_photo_is_recorded_once_not_every_try(box, monkeypatch):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")

    def full(*a, **k):
        raise OSError(errno.ENOSPC, "full")

    monkeypatch.setattr(incoming.Runner, "_stage", full)
    r = box.runner()
    for _ in range(5):
        r.tick()
        box.clock.now += 16 * MIN
    assert kinds(box.db, about="DSC_1.JPG").count("retrying") == 1


def test_lost_nas_is_recorded_once_and_so_is_its_return(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.runner().tick()
    shutil.move(box.root / "2026", box.root.parent / "away")
    for _ in range(4):  # the process ends and Docker starts it again
        with pytest.raises(incoming.RootUnavailable):
            box.runner().tick()
    shutil.move(box.root.parent / "away", box.root / "2026")
    box.runner().tick()
    found = kinds(box.db)
    assert found.count("nas_down") == 1
    assert found.count("nas_up") == 1
    assert found.count("started") <= 2


def test_old_events_are_dropped(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    r.tick()
    box.clock.now += 91 * DAY
    r.tick()
    db = sqlite3.connect(box.db)
    assert db.execute("SELECT MIN(at) FROM events").fetchone()[0] > box.clock.now - 90 * DAY


def test_arrival_is_recorded(g):
    g.chrome.labels[g.day] = g.there
    run(g.checker().tick())
    assert "seen" in kinds(g.box.db.parent / "google.db", about="DSC_1.JPG")


@pytest.mark.parametrize(
    "bad, down, up",
    [
        (ConnectionRefusedError("x"), "chrome_down", "chrome_up"),
        (google.ChromeState(True, False, None), "signed_out", "signed_in"),
        (google.ChromeState(True, True, "prompt"), "folder_lost", "folder_ok"),
    ],
)
def test_browser_trouble_is_recorded_once_and_so_is_the_end_of_it(g, bad, down, up):
    good = g.chrome.state
    c = g.checker()
    run(c.tick())
    g.chrome.state = bad
    for _ in range(4):
        run(c.tick())
    g.chrome.state = good
    for _ in range(3):
        run(c.tick())
    found = kinds(g.box.db.parent / "google.db")
    assert (found.count(down), found.count(up)) == (1, 1)


def test_restarted_checker_does_not_repeat_known_trouble(g):
    g.chrome.state = google.ChromeState(True, False, None)
    for _ in range(3):
        run(g.checker().tick())
    assert kinds(g.box.db.parent / "google.db").count("signed_out") == 1


# --- requests from the page -------------------------------------------------------


def ask(box, **what):
    folder = box.db.parent / "requests"
    folder.mkdir(exist_ok=True)
    ops.write_request(folder, **what)
    return folder


def with_requests(box):
    return box.runner(requests=box.db.parent / "requests")


def test_retry_asked_on_the_page_sends_again(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    r = with_requests(box)
    r.tick()
    (box.staging / "DSC_1.JPG").unlink()
    folder = ask(box, action="retry", path=f"{REL}/DSC_1.JPG")
    assert r.take_requests()
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]
    assert list(folder.iterdir()) == []
    assert "retry" in kinds(box.db, about="DSC_1.JPG")


def test_dismiss_asked_on_the_page(box):
    make_jpeg(box.folder / "DSC_1.JPG", taken="2013:01:01 00:00:00")
    box.landed_long_ago("DSC_1.JPG")
    r = with_requests(box)
    r.tick()
    ask(box, action="dismiss", path=f"{REL}/DSC_1.JPG")
    r.take_requests()
    assert rows(box)["DSC_1.JPG"]["status"] == "dismissed"


@pytest.mark.parametrize(
    "text",
    ["", "not json", "[]", '{"action": "delete", "path": "x"}', '{"action": "retry"}',
     '{"action": "retry", "path": 5}', '{"action": "retry", "path": "unknown.JPG"}', "x" * 100000],
)
def test_bad_request_is_dropped_without_harm(box, text):
    make_jpeg(box.folder / "DSC_1.JPG")
    r = with_requests(box)
    r.tick()
    folder = box.db.parent / "requests"
    folder.mkdir(exist_ok=True)
    (folder / "r.json").write_text(text)
    assert not r.take_requests()
    assert list(folder.iterdir()) == []
    assert rows(box)["DSC_1.JPG"]["status"] == "waiting"


@pytest.mark.skipif(os.name == "nt", reason="needs symlinks")
def test_request_that_is_a_link_is_not_read(box, tmp_path):
    r = with_requests(box)
    folder = box.db.parent / "requests"
    folder.mkdir(exist_ok=True)
    secret = tmp_path / "secret.json"
    secret.write_text('{"action": "retry", "path": "x"}')
    (folder / "r.json").symlink_to(secret)
    r.take_requests()
    assert secret.exists()
    assert list(folder.iterdir()) == []


def test_a_request_is_acted_on_within_seconds_not_at_the_next_pass(box, monkeypatch):
    r = with_requests(box)
    naps = []

    def nap(seconds):
        naps.append(seconds)
        if len(naps) == 3:
            make_jpeg(box.folder / "DSC_1.JPG")
            ask(box, action="retry", path="x")

    monkeypatch.setattr(incoming.time, "sleep", nap)
    monkeypatch.setattr(incoming.Runner, "take_requests", lambda self: len(naps) >= 3)
    incoming.wait(r, 300)
    assert sum(naps) <= 20


# --- settings ---------------------------------------------------------------------


def test_only_listed_cameras_are_sent(box):
    make_jpeg(box.folder / "A.JPG", make="Canon", second_image=None)
    make_jpeg(box.folder / "B.JPG", seed=2)
    box.landed_long_ago("A.JPG", "B.JPG")
    box.runner(cameras=("CANON",)).tick()
    assert box.sent() == ["A.JPG"]


def test_scrub_rules_reach_the_copy_and_the_history(box):
    import subprocess

    p = make_jpeg(box.folder / "A.JPG")
    subprocess.run(["exiftool", "-q", "-overwrite_original", "-P", "-Artist=Someone", str(p)], check=True)
    box.landed_long_ago("A.JPG")
    box.runner(rules=scrub.parse("mpf,names")).tick()
    sent = subprocess.run(
        ["exiftool", "-s3", "-Artist", str(box.staging / "A.JPG")], capture_output=True, text=True
    ).stdout
    assert sent == ""
    db = sqlite3.connect(box.db)
    assert db.execute("SELECT detail FROM events WHERE kind = 'scrubbed'").fetchone()[0] == "mpf, names"


def test_wrong_setting_is_shown_on_the_page(box, monkeypatch):
    make_jpeg(box.folder / "A.JPG")
    monkeypatch.setenv("SCRUB", "mpf,everything")
    code = incoming.main(
        ["--root", str(box.root), "--staging", str(box.staging), "--db", str(box.db),
         "--since", "2026-11-24"]
    )
    assert code == 1
    db = sqlite3.connect(box.db)
    assert "everything" in db.execute("SELECT error FROM heartbeat").fetchone()[0]
    assert box.sent() == []


def _run_main(box):
    return incoming.main(
        ["--root", str(box.root), "--staging", str(box.staging), "--db", str(box.db),
         "--since", "2026-11-24", "--wait-hours", "0"]
    )


@pytest.mark.parametrize("value", [None, "", "ro"])
def test_photos_access_read_only_leaves_the_nas_file(box, monkeypatch, value):
    # Compose passes a blank when the setting is left out.
    p = make_jpeg(box.folder / "DSC_1.JPG")
    before = p.read_bytes()
    if value is None:
        monkeypatch.delenv("PHOTOS_ACCESS", raising=False)
    else:
        monkeypatch.setenv("PHOTOS_ACCESS", value)
    assert _run_main(box) == 0
    assert p.read_bytes() == before
    assert box.sent() == ["DSC_1.JPG"]


def test_photos_access_rw_strips_the_nas_file_too(box, monkeypatch):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    monkeypatch.setenv("PHOTOS_ACCESS", "rw")
    assert _run_main(box) == 0
    assert p.read_bytes() == (box.staging / "DSC_1.JPG").read_bytes()
    assert not has_mpf(p)


def test_photos_access_rw_on_a_read_only_share_is_shown_and_nothing_sent(box, monkeypatch):
    # A file by file failure would hide that the mount or the NAS rule is wrong.
    make_jpeg(box.folder / "DSC_1.JPG")
    monkeypatch.setenv("PHOTOS_ACCESS", "rw")
    real = os.access
    monkeypatch.setattr(
        incoming.os, "access", lambda p, mode, **k: False if mode & os.W_OK else real(p, mode, **k)
    )
    assert _run_main(box) == 1
    db = sqlite3.connect(box.db)
    assert "PHOTOS_ACCESS" in db.execute("SELECT error FROM heartbeat").fetchone()[0]
    assert box.sent() == []


def test_photos_access_unknown_value_is_shown(box, monkeypatch):
    make_jpeg(box.folder / "DSC_1.JPG")
    monkeypatch.setenv("PHOTOS_ACCESS", "yes")
    assert _run_main(box) == 1
    db = sqlite3.connect(box.db)
    assert "PHOTOS_ACCESS" in db.execute("SELECT error FROM heartbeat").fetchone()[0]
    assert box.sent() == []


# --- backups ------------------------------------------------------------------------


def test_database_is_backed_up_daily_and_seven_are_kept(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    for _ in range(12):
        r.tick()
        box.clock.now += DAY + 1
    saved = sorted((box.db.parent / "backup").glob("state-*.db"))
    assert len(saved) == 7
    db = sqlite3.connect(saved[-1])
    assert db.execute("SELECT COUNT(*) FROM incoming").fetchone()[0] == 1


def test_backup_fault_does_not_stop_photos(box, monkeypatch):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")

    def full(*a, **k):
        raise OSError(errno.ENOSPC, "full")

    monkeypatch.setattr(ops, "backup", full)
    box.runner().tick()
    assert box.sent() == ["DSC_1.JPG"]


# --- what the pages are given ----------------------------------------------------------


def test_photos_are_paged(state):  # noqa: F811
    for n in range(120):
        state.photo(f"{n:03}.JPG", sent_at=NOW, landed=NOW - n)
    one = status.photos(state.dir, 4 * HOUR, page=1)
    three = status.photos(state.dir, 4 * HOUR, page=3)
    assert (one.total, one.pages, len(one.items)) == (120, 3, 50)
    assert [p.name for p in three.items][:2] == ["100.JPG", "101.JPG"]


@pytest.mark.parametrize("page", [0, -1, 99])
def test_page_out_of_range_is_the_nearest_page(state, page):  # noqa: F811
    for n in range(60):
        state.photo(f"{n}.JPG", sent_at=NOW)
    assert status.photos(state.dir, 1, page=page).page in (1, 2)


def test_photos_can_be_searched_by_name_and_folder(state):  # noqa: F811
    state.photo("DSC_1.JPG", sent_at=NOW)
    state.photo("IMG_2.JPG", sent_at=NOW)
    assert [p.name for p in status.photos(state.dir, 1, search="dsc_").items] == ["DSC_1.JPG"]
    assert status.photos(state.dir, 1, search="folder").total == 2


@pytest.mark.parametrize("text", ["%", "_", "'", '"; DROP TABLE incoming', "\\"])
def test_search_text_is_taken_literally(state, text):  # noqa: F811
    state.photo("DSC.JPG", sent_at=NOW)
    assert status.photos(state.dir, 1, search=text).total == 0
    assert status.photos(state.dir, 1).total == 1


@pytest.mark.parametrize("stage", status.STAGES)
def test_photos_can_be_filtered_by_where_they_are(state, stage):  # noqa: F811
    state.photo("w", "waiting", landed=NOW)
    state.photo("s", sent_at=NOW)
    state.photo("g", sent_at=NOW, confirmed=NOW)
    state.photo("k", "skipped")
    state.photo("l", "look")
    state.photo("f", "failed")
    found = status.photos(state.dir, 1, stage=stage)
    assert [p.stage for p in found.items] == [stage]


def test_history_merges_both_databases_newest_first(state):  # noqa: F811
    state.event("incoming.db", NOW - 60, "sent", "2026/a/x.JPG")
    state.event("google.db", NOW, "seen", "2026/a/x.JPG")
    state.event("google.db", NOW - 30, "signed_out")
    found = [e for e in events.history(state.dir, limit=10) if e.kind != "started"]
    assert [e.kind for e in found] == ["seen", "signed_out", "sent"]
    assert [e.job for e in found] == ["google", "google", "incoming"]


def test_history_of_one_photo(state):  # noqa: F811
    state.event("incoming.db", NOW - 60, "sent", "2026/a/x.JPG")
    state.event("incoming.db", NOW - 50, "sent", "2026/a/y.JPG")
    assert [e.path for e in events.history(state.dir, path="2026/a/x.JPG")] == ["2026/a/x.JPG"]


def test_history_of_trouble_only(state):  # noqa: F811
    state.event("incoming.db", NOW, "sent", "x")
    state.event("google.db", NOW, "signed_out")
    assert [e.kind for e in events.history(state.dir, trouble=True)] == ["signed_out"]


def flow(state):  # noqa: F811
    return {s.key: s for s in ops.flow(state.read())}


def test_flow_has_every_step_in_order(state):  # noqa: F811
    assert [s.key for s in ops.flow(state.read())] == [
        "nas", "wait", "scrub", "staging", "chrome", "google",
    ]


def test_flow_is_all_good_when_nothing_is_wrong(state):  # noqa: F811
    state.photo("a", sent_at=NOW, confirmed=NOW)
    assert {s.state for s in flow(state).values()} == {"good"}


@pytest.mark.parametrize(
    "break_it, step",
    [
        (lambda s: s.beat(error="gone"), "nas"),
        (lambda s: s.photo("w", "waiting", landed=NOW - 9 * HOUR), "wait"),
        (lambda s: s.photo("f", "failed"), "scrub"),
        (lambda s: s.health(folder="prompt"), "staging"),
        (lambda s: s.health(error="refused"), "chrome"),
        (lambda s: s.health(signed_in=0), "chrome"),
        (lambda s: s.photo("s", sent_at=NOW - 9 * HOUR), "google"),
    ],
)
def test_flow_shows_where_it_is_stuck(state, break_it, step):  # noqa: F811
    break_it(state)
    assert [k for k, s in flow(state).items() if s.state == "bad"] == [step]


def test_checklist_for_a_new_install(tmp_path):
    steps = ops.checklist(status.read(tmp_path, NOW, 1))
    assert [s.done for s in steps] == [False] * len(steps)
    assert all(s.how for s in steps)


def test_checklist_is_done_when_a_photo_has_been_seen(state):  # noqa: F811
    state.photo("a", sent_at=NOW, confirmed=NOW)
    assert all(s.done for s in ops.checklist(state.read()))


def test_set_up_list_does_not_come_back_once_it_has_worked(client, state):  # noqa: F811
    state.photo("a", sent_at=NOW, confirmed=NOW)
    state.health(folder="prompt")
    html = get(client).text
    assert "Set it up" not in html
    assert "lost permission" in html


def test_new_install_shows_the_set_up_list_without_alarm(client, state):  # noqa: F811
    assert "Set it up" in get(client).text


def test_samples_are_kept_in_memory_for_a_day(state):  # noqa: F811
    s = ops.Samples(state.dir)
    for n in range(2000):
        s.take(NOW + n * 60)
    assert len(s.series("waiting")) == 1440


# --- the pages themselves -------------------------------------------------------------


def post(client, path="2026/folder/f.JPG", action="retry", **headers):  # noqa: F811
    from tests.test_product import token

    h = {"Cf-Access-Jwt-Assertion": token(), "Origin": "https://testserver",
         "Host": "testserver", **headers}
    return client.post(
        "/photo", data={"path": path, "action": action}, headers={k: v for k, v in h.items() if v},
        follow_redirects=False,
    )


def asked(state):  # noqa: F811
    folder = state.dir / "requests"
    return [json.loads(p.read_text()) for p in folder.glob("*.json")] if folder.exists() else []


def test_button_leaves_a_request(client, state):  # noqa: F811
    state.photo("f.JPG", "failed")
    r = post(client)
    assert r.status_code == 303
    assert asked(state) == [{"action": "retry", "path": "2026/folder/f.JPG"}]


@pytest.mark.parametrize(
    "headers",
    [{"Cf-Access-Jwt-Assertion": None}, {"Origin": "https://evil.example"}, {"Origin": "null"},
     {"Origin": None}],
    ids=["no-token", "other-site", "null-origin", "no-origin"],
)
def test_button_pressed_from_elsewhere_is_refused(client, state, headers):  # noqa: F811
    state.photo("f.JPG", "failed")
    assert post(client, **headers).status_code == 403
    assert asked(state) == []


@pytest.mark.parametrize("kw", [{"action": "delete"}, {"path": "nope"}, {"path": ""}])
def test_button_with_nonsense_is_refused(client, state, kw):  # noqa: F811
    state.photo("f.JPG", "failed")
    assert post(client, **kw).status_code == 400
    assert asked(state) == []


def test_too_many_requests_are_refused(client, state):  # noqa: F811
    state.photo("f.JPG", "failed")
    codes = [post(client).status_code for _ in range(60)]
    assert codes[-1] == 429
    assert len(asked(state)) <= 50


@pytest.mark.parametrize("path", ["/", "/history", "/ops", "/?page=2&q=x&stage=failed"])
def test_every_page_opens(client, state, path):  # noqa: F811
    state.photo("f.JPG", "failed")
    state.event("google.db", NOW, "signed_out", detail="<b>x</b>")
    r = get(client, path)
    assert r.status_code == 200
    assert "<b>x</b>" not in r.text


@pytest.mark.parametrize("path", ["/?page=x", "/?stage=nope", "/history?path=" + "x" * 5000])
def test_odd_addresses_do_not_break_a_page(client, path):  # noqa: F811
    assert get(client, path).status_code in (200, 400, 422)


def test_page_does_not_refresh_while_someone_is_searching(client, state):  # noqa: F811
    assert 'http-equiv="refresh"' in get(client, "/").text
    assert 'http-equiv="refresh"' not in get(client, "/?q=dsc").text


def test_forms_can_only_go_to_this_site(client):  # noqa: F811
    assert "form-action 'self'" in get(client).headers["content-security-policy"]


def test_ops_page_shows_versions_and_disk(client, state):  # noqa: F811
    m = metrics.Metrics("incoming", state.dir, clock=lambda: NOW, version="abc1234")
    m.set("gphoto.disk.free", 5 * 2**30, "By", "h", mount="state")
    m.set("gphoto.pass.duration", 0.07, "s", "h")
    m.save()
    html = get(client, "/ops").text
    assert "abc1234" in html
    assert "5.0 GB" in html


def test_ops_page_survives_a_broken_metrics_file(client, state):  # noqa: F811
    (state.dir / "metrics-google.json").write_text("{half")
    assert get(client, "/ops").status_code == 200


def test_started_times_are_real(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.runner().tick()
    assert datetime.fromtimestamp(
        json.loads((box.db.parent / "metrics-incoming.json").read_text())["started"]
    ).year >= 2026


def test_export_is_stopped_with_the_page(state):  # noqa: F811
    from fastapi.testclient import TestClient

    from gphoto import web

    stopped = []
    app = web.create_app(state.dir, None, 1, on_stop=lambda: stopped.append(1))
    with TestClient(app):
        assert stopped == []
    assert stopped == [1]


def test_checker_on_is_used(state):  # noqa: F811
    run(checker_on(state).tick())
    assert "started" in kinds(state.dir / "google.db")


# --- review 2026-11-26 ----------------------------------------------------------------


def test_photo_on_the_way_can_be_dismissed_on_the_page(client, state):  # noqa: F811
    state.photo("w.JPG", sent_at=NOW - 3 * HOUR)
    page = get(client).text
    assert 'value="dismiss"' in page


def test_dismissed_photo_is_no_longer_on_the_way_or_late(state):  # noqa: F811
    state.photo("w.JPG", sent_at=NOW - 3 * HOUR, landed=NOW - 7 * HOUR)
    before = state.read()
    assert before.counts["on the way"] == 1
    assert [p for p in before.problems if "arrived" in p.title]
    state._do("incoming.db", "UPDATE incoming SET status = 'dismissed'")
    after = state.read()
    assert after.counts["on the way"] == 0
    assert not [p for p in after.problems if "arrived" in p.title]


def test_runner_dismisses_a_sent_photo(g):
    assert g.box.runner().dismiss(f"{REL}/DSC_1.JPG")
    assert rows(g.box)["DSC_1.JPG"]["status"] == "dismissed"


def test_readyz_is_ok_when_the_page_is_green(client, state):  # noqa: F811
    r = client.get("/readyz")
    assert (r.status_code, r.text) == (200, "ok")


def test_readyz_fails_when_the_page_says_needs_you(client, state):  # noqa: F811
    state.health(signed_in=0)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.text == "needs you: chrome"


def test_readyz_names_areas_only_never_paths(client, state):  # noqa: F811
    # It answers without a sign-in, so it must not show family folder names.
    state.photo("f.JPG", "failed")
    r = client.get("/readyz")
    assert r.status_code == 503
    assert "folder" not in r.text and "JPG" not in r.text


def test_healthz_stays_ok_when_the_page_says_needs_you(client, state):  # noqa: F811
    # autoheal restarts an unhealthy container, which would not sign Google back in.
    state.health(signed_in=0)
    assert client.get("/healthz").status_code == 200


def _many_events(state, count):  # noqa: F811
    for n in range(count):
        state.event("incoming.db" if n % 2 else "google.db", NOW - (n // 4), "sent", f"p{n}")


def test_history_pages_cover_everything_once_in_order(state):  # noqa: F811
    # Several events share one second, and come from both databases.
    _many_events(state, 250)
    seen, after = [], None
    for _ in range(10):
        found, after = events.page(state.dir, 100, after=after)
        seen += found
        if after is None:
            break
    paths = [e.path for e in seen if e.kind == "sent"]
    assert sorted(paths) == sorted(f"p{n}" for n in range(250))
    assert len(paths) == 250
    assert [e.at for e in seen] == sorted((e.at for e in seen), reverse=True)


def test_history_page_has_older_link_that_works(client, state):  # noqa: F811
    _many_events(state, 250)
    first = get(client, "/history").text
    assert "Older" in first
    link = first.split('class="older" href="')[1].split('"')[0].replace("&amp;", "&")
    second = get(client, link)
    assert second.status_code == 200
    assert "Newest" in second.text


def test_history_older_link_keeps_the_filter(client, state):  # noqa: F811
    for n in range(150):
        state.event("google.db", NOW - n, "signed_out")
    page = get(client, "/history?trouble=true").text
    assert "trouble=true" in page.split('class="older" href="')[1].split('"')[0]


def test_bad_history_cursor_shows_the_newest(client, state):  # noqa: F811
    assert get(client, "/history?after=rubbish").status_code == 200


def _disk(state, free):  # noqa: F811
    m = metrics.Metrics("incoming", state.dir, clock=lambda: NOW, version="t")
    m.set("gphoto.disk.free", free, "By", "Free", mount="state")
    m.save()


def test_low_disk_is_a_problem(state):  # noqa: F811
    _disk(state, 1.5e9)
    s = state.read()
    low = [p for p in s.problems if "disk" in p.title.lower()]
    assert len(low) == 1 and low[0].area == "staging"
    assert "1.5 GB" in low[0].title


@pytest.mark.parametrize("free", [50e9, None])
def test_enough_or_unknown_disk_is_not_a_problem(state, free):  # noqa: F811
    if free is not None:
        _disk(state, free)
    assert not [p for p in state.read().problems if "disk" in p.title.lower()]


@pytest.mark.parametrize("hours, words", [(1, "1 hour"), (5, "5 hours"), (72, "3 days")])
def test_up_for_wording(tmp_path, hours, words):
    snapshot = {"started": NOW - hours * HOUR, "metrics": {}}
    found = dict(charts.facts(tmp_path, {"incoming": snapshot, "google": None}, NOW, 4 * HOUR))
    assert dict(found["Versions"])["NAS check up for"] == words
