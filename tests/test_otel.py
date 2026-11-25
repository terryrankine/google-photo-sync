"""What arrives at a real OTLP receiver, and what happens when there is none."""

import contextlib
import hashlib
import json
import logging
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from gphoto import otel, web

REPO = Path(__file__).parent.parent
FOLDER = "2026/Secret birthday"
PHOTO = f"{FOLDER}/DSC_1.JPG"
NOW = 1_795_600_000.0
TABLE = (
    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " at REAL NOT NULL, kind TEXT NOT NULL, path TEXT, detail TEXT)"
)


# --- a receiver ---------------------------------------------------------------


class Receiver:
    """OTLP over HTTP. Keeps the raw requests and reads them with the official classes."""

    def __init__(self, port=0, status=200, hang=False):
        self.requests = []
        self.released = threading.Event()
        if not hang:
            self.released.set()
        self.status = status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.released.wait(60)
                outer.requests.append((self.path, dict(self.headers), body))
                with contextlib.suppress(OSError):
                    self.send_response(outer.status)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.server.handle_error = lambda *_: None
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.released.set()
        self.server.shutdown()
        self.server.server_close()

    def bodies(self, path):
        return [body for where, _, body in list(self.requests) if where == path]

    def logs(self):
        found = []
        for body in self.bodies("/v1/logs"):
            for resource in ExportLogsServiceRequest.FromString(body).resource_logs:
                for scope in resource.scope_logs:
                    found += scope.log_records
        return found

    def spans(self):
        found = []
        for body in self.bodies("/v1/traces"):
            for resource in ExportTraceServiceRequest.FromString(body).resource_spans:
                for scope in resource.scope_spans:
                    found += scope.spans
        return found

    def metric_batches(self):
        """One {(name, job): [(metric, point)]} for each export."""
        batches = []
        for body in self.bodies("/v1/metrics"):
            batch = {}
            for resource in ExportMetricsServiceRequest.FromString(body).resource_metrics:
                for scope in resource.scope_metrics:
                    for metric in scope.metrics:
                        for point in getattr(metric, metric.WhichOneof("data")).data_points:
                            key = metric.name, plain(point)["gphoto.job"]
                            batch.setdefault(key, []).append((metric, point))
            batches.append(batch)
        return batches

    def metrics(self, count=1):
        """The newest export, after that many more have come in."""
        target = len(self.bodies("/v1/metrics")) + count
        wait_for(lambda: len(self.bodies("/v1/metrics")) >= target)
        return self.metric_batches()[-1]


def plain(item):
    return {a.key: getattr(a.value, a.value.WhichOneof("value")) for a in item.attributes}


def wait_for(check, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.02)
    raise AssertionError("did not happen in time")


def settle(seconds=0.5):
    """Long enough for several polls and exports at the test's speed."""
    time.sleep(seconds)


def patiently(act):
    """On Windows a file cannot be swapped while the exporter has it open."""
    for _ in range(100):
        try:
            return act()
        except PermissionError:
            time.sleep(0.02)
    return act()


# --- a state folder -------------------------------------------------------------


class State:
    def __init__(self, folder):
        self.folder = folder

    def db(self, job):
        db = sqlite3.connect(self.folder / f"{job}.db", timeout=5)
        db.execute(TABLE)
        return db

    def add(self, job, kind, at, path=None, detail=None):
        with contextlib.closing(self.db(job)) as db, db:
            db.execute(
                "INSERT INTO events (at, kind, path, detail) VALUES (?, ?, ?, ?)",
                (at, kind, path, detail),
            )

    def replace(self, job, rows):
        """Put another database in its place, as a restore would."""
        with contextlib.closing(sqlite3.connect(self.folder / "other.db")) as db, db:
            db.execute(TABLE)
            db.executemany("INSERT INTO events (at, kind, path) VALUES (?, ?, ?)", rows)
        patiently(lambda: os.replace(self.folder / "other.db", self.folder / f"{job}.db"))

    def metrics(self, job, metrics, at=None, started=None, version="abc1234"):
        at = time.time() if at is None else at
        text = json.dumps(
            {
                "job": job, "at": at, "started": at - 60 if started is None else started,
                "version": version, "metrics": metrics,
            }
        )
        temp = self.folder / f".{job}.tmp"
        temp.write_text(text)
        patiently(lambda: os.replace(temp, self.folder / f"metrics-{job}.json"))


def gauge(value, **attributes):
    return {
        "type": "gauge", "unit": "s", "help": "Seconds",
        "points": [{"attributes": attributes, "value": value}],
    }


def counter(value, **attributes):
    return {
        "type": "counter", "unit": "{photo}", "help": "Photos",
        "points": [{"attributes": attributes, "value": value}],
    }


def histogram(**changes):
    point = {
        "attributes": {}, "count": 3, "sum": 1.2, "min": 0.3, "max": 0.5,
        "bounds": [0.1, 0.5, 1, 5], "buckets": [0, 2, 1, 0, 0],
    }
    return {"type": "histogram", "unit": "s", "help": "Took", "points": [point | changes]}


@pytest.fixture
def state(tmp_path):
    state = State(tmp_path)
    for job in ("incoming", "google"):
        with contextlib.closing(state.db(job)) as db:
            db.commit()
    return state


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    for name in list(os.environ):
        if name.startswith("OTEL_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("OTEL_BSP_SCHEDULE_DELAY", "50")
    monkeypatch.setenv("OTEL_BLRP_SCHEDULE_DELAY", "50")
    monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", "100")
    monkeypatch.setattr(otel, "POLL", 0.05)


@pytest.fixture
def receiver():
    receiver = Receiver()
    yield receiver
    receiver.close()


@pytest.fixture
def run(state):
    """Start an exporter, and stop it at the end whatever happened."""
    started = []

    def start():
        exporter = otel.start(state.folder)
        if exporter:
            started.append(exporter)
        return exporter

    yield start
    for exporter in started:
        exporter.stop()


@pytest.fixture
def on(monkeypatch, receiver, run):
    """The exporter, sending to the receiver."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", receiver.url)

    def start():
        exporter = run()
        assert exporter is not None
        return exporter

    return start


def ns(seconds):
    return round(seconds * 1_000_000) * 1000


def lines(caplog, level=logging.WARNING):
    return [r for r in caplog.records if r.name != "httpx" and r.levelno >= level]


# --- off -------------------------------------------------------------------------

ENDPOINT = {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9"}


def in_a_new_process(code, env):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("OTEL_")}
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, env=clean | env, capture_output=True, text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"OTEL_EXPORTER_OTLP_ENDPOINT": ""},
        {"OTEL_SERVICE_NAME": "x", "OTEL_EXPORTER_OTLP_HEADERS": "a=b"},
        ENDPOINT | {"OTEL_SDK_DISABLED": "TRUE"},
        ENDPOINT | {f"OTEL_{s}_EXPORTER": "none" for s in ("TRACES", "METRICS", "LOGS")},
        ENDPOINT | {"OTEL_EXPORTER_OTLP_PROTOCOL": "grpc"},
    ],
)
def test_off_starts_nothing_and_imports_nothing(tmp_path, env):
    in_a_new_process(
        "import sys, threading\n"
        "from gphoto import otel\n"
        f"assert otel.start({str(tmp_path)!r}) is None\n"
        "assert threading.active_count() == 1\n"
        "tops = {m.split('.')[0] for m in sys.modules}\n"
        "assert not tops & {'opentelemetry', 'requests', 'google'}, tops\n",
        env,
    )


@pytest.mark.slow
def test_on_does_import_the_sdk(tmp_path):
    """Guards the test above: its check must be able to fail."""
    in_a_new_process(
        "import sys\n"
        "from gphoto import otel\n"
        f"e = otel.start({str(tmp_path)!r})\n"
        "assert e is not None and 'opentelemetry.sdk.trace' in sys.modules\n"
        "e.stop()\n",
        ENDPOINT,
    )


@pytest.mark.parametrize("protocol", ["grpc", "http/json", "nonsense"])
def test_another_protocol_is_one_clear_error_and_stays_off(monkeypatch, run, caplog, protocol):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", protocol)
    assert run() is None
    (record,) = lines(caplog)
    assert record.levelno == logging.ERROR
    assert protocol in record.getMessage() and "http/protobuf" in record.getMessage()


def test_another_protocol_for_one_signal_leaves_the_others_on(
    monkeypatch, on, state, receiver, caplog
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_PROTOCOL", "grpc")
    on()
    state.add("incoming", "started", time.time())
    receiver.metrics()
    settle()
    assert not receiver.bodies("/v1/logs")
    (record,) = lines(caplog)
    assert "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL" in record.getMessage()


def test_the_right_protocol_may_be_named(monkeypatch, on, receiver):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    on()
    receiver.metrics()


@pytest.mark.parametrize("signal", ["TRACES", "METRICS", "LOGS"])
def test_one_signal_can_be_switched_off(monkeypatch, on, state, receiver, signal):
    monkeypatch.setenv(f"OTEL_{signal}_EXPORTER", "none")
    on()
    whole_life(state)
    expected = {"/v1/traces", "/v1/metrics", "/v1/logs"} - {f"/v1/{signal.lower()}"}
    wait_for(lambda: {path for path, _, _ in list(receiver.requests)} >= expected)
    settle()
    assert {path for path, _, _ in receiver.requests} == expected


def test_an_exporter_that_is_not_here_is_one_error(monkeypatch, on, receiver, caplog):
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "zipkin")
    on()
    receiver.metrics()
    (record,) = lines(caplog)
    assert "OTEL_TRACES_EXPORTER" in record.getMessage()


def test_only_the_signal_with_an_endpoint_is_sent(monkeypatch, run, state, receiver):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", f"{receiver.url}/other/place")
    assert run()
    whole_life(state)
    wait_for(lambda: receiver.bodies("/other/place"))
    settle()
    assert {path for path, _, _ in receiver.requests} == {"/other/place"}


# --- who is sending -------------------------------------------------------------------


def resource_of(receiver):
    wait_for(lambda: receiver.bodies("/v1/metrics"))
    request = ExportMetricsServiceRequest.FromString(receiver.bodies("/v1/metrics")[0])
    return plain(request.resource_metrics[0].resource)


def test_the_standard_names_set_headers_and_resource(monkeypatch, on, state, receiver):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-key=abc%20def,x-other=2")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "photos")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment.name=home")
    on()
    whole_life(state)
    wait_for(lambda: len({path for path, _, _ in list(receiver.requests)}) == 3)
    resource = resource_of(receiver)
    assert resource["service.name"] == "photos"
    assert resource["deployment.environment.name"] == "home"
    for _, headers, _ in receiver.requests:
        assert headers["x-key"] == "abc def" and headers["x-other"] == "2"
    trace = ExportTraceServiceRequest.FromString(receiver.bodies("/v1/traces")[0])
    assert plain(trace.resource_spans[0].resource) == resource
    log = ExportLogsServiceRequest.FromString(receiver.bodies("/v1/logs")[0])
    assert plain(log.resource_logs[0].resource) == resource


def test_without_a_name_it_is_gphoto(on, receiver):
    on()
    assert resource_of(receiver)["service.name"] == "gphoto"


def test_a_name_among_the_resource_attributes_is_kept(monkeypatch, on, receiver):
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.name=mine")
    on()
    assert resource_of(receiver)["service.name"] == "mine"


def test_the_pages_own_framework_sends_nothing(on, state, receiver):
    """FastAPI traces requests as soon as a global provider exists, so none is set."""
    from opentelemetry import _logs, metrics, trace

    on()
    page_works(state)
    receiver.metrics(2)
    assert not receiver.spans() and not receiver.logs()
    for provider in (
        trace.get_tracer_provider(), metrics.get_meter_provider(), _logs.get_logger_provider()
    ):
        assert "Proxy" in type(provider).__name__


# --- metrics ---------------------------------------------------------------------------


def test_gauge_counter_and_histogram_arrive_as_they_were(on, state, receiver):
    at = time.time() - 5
    started = at - 1000
    state.metrics(
        "incoming",
        {
            "gphoto.pass.duration": gauge(0.07),
            "gphoto.photos": {
                "type": "counter", "unit": "{photo}", "help": "Photos handled",
                "points": [
                    {"attributes": {"outcome": "sent"}, "value": 42},
                    {"attributes": {"outcome": "failed"}, "value": 1},
                ],
            },
            "gphoto.scrub.duration": histogram(),
        },
        at=at, started=started, version="3f8e74a",
    )
    on()
    batch = receiver.metrics()

    ((metric, point),) = batch["gphoto.pass.duration", "incoming"]
    assert metric.WhichOneof("data") == "gauge"
    assert (metric.unit, metric.description) == ("s", "Seconds")
    assert point.as_double == 0.07
    assert point.time_unix_nano == ns(at)

    both = batch["gphoto.photos", "incoming"]
    assert {(plain(p)["outcome"], p.as_int) for _, p in both} == {("sent", 42), ("failed", 1)}
    for metric, point in both:
        assert metric.sum.is_monotonic
        assert metric.sum.aggregation_temporality == 2  # cumulative
        assert point.start_time_unix_nano == ns(started)
        assert point.time_unix_nano == ns(at)

    ((metric, point),) = batch["gphoto.scrub.duration", "incoming"]
    assert metric.histogram.aggregation_temporality == 2
    assert (point.count, point.sum, point.min, point.max) == (3, 1.2, 0.3, 0.5)
    assert list(point.explicit_bounds) == [0.1, 0.5, 1, 5]
    assert list(point.bucket_counts) == [0, 2, 1, 0, 0]
    assert point.start_time_unix_nano == ns(started)
    assert point.time_unix_nano == ns(at)


def test_the_same_name_from_both_processes_stays_apart(on, state, receiver):
    state.metrics("incoming", {"gphoto.disk.free": gauge(1)}, version="aaa")
    state.metrics("google", {"gphoto.disk.free": gauge(2)}, version="bbb")
    on()
    batch = receiver.metrics()
    assert batch["gphoto.disk.free", "incoming"][0][1].as_int == 1
    assert batch["gphoto.disk.free", "google"][0][1].as_int == 2


def test_a_restarted_process_starts_again_from_its_own_start(on, state, receiver):
    first = time.time() - 600
    state.metrics("incoming", {"gphoto.photos": counter(42), "gphoto.scrub.duration": histogram()},
                  at=first + 100, started=first)
    on()
    ((_, before),) = receiver.metrics()["gphoto.photos", "incoming"]
    second = time.time() - 60
    small = histogram(count=1, sum=0.2, min=0.2, max=0.2, buckets=[0, 1, 0, 0, 0])
    state.metrics("incoming", {"gphoto.photos": counter(2), "gphoto.scrub.duration": small},
                  at=second + 10, started=second)
    batch = receiver.metrics(2)
    ((_, after),) = batch["gphoto.photos", "incoming"]
    assert (before.as_int, before.start_time_unix_nano) == (42, ns(first))
    assert (after.as_int, after.start_time_unix_nano) == (2, ns(second))
    # The old series ended before the new one began, or a reader would see both at once.
    assert before.time_unix_nano <= after.start_time_unix_nano
    ((_, after),) = batch["gphoto.scrub.duration", "incoming"]
    assert (after.count, after.start_time_unix_nano) == (1, ns(second))


def names(batch, job):
    return {name for name, whose in batch if whose == job}


OWN = {"gphoto.metrics.age", "gphoto.metrics.usable"}


def own(batch, job):
    return (
        batch["gphoto.metrics.age", job][0][1].as_double,
        batch["gphoto.metrics.usable", job][0][1].as_int,
    )


def test_a_fresh_file_has_its_age_and_is_usable(on, state, receiver):
    state.metrics("google", {"gphoto.signed_in": gauge(1)}, at=time.time() - 30)
    on()
    batch = receiver.metrics()
    age, usable = own(batch, "google")
    assert 30 <= age < 40 and usable == 1
    assert batch["gphoto.metrics.age", "google"][0][0].unit == "s"


def test_a_missing_file_sends_nothing_and_says_so(on, state, receiver):
    state.metrics("incoming", {"gphoto.waiting": gauge(3)})
    on()
    batch = receiver.metrics()
    assert "gphoto.waiting" in names(batch, "incoming")
    assert names(batch, "google") == {"gphoto.metrics.usable"}  # nothing is known of its age
    assert batch["gphoto.metrics.usable", "google"][0][1].as_int == 0


def test_a_file_that_goes_missing_keeps_ageing(on, state, receiver):
    state.metrics("google", {"gphoto.signed_in": gauge(1)}, at=time.time() - 100)
    on()
    receiver.metrics()
    patiently((state.folder / "metrics-google.json").unlink)
    batch = receiver.metrics(2)
    assert names(batch, "google") == OWN
    age, usable = own(batch, "google")
    assert 100 <= age < 120 and usable == 0


@pytest.mark.parametrize(
    "text",
    ["", "{", '{"job": "incoming", "at": 17955', "[]", "null", "\x00\xff", '{"metrics": {}}',
     '{"job": "incoming", "at": "x", "started": 1, "metrics": {}}',
     '{"job": "incoming", "at": NaN, "started": 1, "metrics": {}}',
     '{"job": "incoming", "at": true, "started": 1, "metrics": {}}',
     '{"job": "incoming", "at": 1e999, "started": 1, "metrics": {}}',
     "[" * 100_000],
)
def test_a_half_written_file_sends_nothing_but_the_age_of_the_file(on, state, receiver, text):
    path = state.folder / "metrics-incoming.json"
    path.write_text(text, encoding="latin-1")
    os.utime(path, (time.time() - 50, time.time() - 50))
    on()
    batch = receiver.metrics(2)
    assert names(batch, "incoming") == OWN
    age, usable = own(batch, "incoming")
    assert 50 <= age < 70 and usable == 0


@pytest.mark.parametrize("job, limit", [("incoming", 15 * 60), ("google", 10 * 60)])
def test_a_stale_file_sends_only_its_age(on, state, receiver, job, limit):
    state.metrics(job, {"gphoto.waiting": gauge(3)}, at=time.time() - limit - 60)
    on()
    batch = receiver.metrics()
    assert names(batch, job) == OWN
    age, usable = own(batch, job)
    assert age >= limit + 60 and usable == 0


@pytest.mark.parametrize("at, started", [(3600, 0), (0, 60)])
def test_impossible_times_are_not_passed_on(on, state, receiver, at, started):
    now = time.time()
    state.metrics("incoming", {"gphoto.waiting": gauge(3)}, at=now + at, started=now + started)
    on()
    assert names(receiver.metrics(), "incoming") == OWN


@pytest.mark.parametrize(
    "bad",
    [
        None, 7, {}, {"type": "summary", "points": []}, gauge("x"), gauge(None), gauge(True),
        gauge(float("nan")), gauge(float("inf")), gauge(2**70), counter(-1), counter(float("nan")),
        gauge(1, outcome=["list"]), gauge(1, outcome=None), {"type": "gauge", "points": None},
        {"type": "gauge", "points": [3]}, gauge(1) | {"unit": 5}, gauge(1) | {"help": 5},
        {"type": "gauge", "points": [{"attributes": 4, "value": 1}]},
        histogram(buckets=[1, 2]), histogram(buckets=[0, 2, 2, 0, 0]), histogram(count=-3),
        histogram(buckets=[0, 4, -1, 0, 0]), histogram(bounds=[1, 0.5, 2, 5]),
        histogram(bounds="abcd"), histogram(sum="x"), histogram(min="x"), histogram(count=3.5),
        histogram(bounds=None), histogram(buckets=None),
    ],
)
def test_one_bad_metric_does_not_take_the_good_ones_with_it(on, state, receiver, bad):
    state.metrics("incoming", {"gphoto.bad": bad, "gphoto.good": gauge(1)})
    on()
    assert names(receiver.metrics(2), "incoming") == OWN | {"gphoto.good"}


def test_an_empty_histogram_has_no_min_or_max(on, state, receiver):
    empty = histogram(count=0, sum=0, min=None, max=None, buckets=[0] * 5)
    state.metrics("incoming", {"gphoto.scrub.duration": empty})
    on()
    ((_, point),) = receiver.metrics()["gphoto.scrub.duration", "incoming"]
    assert point.count == 0 and not point.HasField("min") and not point.HasField("max")


# --- logs --------------------------------------------------------------------------------


def kinds(receiver):
    return [plain(r)["gphoto.kind"] for r in receiver.logs()]


def test_only_what_happens_after_the_start_is_sent_once_with_its_own_time(on, state, receiver):
    state.add("incoming", "landed", NOW - 10, f"{FOLDER}/OLD.JPG")
    state.add("google", "started", NOW - 5)
    on()
    state.add("incoming", "landed", NOW + 0.25, PHOTO, "x")
    state.add("google", "chrome_down", NOW + 7.5, None, "y")
    wait_for(lambda: len(receiver.logs()) >= 2)
    settle()
    assert len(receiver.logs()) == 2
    logs = {plain(r)["gphoto.kind"]: r for r in receiver.logs()}
    assert logs["landed"].time_unix_nano == ns(NOW + 0.25)
    assert logs["landed"].body.string_value == "landed"
    assert plain(logs["landed"])["gphoto.job"] == "incoming"
    assert logs["chrome_down"].time_unix_nano == ns(NOW + 7.5)
    assert plain(logs["chrome_down"]) == {"gphoto.kind": "chrome_down", "gphoto.job": "google"}
    assert abs(logs["landed"].observed_time_unix_nano - time.time_ns()) < 60e9


ERRORS = {"failed", "nas_down", "pass_error", "chrome_down", "signed_out", "folder_lost", "search_broken"}
WARNINGS = {"look", "retrying", "reloaded"}
INFOS = {
    "landed", "scrubbed", "sent", "skipped", "gone", "changed", "retry", "dismiss", "seen",
    "tidied", "nas_up", "pass_ok", "started", "chrome_up", "signed_in", "folder_ok",
    "search_ok", "something new",
}


def test_severity_follows_the_kind(on, state, receiver):
    on()
    for kind in sorted(ERRORS | WARNINGS | INFOS):
        state.add("incoming", kind, NOW)
    wait_for(lambda: len(receiver.logs()) == len(ERRORS | WARNINGS | INFOS))
    for record in receiver.logs():
        kind = plain(record)["gphoto.kind"]
        expected = (9, "INFO")
        if kind in ERRORS:
            expected = (17, "ERROR")
        elif kind in WARNINGS:
            expected = (13, "WARN")
        assert (record.severity_number, record.severity_text) == expected, kind


def test_many_rows_arrive_in_order_and_once(on, state, receiver):
    on()
    with contextlib.closing(state.db("incoming")) as db, db:
        db.executemany(
            "INSERT INTO events (at, kind, path) VALUES (?, 'landed', ?)",
            [(NOW + i, f"{FOLDER}/{i}.JPG") for i in range(1000)],
        )
    wait_for(lambda: len(receiver.logs()) >= 1000, 20)
    settle()
    assert [r.time_unix_nano for r in receiver.logs()] == [ns(NOW + i) for i in range(1000)]


def test_a_second_start_sends_nothing_again(on, state, receiver):
    first = on()
    state.add("incoming", "started", NOW)
    wait_for(lambda: receiver.logs())
    first.stop()
    on()
    state.add("incoming", "pass_ok", NOW + 1)
    wait_for(lambda: len(receiver.logs()) >= 2)
    settle()
    assert kinds(receiver) == ["started", "pass_ok"]


def test_what_was_written_just_before_the_stop_is_sent(on, state, receiver, monkeypatch):
    monkeypatch.setattr(otel, "POLL", 60)
    exporter = on()
    state.add("incoming", "nas_down", NOW)
    exporter.stop()
    assert kinds(receiver) == ["nas_down"]


def test_a_database_that_appears_later_sends_only_what_is_new(on, state, receiver, caplog):
    (state.folder / "google.db").unlink()
    on()
    settle(0.3)
    now = time.time()
    state.replace(
        "google",
        [(now - 5000, "signed_out", None), (now + 1, "signed_in", None),
         (now - 9000, "landed", PHOTO), (now + 2, "folder_ok", None)],
    )
    wait_for(lambda: len(receiver.logs()) >= 3)
    settle()
    # A landing carries the time of the file, which is before the row was written.
    assert kinds(receiver) == ["signed_in", "landed", "folder_ok"]
    assert not lines(caplog)


def test_a_database_without_the_table_is_survived(on, state, receiver):
    (state.folder / "google.db").unlink()
    sqlite3.connect(state.folder / "google.db").close()
    on()
    state.add("incoming", "started", NOW)
    wait_for(lambda: receiver.logs())
    state.add("google", "chrome_up", time.time() + 1)
    wait_for(lambda: len(receiver.logs()) == 2)


def test_a_broken_database_does_not_stop_the_other(on, state, receiver):
    (state.folder / "google.db").write_bytes(b"not a database" * 100)
    on()
    state.add("incoming", "started", NOW)
    wait_for(lambda: receiver.logs())


def test_a_broken_incoming_database_does_not_hold_back_google_for_ever(on, state, receiver):
    (state.folder / "incoming.db").write_bytes(b"not a database" * 100)
    on()
    state.add("google", "chrome_down", NOW)
    state.add("google", "seen", NOW + 1, PHOTO)
    wait_for(lambda: len(receiver.logs()) == 2)
    assert not any(r.trace_id for r in receiver.logs())


def test_a_locked_database_is_waited_for(on, state, receiver):
    on()
    with contextlib.closing(state.db("incoming")) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        lock.execute("INSERT INTO events (at, kind) VALUES (?, 'pass_error')", (NOW,))
        settle(1.5)
        assert not receiver.logs()
        lock.commit()
    wait_for(lambda: receiver.logs())
    settle()
    assert kinds(receiver) == ["pass_error"]


def test_locked_at_the_start_still_sends_only_what_is_new(on, state, receiver):
    state.add("incoming", "nas_down", time.time() - 100)
    with contextlib.closing(state.db("incoming")) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        on()
        lock.rollback()
    state.add("incoming", "nas_up", time.time() + 1)
    wait_for(lambda: receiver.logs())
    settle()
    assert kinds(receiver) == ["nas_up"]


def test_a_restored_database_is_not_sent_again(on, state, receiver):
    start = time.time()
    on()
    for i in range(5):
        state.add("incoming", "pass_ok", start + i)
    wait_for(lambda: len(receiver.logs()) == 5)
    # A backup from earlier takes its place, then something new happens.
    state.replace(
        "incoming",
        [(start, "pass_ok", None), (start + 1, "pass_ok", None), (start + 60, "started", None)],
    )
    wait_for(lambda: len(receiver.logs()) >= 6)
    settle()
    assert kinds(receiver)[5:] == ["started"]


def test_pruning_old_rows_changes_nothing(on, state, receiver):
    on()
    state.add("incoming", "pass_error", NOW)
    wait_for(lambda: receiver.logs())
    with contextlib.closing(state.db("incoming")) as db, db:
        db.execute("DELETE FROM events")
    settle(0.3)
    state.add("incoming", "pass_ok", NOW + 1)
    wait_for(lambda: len(receiver.logs()) == 2)
    settle()
    assert kinds(receiver) == ["pass_error", "pass_ok"]


def test_one_unusable_row_does_not_stop_the_rest(on, state, receiver):
    on()
    state.add("incoming", "started", "yesterday")
    state.add("incoming", "started", -5.0)
    state.add("incoming", "started", 1e300)
    state.add("incoming", b"\xff\xfe", NOW, b"\xff")
    state.add("incoming", "pass_ok", NOW + 1)
    wait_for(lambda: "pass_ok" in kinds(receiver))


def test_the_databases_are_never_written(on, state, receiver):
    for job in ("incoming", "google"):
        state.add(job, "started", NOW)
    before = {p.name: p.read_bytes() for p in state.folder.iterdir()}
    exporter = on()
    settle()
    exporter.stop()
    assert {p.name: p.read_bytes() for p in state.folder.iterdir()} == before


# --- traces --------------------------------------------------------------------------------


def whole_life(state, path=PHOTO, at=NOW):
    state.add("incoming", "landed", at, path)
    state.add("incoming", "scrubbed", at + 14400, path)
    state.add("incoming", "sent", at + 14401.5, path)
    state.add("google", "seen", at + 15000, path)


def by_name(spans):
    found = {s.name: s for s in spans}
    assert len(found) == len(spans)
    return found


def times(span):
    return span.start_time_unix_nano, span.end_time_unix_nano


def test_a_photo_is_one_trace_with_real_times(on, state, receiver):
    on()
    whole_life(state)
    wait_for(lambda: len(receiver.spans()) >= 4)
    settle()
    spans = by_name(receiver.spans())
    assert set(spans) == {"photo", "wait", "scrub", "upload"}
    assert times(spans["photo"]) == (ns(NOW), ns(NOW + 15000))
    assert times(spans["wait"]) == (ns(NOW), ns(NOW + 14400))
    assert times(spans["scrub"]) == (ns(NOW + 14400), ns(NOW + 14401.5))
    assert times(spans["upload"]) == (ns(NOW + 14401.5), ns(NOW + 15000))
    assert spans["photo"].parent_span_id == b""
    assert len({s.span_id for s in spans.values()}) == 4
    assert len({s.trace_id for s in spans.values()}) == 1
    for name in ("wait", "scrub", "upload"):
        assert spans[name].parent_span_id == spans["photo"].span_id
    assert "gphoto.missing" not in plain(spans["photo"])


def test_the_logs_of_a_photo_carry_its_trace(on, state, receiver):
    on()
    state.add("incoming", "landed", NOW, PHOTO)
    wait_for(lambda: len(receiver.logs()) == 1)  # long before there is a trace
    state.add("incoming", "landed", NOW, f"{FOLDER}/OTHER.JPG")
    state.add("incoming", "nas_down", NOW + 1)
    state.add("incoming", "sent", NOW + 5, PHOTO)
    state.add("google", "seen", NOW + 9, PHOTO)
    state.add("google", "tidied", NOW + 99, PHOTO)
    wait_for(lambda: len(receiver.logs()) == 6 and receiver.spans())
    root = by_name(receiver.spans())["photo"]
    photo = [r for r in receiver.logs() if plain(r).get("gphoto.photo") == otel.photo_id(PHOTO)]
    assert {plain(r)["gphoto.kind"] for r in photo} == {"landed", "sent", "seen", "tidied"}
    for record in photo:
        assert record.trace_id == root.trace_id
        assert record.span_id == root.span_id
    others = {plain(r)["gphoto.kind"]: r for r in receiver.logs() if r not in photo}
    assert others["nas_down"].trace_id == b""
    assert others["landed"].trace_id not in (b"", root.trace_id)


def test_the_trace_id_comes_from_the_path_and_the_landing(on, state, receiver):
    on()
    whole_life(state)
    wait_for(lambda: len(receiver.spans()) == 4)
    text = f"{PHOTO}\0{ns(NOW)}".encode()
    assert receiver.spans()[0].trace_id == hashlib.sha256(text).digest()[:16]


def test_a_photo_that_needs_no_scrub(on, state, receiver):
    on()
    state.add("incoming", "landed", NOW, PHOTO)
    state.add("incoming", "sent", NOW + 5, PHOTO)
    state.add("google", "seen", NOW + 9, PHOTO)
    wait_for(lambda: receiver.spans())
    spans = by_name(receiver.spans())
    assert set(spans) == {"photo", "wait", "upload"}
    assert times(spans["wait"]) == (ns(NOW), ns(NOW + 5))
    assert "gphoto.missing" not in plain(spans["photo"])


def test_a_photo_that_was_tried_twice(on, state, receiver):
    on()
    for kind, after in (
        ("landed", 0), ("scrubbed", 10), ("sent", 11), ("retry", 100), ("scrubbed", 110),
        ("failed", 111), ("retry", 200), ("scrubbed", 210), ("sent", 212),
    ):
        state.add("incoming", kind, NOW + after, PHOTO)
    state.add("google", "seen", NOW + 300, PHOTO)
    wait_for(lambda: receiver.spans())
    spans = by_name(receiver.spans())
    assert times(spans["photo"]) == (ns(NOW), ns(NOW + 300))
    assert times(spans["wait"]) == (ns(NOW), ns(NOW + 10))
    assert times(spans["scrub"]) == (ns(NOW + 210), ns(NOW + 212))
    assert times(spans["upload"]) == (ns(NOW + 212), ns(NOW + 300))


def test_a_scrub_before_an_earlier_send_is_not_the_scrub_of_the_last(on, state, receiver):
    on()
    for kind, after in (("landed", 0), ("scrubbed", 10), ("sent", 11), ("sent", 50)):
        state.add("incoming", kind, NOW + after, PHOTO)
    state.add("google", "seen", NOW + 60, PHOTO)
    wait_for(lambda: receiver.spans())
    assert set(by_name(receiver.spans())) == {"photo", "wait", "upload"}


@pytest.mark.parametrize(
    "have, spans, missing",
    [
        (("landed",), {"photo"}, ["sent"]),
        (("landed", "scrubbed"), {"photo", "wait"}, ["sent"]),
        (("scrubbed", "sent"), {"photo", "scrub", "upload"}, ["landed"]),
        (("sent",), {"photo", "upload"}, ["landed"]),
        (("look",), {"photo"}, ["landed", "sent"]),
        ((), set(), []),
    ],
)
def test_missing_events_give_the_spans_they_can(on, state, receiver, have, spans, missing):
    on()
    for i, kind in enumerate(have):
        state.add("incoming", kind, NOW + i, PHOTO)
    state.add("google", "seen", NOW + 100, PHOTO)
    state.add("google", "search_ok", NOW + 101)
    wait_for(lambda: len(receiver.logs()) == len(have) + 2)
    settle()
    found = by_name(receiver.spans())
    assert set(found) == spans
    if found:
        (value,) = [a.value for a in found["photo"].attributes if a.key == "gphoto.missing"]
        assert [v.string_value for v in value.array_value.values] == missing
        assert found["photo"].end_time_unix_nano == ns(NOW + 100)
    # The logs agree with whatever trace there is.
    ids = {r.trace_id for r in receiver.logs() if "gphoto.photo" in plain(r)}
    assert ids == ({found["photo"].trace_id} if found else {b""})


def test_times_that_go_backwards_give_no_negative_span(on, state, receiver):
    on()
    state.add("incoming", "landed", NOW, PHOTO)
    state.add("incoming", "scrubbed", NOW + 20, PHOTO)
    state.add("incoming", "sent", NOW + 10, PHOTO)
    state.add("google", "seen", NOW + 30, PHOTO)
    wait_for(lambda: receiver.spans())
    for span in receiver.spans():
        assert span.end_time_unix_nano >= span.start_time_unix_nano
    assert "scrub" not in by_name(receiver.spans())


def test_seen_twice_is_one_trace(on, state, receiver):
    on()
    whole_life(state)
    wait_for(lambda: len(receiver.spans()) == 4)
    state.add("incoming", "retry", NOW + 16000, PHOTO)
    state.add("incoming", "sent", NOW + 16001, PHOTO)
    state.add("google", "seen", NOW + 17000, PHOTO)
    wait_for(lambda: len(receiver.logs()) == 7)
    settle()
    assert len(receiver.spans()) == 4


def test_seen_before_this_process_started_is_not_traced_again(on, state, receiver):
    whole_life(state)
    on()
    state.add("google", "seen", NOW + 20000, PHOTO)
    wait_for(lambda: receiver.logs())
    settle()
    assert not receiver.spans()


def test_the_same_name_landing_again_is_a_new_trace(on, state, receiver):
    on()
    whole_life(state)
    whole_life(state, at=NOW + 50000)
    wait_for(lambda: len(receiver.spans()) == 8)
    roots = [s for s in receiver.spans() if s.name == "photo"]
    assert {times(s) for s in roots} == {
        (ns(NOW), ns(NOW + 15000)), (ns(NOW + 50000), ns(NOW + 65000))
    }
    assert len({s.trace_id for s in roots}) == 2


def test_a_photo_that_landed_before_the_start_still_gets_its_whole_trace(on, state, receiver):
    state.add("incoming", "landed", NOW, PHOTO)
    state.add("incoming", "sent", NOW + 5, PHOTO)
    on()
    state.add("google", "seen", NOW + 9, PHOTO)
    wait_for(lambda: receiver.spans())
    assert set(by_name(receiver.spans())) == {"photo", "wait", "upload"}


@pytest.mark.slow
def test_a_lock_on_incoming_delays_the_trace_and_does_not_lose_it(
    on, state, receiver, monkeypatch
):
    monkeypatch.setattr(otel, "PATIENCE", 1000)
    state.add("incoming", "landed", NOW, PHOTO)
    state.add("incoming", "sent", NOW + 5, PHOTO)
    on()
    with contextlib.closing(state.db("incoming")) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        state.add("google", "seen", NOW + 9, PHOTO)
        settle(3)
        assert not receiver.spans()
        lock.rollback()
    wait_for(lambda: len(receiver.spans()) == 3)
    settle()
    (record,) = receiver.logs()
    assert record.trace_id == receiver.spans()[0].trace_id


def test_the_sdks_own_sampler_setting_works(monkeypatch, on, state, receiver):
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_off")
    on()
    whole_life(state)
    wait_for(lambda: len(receiver.logs()) == 4)
    settle()
    assert not receiver.spans()


# --- privacy -----------------------------------------------------------------------------------


def everything(receiver):
    return b"".join(body for _, _, body in receiver.requests)


def tell_all(state):
    state.metrics("incoming", {"gphoto.waiting": gauge(1, path=PHOTO, outcome="sent")})
    whole_life(state)
    state.add("incoming", "failed", NOW + 1, PHOTO, f"cannot read /photos/{PHOTO}")
    state.add("incoming", "pass_error", NOW + 2, None, f"1 not read, first: {FOLDER}")


def test_no_folder_or_file_name_leaves_by_default(on, state, receiver):
    on()
    tell_all(state)
    wait_for(lambda: len(receiver.logs()) == 6 and len(receiver.spans()) == 4)
    receiver.metrics(2)
    sent = everything(receiver)
    for secret in (b"Secret", b"birthday", b"DSC_1", b"not read", b"cannot"):
        assert secret not in sent
    photo = otel.photo_id(PHOTO)
    assert 8 <= len(photo) <= 16
    assert photo != otel.photo_id(FOLDER)
    for item in [*receiver.spans(), *receiver.logs()]:
        attributes = plain(item)
        assert "gphoto.path" not in attributes and "gphoto.detail" not in attributes
        if attributes.get("gphoto.kind") != "pass_error":
            assert attributes["gphoto.photo"] == photo


@pytest.mark.parametrize(
    "value, shown",
    [("true", True), ("TRUE", True), ("false", False), ("1", False), ("", False)],
)
def test_paths_leave_only_when_asked_for(monkeypatch, on, state, receiver, value, shown):
    monkeypatch.setenv("OTEL_GPHOTO_PATHS", value)
    on()
    tell_all(state)
    wait_for(lambda: len(receiver.logs()) == 6 and len(receiver.spans()) == 4)
    assert (b"Secret birthday" in everything(receiver)) is shown
    if shown:
        assert {plain(s)["gphoto.path"] for s in receiver.spans()} == {PHOTO}
        logs = {plain(r)["gphoto.kind"]: plain(r) for r in receiver.logs()}
        assert logs["failed"]["gphoto.path"] == PHOTO
        assert logs["failed"]["gphoto.detail"] == f"cannot read /photos/{PHOTO}"
        assert "gphoto.photo" not in logs["failed"]


# --- when the receiver is not there ---------------------------------------------------------------


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def page_works(state):
    access = web.Access(team="https://t", audience="a", email="e", key_for=lambda _: "")
    with TestClient(web.create_app(state.folder, access, 0)) as client:
        began = time.monotonic()
        assert client.get("/healthz").status_code == 200
        assert client.get("/").status_code == 403
        return time.monotonic() - began


def stop_in_time(exporter):
    began = time.monotonic()
    exporter.stop()
    assert time.monotonic() - began < 5


@pytest.mark.slow
def test_refused_is_one_line_then_one_when_it_is_back(monkeypatch, run, state, caplog):
    caplog.set_level(logging.INFO)
    port = free_port()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.4")
    state.metrics("incoming", {"gphoto.waiting": gauge(1)})
    exporter = run()
    for i in range(6):
        whole_life(state, f"{FOLDER}/{i}.JPG")
        time.sleep(0.8)
    assert page_works(state) < 1
    (record,) = lines(caplog)
    assert "gphoto" in record.name

    receiver = Receiver(port)
    try:
        # Whole photos keep coming, so every signal gets its turn to work again.
        for i in range(20):
            whole_life(state, f"{FOLDER}/back{i}.JPG")
            time.sleep(0.2)
        wait_for(lambda: receiver.logs() and receiver.spans())
        wait_for(lambda: any("again" in r.getMessage() for r in lines(caplog, logging.INFO)))
        stop_in_time(exporter)
    finally:
        receiver.close()
    assert len(lines(caplog)) == 1
    assert sum("again" in r.getMessage() for r in lines(caplog, logging.INFO)) == 1


@pytest.mark.slow
def test_refused_stops_in_time(monkeypatch, run, state, caplog):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{free_port()}")
    state.metrics("incoming", {"gphoto.waiting": gauge(1)})
    exporter = run()  # with the standard timeout of 10 seconds
    whole_life(state)
    settle(1.0)
    stop_in_time(exporter)
    assert len(lines(caplog)) <= 1


@pytest.mark.slow
def test_hanging_holds_up_neither_the_page_nor_the_stop(monkeypatch, run, state, caplog):
    receiver = Receiver(hang=True)
    try:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", receiver.url)
        state.metrics("incoming", {"gphoto.waiting": gauge(1)})
        exporter = run()
        whole_life(state)
        settle(1.0)
        assert page_works(state) < 1
        stop_in_time(exporter)
        began = time.monotonic()
        exporter.stop()  # a second stop is nothing
        assert time.monotonic() - began < 0.5
    finally:
        receiver.close()
    assert len(lines(caplog)) <= 1


@pytest.mark.slow
def test_hanging_is_one_line_and_is_given_up_on(monkeypatch, run, state, caplog):
    receiver = Receiver(hang=True)
    try:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", receiver.url)
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.3")
        state.metrics("incoming", {"gphoto.waiting": gauge(1)})
        exporter = run()
        for i in range(5):
            whole_life(state, f"{FOLDER}/{i}.JPG")
            time.sleep(0.6)
        (record,) = lines(caplog)
        assert "timed out" in record.getMessage()
        receiver.released.set()
        state.add("incoming", "nas_up", NOW + 99)
        wait_for(lambda: "nas_up" in kinds(receiver))
        stop_in_time(exporter)
    finally:
        receiver.close()


@pytest.mark.slow
@pytest.mark.parametrize("status", [400, 401, 404, 500, 503])
def test_an_unhappy_receiver_is_one_line(monkeypatch, run, state, caplog, status):
    receiver = Receiver(status=status)
    try:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", receiver.url)
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.4")
        state.metrics("incoming", {"gphoto.waiting": gauge(1)})
        exporter = run()
        for i in range(3):
            whole_life(state, f"{FOLDER}/{i}.JPG")
            time.sleep(0.6)
        stop_in_time(exporter)
    finally:
        receiver.close()
    (record,) = lines(caplog)
    assert str(status) in record.getMessage()


@pytest.mark.slow
def test_a_tls_error_is_one_line(monkeypatch, run, state, caplog):
    receiver = Receiver()
    try:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"https://127.0.0.1:{receiver.port}")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.5")
        exporter = run()
        for i in range(3):
            whole_life(state, f"{FOLDER}/{i}.JPG")
            time.sleep(0.6)
        assert page_works(state) < 1
        stop_in_time(exporter)
    finally:
        receiver.close()
    (record,) = lines(caplog)
    assert "SSL" in record.getMessage()


@pytest.mark.parametrize("endpoint", ["not a url", "ftp://127.0.0.1", "http://[::1"])
def test_a_wrong_endpoint_is_not_a_crash(monkeypatch, run, state, caplog, endpoint):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)
    exporter = run()
    whole_life(state)
    settle(1.0)
    if exporter:
        stop_in_time(exporter)
    assert len(lines(caplog)) == 1


@pytest.mark.parametrize("interval", ["0", "-5", "soon", "nan"])
def test_a_wrong_interval_leaves_the_rest_working(monkeypatch, on, state, receiver, interval):
    monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", interval)
    on()
    state.add("incoming", "started", NOW)
    wait_for(lambda: receiver.logs())


@pytest.mark.slow
def test_queues_stay_small_and_quiet_in_a_long_outage(monkeypatch, run, state, caplog):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{free_port()}")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
    monkeypatch.setenv("OTEL_BLRP_MAX_QUEUE_SIZE", "20")
    monkeypatch.setenv("OTEL_BLRP_MAX_EXPORT_BATCH_SIZE", "10")
    exporter = run()
    threads = threading.active_count()
    with contextlib.closing(state.db("incoming")) as db, db:
        db.executemany(
            "INSERT INTO events (at, kind) VALUES (?, 'pass_ok')", [(NOW + i,) for i in range(900)]
        )
    settle(3)
    assert threading.active_count() <= threads
    stop_in_time(exporter)
    assert len(lines(caplog)) <= 1
    assert "Queue full" not in caplog.text


def test_a_secret_header_is_never_logged(monkeypatch, run, state, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{free_port()}")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.3")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_HEADERS", "x-key=hush%0Ahush,: hushhush,authorization=Bearer hushhush"
    )
    exporter = run()
    whole_life(state)
    settle(1.0)
    exporter.stop()
    assert lines(caplog) and "hush" not in caplog.text


def test_stopping_leaves_no_threads_behind(on, receiver):
    before = {t.ident for t in threading.enumerate()}
    exporter = on()
    receiver.metrics()
    stop_in_time(exporter)
    wait_for(
        lambda: not [
            t for t in threading.enumerate()
            if t.ident not in before and (t.name.startswith("Otel") or "gphoto" in t.name)
        ]
    )
