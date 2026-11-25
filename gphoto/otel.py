"""Send metrics, logs and traces to an OTLP endpoint, if the environment names one.

Runs inside the status page process, the only one with a network. It reads the two
databases and the two metrics files the other processes write, and writes nothing.
The standard OTEL_ variables set it up. Without an endpoint no thread is started and
the OpenTelemetry packages are not imported.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
import os
import sqlite3
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from gphoto.status import CHECK_STALE, CLOCK_SLACK, PASS_STALE

if TYPE_CHECKING:
    import requests
    from opentelemetry.context import Context
    from opentelemetry.metrics import CallbackOptions, Observation
    from opentelemetry.sdk.metrics.export import Metric, MetricsData, ScopeMetrics
    from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

SIGNALS = ("traces", "metrics", "logs")
PROTOCOL = "http/protobuf"
JOBS = ("incoming", "google")
# The page calls a process stopped after the same time.
STALE = {"incoming": PASS_STALE, "google": CHECK_STALE}

ERRORS = {"failed", "nas_down", "pass_error", "chrome_down", "signed_out", "folder_lost", "search_broken"}
WARNINGS = {"look", "retrying", "reloaded"}

POLL = 5.0
# Rows read at a time. The database is the queue, so that the SDK's own stays small.
BATCH = 200
# Polls to wait for a locked incoming.db before sending without trace ids.
PATIENCE = 12
# Short, because the next poll tries again and a stop may be waiting for this one.
BUSY_SECONDS = 0.1
POLLER_SECONDS = 1.5
STOP_SECONDS = 4.0


def start(state_dir: Path | str) -> Exporter | None:
    """Start sending, or return None if the environment does not ask for it."""
    signals = _wanted()
    if not signals:
        return None
    try:
        return Exporter(Path(state_dir), signals)
    except Exception:
        logger.exception("OpenTelemetry could not start")
        return None


def photo_id(path: str) -> str:
    """Says which photo without saying what its folder is called."""
    return hashlib.sha256(path.encode()).hexdigest()[:12]


def _setting(*names: str) -> tuple[str, str]:
    """The first of these variables that is set, and its value."""
    for name in names:
        if value := os.getenv(name, "").strip():
            return name, value
    return names[-1], ""


def _wanted() -> list[str]:
    """The signals to send. Decided here because the SDK would have to be imported to ask it."""
    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return []
    wanted, refused = [], []
    for signal in SIGNALS:
        upper = signal.upper()
        # A signal without an endpoint would go to localhost, where nobody asked for it.
        if not _setting(f"OTEL_EXPORTER_OTLP_{upper}_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")[1]:
            continue
        name, value = _setting(f"OTEL_{upper}_EXPORTER")
        exporters = [e.strip().lower() for e in (value or "otlp").split(",")]
        if exporters == ["none"]:
            continue
        if not {"otlp", "otlp_proto_http"} & set(exporters):
            refused.append(f"{name}={value}")
            continue
        name, value = _setting(
            f"OTEL_EXPORTER_OTLP_{upper}_PROTOCOL", "OTEL_EXPORTER_OTLP_PROTOCOL"
        )
        if value not in ("", PROTOCOL):
            refused.append(f"{name}={value}")
            continue
        wanted.append(signal)
    if refused:
        logger.error(
            "OpenTelemetry export is off for: %s. Only otlp over %s is supported.",
            ", ".join(dict.fromkeys(refused)), PROTOCOL,
        )
    return wanted


# --- checked values --------------------------------------------------------------------
# One value that cannot be encoded would lose everything sent in the same request.


def _number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("not a number")
    if not math.isfinite(value) or not -(2**63) <= value < 2**63:
        raise ValueError("number out of range")
    return value


def _count(value: Any) -> int:
    if not isinstance(_number(value), int) or value < 0:
        raise ValueError("not a count")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("not text")
    value.encode()
    return value


def _ns(seconds: Any) -> int:
    """Nanoseconds. Rounded, because a float of today's date is not exact to the last digits."""
    value = round(_number(seconds) * 1_000_000) * 1000
    if not 0 <= value < 2**63:
        raise ValueError("time out of range")
    return value


# --- metrics files -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Snapshot:
    at: float
    started: float
    version: str
    metrics: dict[str, Any]


class _MetricsFile:
    """The numbers one process saved at the end of its last pass."""

    def __init__(self, state: Path, job: str) -> None:
        self.job = job
        self._path = state / f"metrics-{job}.json"
        self._last_at: float | None = None

    def read(self, now: float) -> tuple[_Snapshot | None, float | None]:
        """What may be sent, and the age in seconds as far as it is known."""
        snapshot = self._load(now)
        if snapshot is not None:
            self._last_at = snapshot.at
            fresh = now - snapshot.at <= STALE[self.job] and snapshot.started <= snapshot.at
            return snapshot if fresh else None, max(0.0, now - snapshot.at)
        written = self._last_at
        with contextlib.suppress(OSError):
            written = self._path.stat().st_mtime
        return None, None if written is None else max(0.0, now - written)

    def _load(self, now: float) -> _Snapshot | None:
        try:
            saved = json.loads(self._path.read_text(encoding="utf-8"))
            snapshot = _Snapshot(
                at=float(_number(saved["at"])), started=float(_number(saved["started"])),
                version=_text(saved.get("version", "")), metrics=saved["metrics"],
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            return None
        sound = isinstance(snapshot.metrics, dict) and snapshot.started >= 0
        return snapshot if sound and 0 < snapshot.at <= now + CLOCK_SLACK else None


def _metric(job: str, name: str, saved: dict[str, Any], start: int, at: int, paths: bool) -> Metric:
    """One saved metric as the SDK would have collected it. ValueError if it makes no sense.

    'at' is when the process measured it. Sent as the time now, the last count of a
    process that was restarted would overlap the first of the new one.
    """
    from opentelemetry.sdk.metrics import export as sdk

    def attributes(point: dict[str, Any]) -> dict[str, str | bool | int | float]:
        found: dict[str, str | bool | int | float] = {"gphoto.job": job}
        for key, value in point.get("attributes", {}).items():
            keep = value if isinstance(value, bool) else (
                _text(value) if isinstance(value, str) else _number(value))
            found[_text(key)] = keep
        return found

    kind, points = saved["type"], saved["points"]
    if not paths:
        points = [p for p in points if not {"path", "gphoto.path"} & set(p.get("attributes", {}))]
    cumulative = sdk.AggregationTemporality.CUMULATIVE
    data: sdk.Gauge | sdk.Sum | sdk.Histogram
    if kind == "gauge":
        data = sdk.Gauge(
            [sdk.NumberDataPoint(attributes(p), 0, at, _number(p["value"])) for p in points]
        )
    elif kind == "counter":
        if any(_number(p["value"]) < 0 for p in points):
            raise ValueError("a counter below zero")
        data = sdk.Sum(
            [sdk.NumberDataPoint(attributes(p), start, at, p["value"]) for p in points],
            cumulative, is_monotonic=True,
        )
    elif kind == "histogram":
        data = sdk.Histogram([_histogram(p, attributes(p), start, at) for p in points], cumulative)
    else:
        raise ValueError("unknown type")
    return sdk.Metric(_text(name), _text(saved.get("help", "")), _text(saved.get("unit", "")), data)


def _histogram(point: dict[str, Any], attributes: dict[str, Any], start: int, at: int) -> Any:
    from opentelemetry.sdk.metrics.export import HistogramDataPoint

    count = _count(point["count"])
    bounds = [float(_number(b)) for b in point["bounds"]]
    buckets = [_count(b) for b in point["buckets"]]
    if len(buckets) != len(bounds) + 1 or sum(buckets) != count:
        raise ValueError("buckets do not add up")
    if any(low >= high for low, high in zip(bounds, bounds[1:], strict=False)):
        raise ValueError("bounds out of order")
    low, high = point.get("min"), point.get("max")
    return HistogramDataPoint(
        attributes, start, at, count=count, sum=_number(point["sum"]),
        bucket_counts=buckets, explicit_bounds=bounds,
        # Nothing has been measured yet, so there is no smallest and no largest.
        min=None if low is None else _number(low),  # type: ignore[arg-type]
        max=None if high is None else _number(high),  # type: ignore[arg-type]
    )


# --- events --------------------------------------------------------------------------------


class _Event(NamedTuple):
    id: int
    at: float
    kind: str
    path: str | None
    detail: str | None = None


class _Events:
    """The events of one database, from now on. The place is kept in memory only."""

    def __init__(self, state: Path, job: str) -> None:
        self.job = job
        self._uri = f"{(state / f'{job}.db').absolute().as_uri()}?mode=ro"
        self._since = time.time()
        self._after: int | None = None
        with contextlib.suppress(sqlite3.Error), contextlib.closing(self._connect()) as db:
            self._after = self._top(db)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self._uri, uri=True, timeout=BUSY_SECONDS)
        db.text_factory = lambda raw: raw.decode("utf-8", "replace")
        return db

    @staticmethod
    def _top(db: sqlite3.Connection) -> int:
        """The newest id ever given out. Unlike MAX(id) it stays when old rows are deleted."""
        row = db.execute("SELECT seq FROM sqlite_sequence WHERE name = 'events'").fetchone()
        return row[0] if row else 0

    def new(self) -> list[_Event]:
        with contextlib.closing(self._connect()) as db:
            if self._after is None or self._top(db) < self._after:
                # Not readable at the start, or another database was put in its place.
                # A landing is left out because it carries the time of the file.
                self._after = db.execute(
                    "SELECT COALESCE(MAX(id), 0) FROM events WHERE at <= ? AND kind <> 'landed'",
                    (self._since,),
                ).fetchone()[0]
            rows = db.execute(
                "SELECT id, at, kind, path, detail FROM events WHERE id > ? ORDER BY id LIMIT ?",
                (self._after, BATCH),
            )
            return [_Event(*row) for row in rows]

    def passed(self, event: _Event) -> None:
        """Never read this one again, whatever becomes of it."""
        self._after = event.id
        with contextlib.suppress(ValueError):
            if event.kind != "landed" and _number(event.at) <= time.time() + CLOCK_SLACK:
                self._since = max(self._since, event.at)

    def about(self, paths: Iterable[str]) -> dict[str, list[_Event]]:
        """Everything recorded about these photos, oldest first."""
        wanted = list(paths)
        found: dict[str, list[_Event]] = defaultdict(list)
        if wanted:
            marks = ",".join("?" * len(wanted))
            with contextlib.closing(self._connect()) as db:
                rows = db.execute(
                    f"SELECT id, at, kind, path FROM events WHERE path IN ({marks}) ORDER BY id",
                    wanted,
                )
                for event in map(_Event._make, ((*row, None) for row in rows)):
                    with contextlib.suppress(ValueError):
                        _ns(event.at)
                        found[str(event.path)].append(event)
        return found


def _beginning(life: Sequence[_Event], at: float) -> _Event | None:
    """Where the story of a photo begins: its last landing, or failing that its first event.

    Logs and spans both ask here, so they agree on the trace even if the landing is missing.
    """
    landings = [e for e in life if e.kind == "landed" and e.at <= at]
    if landings:
        return landings[-1]
    return life[0] if life else None


class _Ids(NamedTuple):
    trace: int
    root: int

    @classmethod
    def of(cls, path: str, landed: float) -> _Ids:
        """Worked out, not drawn, so a log sent hours before its trace already has the id."""
        digest = hashlib.sha256(f"{path}\0{_ns(landed)}".encode()).digest()
        return cls(int.from_bytes(digest[:16]), int.from_bytes(digest[16:24]))

    def child(self, name: str) -> int:
        digest = hashlib.sha256(f"{self.trace:032x}{name}".encode()).digest()
        return int.from_bytes(digest[:8])


# --- when sending fails ----------------------------------------------------------------------

_heard = threading.local()


class _Hush(logging.Filter):
    """The SDK logs every attempt. The outage is logged once here instead."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(_heard, "reason", None):
            # Not a network fault, or the session below would have noted it.
            errors = [a for a in record.args or () if isinstance(a, Exception)]
            _heard.reason = type(errors[0]).__name__ if errors else record.msg.split("%")[0]
        return False


class _HushQueue(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not record.msg.startswith("Queue full")


class _HideHeader(logging.Filter):
    """The SDK prints a header it cannot read, and headers hold passwords."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = ("(not shown)",)
        return True


_FILTERS: tuple[tuple[str, logging.Filter], ...] = (
    ("opentelemetry.exporter.otlp.proto.http.trace_exporter", _Hush()),
    ("opentelemetry.exporter.otlp.proto.http.metric_exporter", _Hush()),
    ("opentelemetry.exporter.otlp.proto.http._log_exporter", _Hush()),
    ("opentelemetry.sdk._shared_internal", _HushQueue()),
    ("opentelemetry.util.re", _HideHeader()),
)


def _add_filters() -> None:
    for name, wanted in _FILTERS:
        filters = logging.getLogger(name).filters
        if wanted not in filters:
            filters.insert(0, wanted)  # before the SDK's own, which would hide some from it


def _session() -> requests.Session:
    """Notes why a request failed. The SDK's exporters only say that it did."""
    import requests

    class Session(requests.Session):
        def request(self, *args: Any, **kwargs: Any) -> requests.Response:
            try:
                response = super().request(*args, **kwargs)
            except Exception as error:
                _heard.reason = _describe(error)
                raise
            _heard.reason = None if response.status_code < 400 else f"HTTP {response.status_code}"
            return response

    return Session()


def _describe(error: Exception) -> str:
    """The innermost cause. Other errors give only their name: their text can quote a header."""
    import requests

    if not isinstance(error, requests.ConnectionError | requests.Timeout):
        return type(error).__name__
    cause: Any = error
    while True:
        inner = getattr(cause, "reason", None)
        if not isinstance(inner, Exception):
            inner = cause.args[0] if cause.args else None
        if not isinstance(inner, Exception):
            return f"{type(error).__name__}: {cause}"
        cause = inner


class _Outage:
    """One line when sending stops working and one when it works again."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._down: dict[str, str] = {}
        self._closed = False

    def watch(self, signal: str, export: Callable[..., Any], failure: Any) -> Callable[..., Any]:
        def watched(*args: Any, **kwargs: Any) -> Any:
            _heard.reason = None
            try:
                result = export(*args, **kwargs)
            except Exception as error:
                _heard.reason, result = type(error).__name__, failure
            if result is failure:
                self._failed(signal, _heard.reason or "no reason given")
            else:
                self._worked(signal)
            return result

        return watched

    def _failed(self, signal: str, reason: str) -> None:
        # A server that answers with an error is another fault than one that does not answer.
        fault = reason if reason.startswith("HTTP ") else "unreachable"
        with self._lock:
            known = self._closed or fault in self._down.values()
            self._down[signal] = fault
        if not known:
            logger.warning(
                "OpenTelemetry cannot send %s: %s. Photos are not affected. What happens"
                " meanwhile may not be sent.", signal, reason,
            )

    def _worked(self, signal: str) -> None:
        with self._lock:
            was_down = self._down.pop(signal, None)
            over = was_down is not None and not self._down and not self._closed
        if over:
            logger.info("OpenTelemetry is sending again")

    def close(self) -> None:
        with self._lock:
            self._closed = True


# --- the exporter --------------------------------------------------------------------------------


class Exporter:
    """Made by start(). Everything runs on background threads."""

    def __init__(self, state: Path, signals: Sequence[str]) -> None:
        self._paths = os.getenv("OTEL_GPHOTO_PATHS", "").strip().lower() == "true"
        self._files = [_MetricsFile(state, job) for job in JOBS]
        self._incoming = _Events(state, "incoming")
        self._google = _Events(state, "google")
        self._held = 0
        self._warned: set[str] = set()
        self._logger: Any = None
        self._tracer: Any = None
        self._outage = _Outage()
        self._stopping = threading.Event()
        self._stop_once = threading.Lock()
        self._closers: list[Callable[[], Any]] = []
        self._cutters: list[Callable[[], Any]] = []

        _add_filters()
        resource = _resource()
        begin = {
            "traces": self._begin_traces, "metrics": self._begin_metrics, "logs": self._begin_logs
        }
        working = []
        for signal in signals:
            try:
                begin[signal](resource)
                working.append(signal)
            except Exception as error:
                logger.error(
                    "OpenTelemetry cannot send %s: %s", signal, " ".join(str(error).split())
                )
        self._poller: threading.Thread | None = None
        if self._logger or self._tracer:
            self._poller = threading.Thread(target=self._run, name="gphoto-otel", daemon=True)
            self._poller.start()
        logger.info("OpenTelemetry is sending %s", ", ".join(working) or "nothing")

    # The providers are never made global. FastAPI would trace every request if they were.
    # They are not tied to the exit of the process either, because that waits 30 seconds.

    def _begin_traces(self, resource: Resource) -> None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExportResult
        from opentelemetry.sdk.trace.id_generator import IdGenerator

        class Given(IdGenerator):
            """Hands out what _span put here. Only the poller makes spans."""

            trace = span = 0

            def generate_trace_id(self) -> int:
                return self.trace

            def generate_span_id(self) -> int:
                return self.span

        exporter = OTLPSpanExporter(session=_session())
        self._watch("traces", exporter, SpanExportResult.FAILURE)
        self._given = Given()
        provider = TracerProvider(
            resource=resource, shutdown_on_exit=False, id_generator=self._given
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        self._closers.append(provider.shutdown)
        self._tracer = provider.get_tracer("gphoto")

    def _begin_logs(self, resource: Resource) -> None:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExportResult

        exporter = OTLPLogExporter(session=_session())
        self._watch("logs", exporter, LogRecordExportResult.FAILURE)
        provider = LoggerProvider(resource=resource, shutdown_on_exit=False)
        provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        self._closers.append(provider.shutdown)
        self._logger = provider.get_logger("gphoto")

    def _begin_metrics(self, resource: Resource) -> None:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            MetricExportResult,
            PeriodicExportingMetricReader,
        )

        add_files = self._add_files

        class Reader(PeriodicExportingMetricReader):
            """Adds the files to what the SDK collected. It has no MetricProducer in Python,
            and its instruments cannot replay a histogram."""

            def _receive_metrics(
                self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any
            ) -> None:
                super()._receive_metrics(add_files(metrics_data), timeout_millis, **kwargs)

        exporter = OTLPMetricExporter(session=_session())
        self._watch("metrics", exporter, MetricExportResult.FAILURE)
        provider = MeterProvider([Reader(exporter)], resource=resource, shutdown_on_exit=False)
        self._closers.append(provider.shutdown)
        meter = provider.get_meter("gphoto")
        meter.create_observable_gauge(
            "gphoto.metrics.age", [self._ages], "s", "Since the process saved its metrics"
        )
        meter.create_observable_gauge(
            "gphoto.metrics.usable", [self._usable], "1", "1 if its metrics can be sent"
        )

    def _watch(self, signal: str, exporter: Any, failure: Any) -> None:
        exporter.export = self._outage.watch(signal, exporter.export, failure)
        self._cutters.append(exporter.shutdown)

    def stop(self) -> None:
        """Send what is left if that is quick. Back within 5 seconds whatever happens."""
        if not self._stop_once.acquire(blocking=False):
            return
        deadline = time.monotonic() + STOP_SECONDS
        self._stopping.set()
        if self._poller:
            self._poller.join(POLLER_SECONDS)
        threads = [
            threading.Thread(target=self._quietly, args=(close,), name="gphoto-otel-stop",
                             daemon=True)
            for close in self._closers
        ]
        with contextlib.suppress(RuntimeError):  # no new threads while Python is exiting
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(max(0.0, deadline - time.monotonic()))
        self._outage.close()
        for cut in self._cutters:  # ends a retry that is waiting for its turn
            self._quietly(cut)

    @staticmethod
    def _quietly(act: Callable[[], Any]) -> None:
        try:
            act()
        except Exception:
            logger.debug("OpenTelemetry did not stop cleanly", exc_info=True)

    def _warn_once(self, what: str, error: Exception) -> None:
        if what not in self._warned:
            self._warned.add(what)
            logger.warning("OpenTelemetry leaves out %s: %s", what, type(error).__name__)

    # --- metrics ---

    def _ages(self, _: CallbackOptions) -> Iterable[Observation]:
        from opentelemetry.metrics import Observation

        for file in self._files:
            age = file.read(time.time())[1]
            if age is not None:
                yield Observation(age, {"gphoto.job": file.job})

    def _usable(self, _: CallbackOptions) -> Iterable[Observation]:
        from opentelemetry.metrics import Observation

        for file in self._files:
            snapshot = file.read(time.time())[0]
            yield Observation(int(snapshot is not None), {"gphoto.job": file.job})

    def _add_files(self, collected: MetricsData) -> MetricsData:
        try:
            scopes = [scope for file in self._files if (scope := self._scope(file))]
            first, *others = collected.resource_metrics
            joined = replace(first, scope_metrics=[*first.scope_metrics, *scopes])
            return replace(collected, resource_metrics=[joined, *others])
        except Exception as error:  # would end the SDK's thread
            self._warn_once("the metrics files", error)
            return collected

    def _scope(self, file: _MetricsFile) -> ScopeMetrics | None:
        from opentelemetry.sdk.metrics.export import ScopeMetrics
        from opentelemetry.sdk.util.instrumentation import InstrumentationScope

        snapshot, _ = file.read(time.time())
        if snapshot is None:
            return None
        start, at = _ns(snapshot.started), _ns(snapshot.at)
        metrics = []
        for name, saved in snapshot.metrics.items():
            try:
                metric = _metric(file.job, name, saved, start, at, self._paths)
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
                self._warn_once(f"{file.job} metric {name!r}", error)
                continue
            if metric.data.data_points:
                metrics.append(metric)
        # A scope of its own, because both processes use some of the same names.
        scope = InstrumentationScope(f"gphoto.{file.job}", snapshot.version)
        return ScopeMetrics(scope, metrics, "") if metrics else None

    # --- events ---

    def _run(self) -> None:
        while not self._stopping.wait(POLL):
            self._poll()
        self._poll()

    def _poll(self) -> None:
        for events in (self._incoming, self._google):
            try:
                self._send_new(events)
            except sqlite3.Error:
                pass  # missing or locked: the rows are still there at the next poll
            except Exception as error:
                self._warn_once(f"some {events.job} events", error)

    def _send_new(self, events: _Events) -> None:
        new = events.new()
        paths = {e.path for e in new if isinstance(e.path, str)}
        try:
            lives = self._incoming.about(paths)
            self._held = 0
        except sqlite3.Error:
            # Without it there are no trace ids, so wait a little, but not for ever.
            self._held += 1
            if self._held <= PATIENCE:
                return
            lives = {}
        seen = {e.path for e in new if e.kind == "seen" and isinstance(e.path, str)}
        sightings = events.about(seen) if self._tracer else {}
        for event in new:
            events.passed(event)
            try:
                self._send(events.job, event, lives, sightings)
            except Exception as error:
                self._warn_once(f"an {events.job} event", error)

    def _send(
        self, job: str, event: _Event, lives: dict[str, list[_Event]],
        sightings: dict[str, list[_Event]],
    ) -> None:
        at = _ns(event.at)
        kind = _text(event.kind)
        path = None if event.path is None else _text(event.path)
        life = lives.get(path, []) if path else []
        begins = _beginning(life, event.at)
        ids = _Ids.of(path, begins.at) if path and begins else None
        if self._logger:
            self._send_log(job, kind, at, path, event.detail, ids)
        if self._tracer and job == "google" and kind == "seen" and path and begins and ids:
            # Seen again after a retry. This trace has been sent, perhaps by an earlier process.
            before = [e for e in sightings.get(path, []) if e.kind == "seen" and e.id < event.id]
            if not any(e.at >= begins.at for e in before):
                self._send_trace(path, life, begins, event.at, ids)

    def _about(self, path: str | None) -> dict[str, Any]:
        """A path holds the names of family folders, so it leaves only if asked for."""
        if path is None:
            return {}
        return {"gphoto.path": path} if self._paths else {"gphoto.photo": photo_id(path)}

    def _send_log(
        self, job: str, kind: str, at: int, path: str | None, detail: Any, ids: _Ids | None
    ) -> None:
        from opentelemetry._logs import SeverityNumber

        severity = SeverityNumber.INFO
        if kind in ERRORS:
            severity = SeverityNumber.ERROR
        elif kind in WARNINGS:
            severity = SeverityNumber.WARN
        attributes = {"gphoto.kind": kind, "gphoto.job": job, **self._about(path)}
        if self._paths and isinstance(detail, str):  # an error text often quotes a path
            attributes["gphoto.detail"] = detail
        self._logger.emit(
            timestamp=at, context=self._context(ids), severity_number=severity,
            severity_text=severity.name, body=kind, attributes=attributes,
        )

    def _context(self, ids: _Ids | None) -> Context:
        """As if inside the root span of that photo."""
        from opentelemetry import trace
        from opentelemetry.context import Context

        if ids is None:
            return Context()
        sampled = trace.TraceFlags.SAMPLED if self._tracer else trace.TraceFlags.DEFAULT
        inside = trace.SpanContext(
            ids.trace, ids.root, is_remote=False, trace_flags=trace.TraceFlags(sampled)
        )
        return trace.set_span_in_context(trace.NonRecordingSpan(inside), Context())

    def _send_trace(
        self, path: str, life: Sequence[_Event], begins: _Event, seen: float, ids: _Ids
    ) -> None:
        from opentelemetry import trace
        from opentelemetry.context import Context

        if begins.at > seen:
            return
        told = [e for e in life if e.id >= begins.id and e.at <= seen]
        kinds = {e.kind for e in told}
        work = [e for e in told if e.kind in ("scrubbed", "sent")]
        sends = [i for i, e in enumerate(work) if e.kind == "sent"]
        stages: list[tuple[str, float, float]] = []
        if begins.kind == "landed" and work:
            stages.append(("wait", begins.at, work[0].at))
        if sends:
            last = sends[-1]
            # An earlier scrub, with a send after it, belongs to that send.
            if last and work[last - 1].kind == "scrubbed":
                stages.append(("scrub", work[last - 1].at, work[last].at))
            stages.append(("upload", work[last].at, seen))

        about = self._about(path)
        missing = [kind for kind in ("landed", "sent") if kind not in kinds]
        self._given.trace, self._given.span = ids
        root = self._tracer.start_span(
            "photo", Context(), start_time=_ns(begins.at),
            # Without its landing the root begins late. Say so, or it looks like a quick one.
            attributes={**about, "gphoto.missing": missing} if missing else about,
        )
        inside = trace.set_span_in_context(root, Context())
        for name, began, ended in stages:
            if ended >= began:  # a clock was put back
                self._given.span = ids.child(name)
                span = self._tracer.start_span(
                    name, inside, start_time=_ns(began), attributes=about
                )
                span.end(_ns(ended))
        root.end(_ns(seen))


def _resource() -> Resource:
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    resource = Resource.create()
    # The SDK's own default, so nobody gave a name.
    if str(resource.attributes[SERVICE_NAME]).startswith("unknown_service"):
        resource = resource.merge(Resource({SERVICE_NAME: "gphoto"}))
    return resource
