"""Small charts and figures for the ops page, drawn as plain SVG numbers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from gphoto import metrics
from gphoto.ops import Samples

WIDTH, HEIGHT = 160, 36


@dataclass(frozen=True)
class Tile:
    name: str
    value: str
    line: str  # points of an SVG polyline, empty when there is nothing to draw yet
    last: tuple[float, float] | None
    note: str


@dataclass(frozen=True)
class Column:
    day: str
    count: int
    x: float
    y: float
    width: float
    height: float
    mark: bool


def size(value: float | None) -> str:
    if value is None:
        return "not known"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1024
    return ""


def seconds(value: float | None) -> str:
    if value is None:
        return "not known"
    if value < 1:
        return f"{value * 1000:.0f} ms"
    return f"{value:.1f} s" if value < 120 else f"{value / 60:.0f} min"


def number(value: float | None) -> str:
    return "not known" if value is None else f"{value:,.0f}"


def _line(points: list[tuple[float, float | None]]) -> tuple[str, tuple[float, float] | None]:
    known = [(t, v) for t, v in points if v is not None]
    if len(known) < 2:
        return "", None
    # A day of minutes is far more than the pixels there are.
    known = known[:: max(1, len(known) // WIDTH)] + known[-1:]
    start, span = known[0][0], max(known[-1][0] - known[0][0], 1)
    low, high = min(0, min(v for _, v in known)), max(v for _, v in known)
    room = (high - low) or 1
    drawn = [
        (round((t - start) / span * (WIDTH - 8) + 4, 1),
         round(HEIGHT - 4 - (v - low) / room * (HEIGHT - 8), 1))
        for t, v in known
    ]
    return " ".join(f"{x},{y}" for x, y in drawn), drawn[-1]


def tiles(saved: dict[str, Any], samples: Samples | None) -> list[Tile]:
    incoming, google = saved["incoming"], saved["google"]

    def tile(name: str, series: str, value: str, show: Any) -> Tile:
        points = samples.series(series) if samples else []
        line, last = _line(points)
        seen = [v for _, v in points if v is not None]
        note = f"{show(min(seen))} to {show(max(seen))} since this page started" if seen else ""
        return Tile(name, value, line, last, note)

    return [
        tile("Last NAS pass", "pass", seconds(metrics.value(incoming, "gphoto.pass.duration")), seconds),
        tile("Last Google check", "check", seconds(metrics.value(google, "gphoto.check.duration")), seconds),
        tile("Waiting", "waiting", number(metrics.value(incoming, "gphoto.waiting")), number),
        tile("On the way", "way", number(metrics.value(google, "gphoto.on_the_way")), number),
        tile("Staging", "staging", size(metrics.value(google, "gphoto.staging.bytes")), size),
        tile("Disk free", "free", size(metrics.value(incoming, "gphoto.disk.free", mount="state")), size),
    ]


def columns(days: list[tuple[str, int]], width: int = 640, height: int = 120) -> list[Column]:
    most = max((n for _, n in days), default=0) or 1
    step = width / max(len(days), 1)
    tallest = max((i for i, (_, n) in enumerate(days) if n == most), default=-1)
    return [
        Column(
            date.fromisoformat(day).strftime("%d %b"), count, round(i * step + 1, 1),
            round(height - count / most * (height - 16), 1), round(step - 2, 1),
            round(count / most * (height - 16), 1), i == tallest,
        )
        for i, (day, count) in enumerate(days)
    ]


def _average(snapshot: dict[str, Any] | None, name: str) -> float | None:
    try:
        (point,) = snapshot["metrics"][name]["points"]
        return point["sum"] / point["count"]
    except (TypeError, KeyError, ValueError, ZeroDivisionError):
        return None


def _file(path: Path) -> float | None:
    try:
        return float(path.stat().st_size)
    except OSError:
        return None


def facts(
    state: Path, saved: dict[str, Any], now: float, wait_seconds: float
) -> list[tuple[str, list[tuple[str, str]]]]:
    incoming, google = saved["incoming"], saved["google"]

    def i(name: str, **a: str) -> float | None:
        return metrics.value(incoming, name, **a)

    def g(name: str, **a: str) -> float | None:
        return metrics.value(google, name, **a)

    chrome = "not known"
    try:
        chrome = google["metrics"]["gphoto.chrome.info"]["points"][-1]["attributes"]["version"]
    except (TypeError, KeyError, IndexError):
        pass

    def up(snapshot: dict[str, Any] | None) -> str:
        if not snapshot:
            return "not known"
        hours = max(0, now - snapshot["started"]) / 3600
        if hours >= 48:
            return f"{hours / 24:.0f} days"
        return "1 hour" if round(hours) == 1 else f"{hours:.0f} hours"

    def outcome(kind: str) -> str:
        return number(i("gphoto.photos", outcome=kind) or 0)

    return [
        ("NAS", [
            ("Folders known", number(i("gphoto.pass.folders_known"))),
            ("Folders listed last pass", number(i("gphoto.pass.folders_listed"))),
            ("Photos asked about last pass", number(i("gphoto.pass.photos_checked"))),
            ("Places not read", number(i("gphoto.pass.problems"))),
            ("Wait", f"{wait_seconds / 3600:g} hours"),
        ]),
        ("Since it started", [
            ("Sent", outcome("sent")), ("Skipped", outcome("skipped")),
            ("Left out", outcome("look")), ("Failed", outcome("failed")),
            ("Time to scrub, average", seconds(_average(incoming, "gphoto.scrub.duration"))),
            ("Sent until seen, average", seconds(_average(google, "gphoto.arrival.duration"))),
        ]),
        ("Google", [
            ("Signed in", "Yes" if g("gphoto.signed_in") else "No"),
            ("Folder allowed", "Yes" if g("gphoto.folder_allowed") else "No"),
            ("Searches", number(g("gphoto.searches") or 0)),
            ("Reloads", number(g("gphoto.reloads") or 0)),
            ("Search time, average", seconds(_average(google, "gphoto.search.duration"))),
        ]),
        ("Disk", [
            ("Staging", f"{number(g('gphoto.staging.files'))} files, {size(g('gphoto.staging.bytes'))}"),
            ("Free", size(i("gphoto.disk.free", mount="state"))),
            ("Photo database", size(_file(state / "incoming.db"))),
            ("Google database", size(_file(state / "google.db"))),
        ]),
        ("Versions", [
            ("gphoto", (incoming or google or {}).get("version", "not known")),
            ("Chrome", chrome),
            ("NAS check up for", up(incoming)), ("Google check up for", up(google)),
        ]),
    ]
