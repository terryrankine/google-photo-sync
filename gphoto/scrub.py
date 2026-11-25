"""What may be taken out of a photo before it is sent.

The owner lists groups in SCRUB. Each group knows which tags it removes. The capture
time, time zone, rotation, colour and camera model belong to no group, so nothing the
owner writes can remove them.

This module decides. incoming.py runs exiftool and checks the result.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import NamedTuple

# In the order they are reported.
GROUPS: dict[str, str] = {
    "mpf": "the camera's large MPF preview, which keeps Google from shrinking the photo",
    "serial": "camera and lens serial numbers and shutter count, with all maker notes",
    "gps": "where the photo was taken",
    "previews": "the EXIF thumbnail, embedded previews and the MPF preview",
    "names": "artist, copyright, owner, user comment and description",
    "maker": "all maker notes",
}

# Google matches on bytes, so a photo with nothing but MPF to remove must keep coming out
# the same. Changing these changes every such photo.
MPF_ARGUMENTS = ["-mpf:all=", "-trailer:all="]
# Phones keep an HDR gain map under another type. That is part of the photo.
STRIPPABLE_MPF = "Large Thumbnail"

KEEP = frozenset(
    """DateTimeOriginal CreateDate ModifyDate DateTimeDigitized DateCreated TimeCreated
    DigitalCreationDate DigitalCreationTime SubSecTime SubSecTimeOriginal SubSecTimeDigitized
    OffsetTime OffsetTimeOriginal OffsetTimeDigitized TimeZoneOffset Orientation
    ColorSpace InteropIndex InteropVersion Gamma WhitePoint PrimaryChromaticities
    YCbCrCoefficients ReferenceBlackWhite TransferFunction Make Model""".split()
)

_SERIAL = re.compile(r"serial|shutter(count|actuation|release)|imagecount", re.IGNORECASE)
_GPS = re.compile(r"gps", re.IGNORECASE)
_PREVIEW = re.compile(
    r"^(ThumbnailImage|ThumbnailTIFF|PreviewImage|PreviewTIFF|JpgFromRaw|OtherImage"
    r"|PhotoshopThumbnail|PhotoshopBGRThumbnail)$"
)
_NAMES = frozenset(
    """Artist Copyright OwnerName CameraOwnerName UserComment ImageDescription Comment
    XPAuthor XPComment XPTitle XPSubject Creator Rights Description Owner UsageTerms
    AuthorsPosition CaptionWriter Credit CopyrightNotice By-line By-lineTitle
    Caption-Abstract Writer-Editor Photographer""".split()
)
# A position in the file, or a block's own bookkeeping. They move on any rewrite.
_MOVES = frozenset(
    """ThumbnailOffset PreviewImageStart OtherImageStart JpgFromRawStart MPImageStart
    XMPToolkit CurrentIPTCDigest IPTCDigest ApplicationRecordVersion""".split()
)
_OFF = {"No", "Off"}


class StripError(RuntimeError):
    """The scrubbed copy failed a check. The original was left alone."""


class Tag(NamedTuple):
    family: str  # EXIF, MakerNotes, XMP
    group: str  # IFD0, Nikon, XMP-dc
    name: str

    def __str__(self) -> str:
        return f"{self.group}:{self.name}"


Tags = Mapping[Tag, tuple[str, ...]]
_ZONE = Tag("EXIF", "ExifIFD", "OffsetTimeOriginal")


def read_tags(found: Mapping[str, object]) -> dict[Tag, tuple[str, ...]]:
    """Tags from `exiftool -j -a -G0:1:4`. Tags about the file on disk are left out.

    exiftool numbers repeated names across the whole file, so a number changes when an
    unrelated tag goes. The numbers are dropped and repeats are kept as a sorted list.
    """
    tags: dict[Tag, list[str]] = {}
    for key, value in found.items():
        *groups, name = [p for p in key.split(":") if not re.fullmatch(r"Copy\d+", p)]
        if not groups or groups[0] in ("Composite", "ExifTool") or groups[-1] == "System":
            continue
        text = value if isinstance(value, str) else json.dumps(value)
        tags.setdefault(Tag(groups[0], groups[-1], name), []).append(text)
    return {tag: tuple(sorted(values)) for tag, values in tags.items()}


def mpf_types(tags: Tags) -> tuple[str, ...]:
    """Types of the extra images in the MPF block, the first being the photo itself."""
    return tuple(
        value
        for tag, values in sorted(tags.items())
        if _is_extra_mpf(tag)
        for value in values
    )


def unknown_mpf(types: Iterable[str]) -> list[str]:
    return [t for t in types if not t.startswith(STRIPPABLE_MPF)]


def _is_extra_mpf(tag: Tag) -> bool:
    return tag.family == "MPF" and tag.name == "MPImageType" and tag.group != "MPImage1"


def _is_note(tag: Tag, name: str) -> bool:
    return tag.family == "MakerNotes" and tag.name == name


def _filled(values: Iterable[str]) -> bool:
    return any(v.strip(" \0\t\r\n") for v in values)


def _kept(tag: Tag) -> bool:
    """Part of every photo. A copy in a thumbnail or a maker note is not the photo's own."""
    if tag.family == "ICC_Profile":
        return True
    return tag.name in KEEP and tag.family not in ("MakerNotes", "MPF") and tag.group != "IFD1"


def _wants(group: str, tag: Tag, values: tuple[str, ...]) -> bool:
    """Whether this tag must be gone. A blank field is not worth changing the file for."""
    if _kept(tag) or not _filled(values):
        return False
    match group:
        case "mpf":
            return _is_extra_mpf(tag)
        case "serial":
            # exiftool cannot read every maker note, and Nikon's shutter count unlocks
            # other blocks, so it cannot go alone. Only no maker notes is known clean.
            return tag.family == "MakerNotes" or bool(_SERIAL.search(tag.name))
        case "gps":
            return bool(_GPS.search(tag.name)) and tag.name != "GPSVersionID"
        case "previews":
            return _is_extra_mpf(tag) or bool(_PREVIEW.match(tag.name))
        case "names":
            # XMP text can carry a language, as in Description-fr.
            base = tag.name.partition("-")[0] if tag.family == "XMP" else tag.name
            contact = tag.group == "XMP-iptcCore" and base.startswith("Creator")
            return base in _NAMES or contact
        case "maker":
            return tag.family == "MakerNotes"
    raise AssertionError(group)


def _covers(group: str, tag: Tag) -> bool:
    """Whether the group may change or remove this tag, whole maker notes aside."""
    match group:
        case "mpf":
            return tag.family == "MPF"
        case "gps":
            return tag.group == "GPS" or bool(_GPS.search(tag.name))
        case "previews":
            return (
                tag.family == "MPF"
                or tag.group == "IFD1"
                or tag.name.startswith(("Thumbnail", "PreviewImage"))
                or bool(_PREVIEW.match(tag.name))
            )
    return tag.family != "MakerNotes" and _wants(group, tag, ("filled",))


@dataclass(frozen=True)
class Rules:
    """The groups the owner listed, in the order of GROUPS."""

    names: tuple[str, ...]

    def found(self, tags: Tags) -> list[str]:
        """The groups that have something to remove from this photo."""
        return [g for g in self.names if any(_wants(g, t, v) for t, v in tags.items())]

    def drops_notes(self, tags: Tags) -> bool:
        """exiftool cannot delete one entry of a maker note, so all of it goes."""
        return any(
            _wants(g, t, v)
            for g in self.names
            if g != "previews"  # the one thing exiftool can empty in place
            for t, v in tags.items()
            if t.family == "MakerNotes"
        )

    def covers(self, tag: Tag, drops_notes: bool) -> bool:
        if _kept(tag):
            return False
        # Print hints are often stored inside the maker notes and go with them.
        if drops_notes and tag.family in ("MakerNotes", "PrintIM"):
            return True
        return any(_covers(g, tag) for g in self.names)

    def arguments(self, tags: Tags) -> list[str]:
        """What to tell exiftool."""
        wanted = [(g, t) for g in self.names for t, v in tags.items() if _wants(g, t, v)]
        drops = self.drops_notes(tags)
        arguments: list[str] = []
        # Emptying a preview cuts the MPF image off the end of the file as well, so
        # previews takes the whole MPF block rather than leave one that points at nothing.
        if any(t.family == "MPF" for _, t in wanted):
            arguments += MPF_ARGUMENTS
        if drops:
            arguments.append("-MakerNotes:all=")
        for group, tag in wanted:
            if tag.family == "MPF":
                continue
            if tag.family == "MakerNotes":
                if group == "previews" and not drops:
                    arguments.append("-PreviewImage=")
            elif tag.group in ("GPS", "IFD1"):
                arguments.append(f"-{tag.group}:all=")
            else:
                arguments.append(f"-{tag}=")
        zone = self.carried_zone(tags)
        if zone:
            arguments.append(f"-{_ZONE}={zone}")
        return list(dict.fromkeys(arguments))

    def carried_zone(self, tags: Tags) -> str | None:
        """The time zone to move to EXIF when only the maker notes hold it.

        Older Nikons write it nowhere else. Whether summer time is counted in it differs
        between makers, so with summer time on there is no safe answer.
        """
        if not self.drops_notes(tags) or _filled(tags.get(_ZONE, ())):
            return None
        zones = {v for t, vs in tags.items() if _is_note(t, "TimeZone") for v in vs}
        if not zones:
            return None
        summer = {v for t, vs in tags.items() if _is_note(t, "DaylightSavings") for v in vs}
        zone = zones.pop()
        if zones or summer - _OFF or not re.fullmatch(r"[+-]\d\d:\d\d", zone):
            raise StripError("only the maker notes hold the time zone and it is not clear")
        return zone

    def check(self, before: Tags, after: Tags) -> None:
        """Raise if anything but what these groups cover is different. Names no values."""
        drops = self.drops_notes(before)
        zone = self.carried_zone(before)
        wrong = [
            tag
            for tag in sorted(before.keys() | after.keys())
            if before.get(tag) != after.get(tag)
            and tag.name not in _MOVES
            and not (tag in before and self.covers(tag, drops))
            and not (tag == _ZONE and zone and after.get(tag) == (zone,))
        ]
        if wrong:
            raise StripError(f"other tags would change: {_listed(wrong)}")
        if drops:
            own = {t.name for t in after if _kept(t)}
            lost = [
                t
                for t in before
                if t.family == "MakerNotes" and t.name in KEEP and t.name not in own
            ]
            if lost:
                raise StripError(f"only the maker notes hold: {_listed(lost)}")

    def check_gone(self, after: Tags) -> None:
        """Raise if a group left something behind."""
        for group in self.names:
            left = [t for t, v in after.items() if _wants(group, t, v)]
            if left:
                raise StripError(f"{group} still present: {_listed(left)}")

    def check_serial_text(self, before: Tags, data: bytes) -> None:
        """Raise if a serial number survives anywhere in the file, under any tag or none."""
        if "serial" not in self.names:
            return
        for text in _serial_texts(before):
            if any(text.encode(code) in data for code in ("ascii", "utf-16-le", "utf-16-be")):
                raise StripError("serial number text still present in the file")


def _serial_texts(tags: Tags) -> set[str]:
    """Runs long enough not to appear by chance, with a digit, not one repeated character."""
    texts = set()
    for tag, values in tags.items():
        if "serial" not in tag.name.lower():
            continue
        for run in re.findall(r"[0-9A-Za-z]{5,}", " ".join(values)):
            for text in (run, run.lstrip("0")):
                if len(text) >= 5 and re.search(r"\d", text) and len(set(text)) > 1:
                    texts.add(text)
    return texts


def _listed(tags: Iterable[Tag]) -> str:
    names = [str(t) for t in tags]
    return ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")


def parse(text: str) -> Rules:
    """Rules from a comma separated list of group names."""
    asked = [part.strip().lower() for part in text.split(",") if part.strip()]
    unknown = [name for name in asked if name not in GROUPS]
    if unknown:
        raise ValueError(f"unknown scrub group: {', '.join(unknown)}. Use {', '.join(GROUPS)}")
    if not asked:
        raise ValueError(f"the scrub list names no group. Use {', '.join(GROUPS)}")
    return Rules(tuple(name for name in GROUPS if name in asked))


def parse_cameras(text: str) -> tuple[str, ...]:
    """Make prefixes from a comma separated list. A blank prefix would match every phone."""
    return tuple(part.strip().upper() for part in text.split(",") if part.strip())


DEFAULT_RULES = parse("mpf")
DEFAULT_CAMERAS = parse_cameras("NIKON")


@dataclass(frozen=True)
class Settings:
    rules: Rules
    cameras: tuple[str, ...]


def from_env(env: Mapping[str, str] | None = None) -> Settings:
    """SCRUB and CAMERAS. Blank counts as not set, because compose passes blanks."""
    env = os.environ if env is None else env
    groups = env.get("SCRUB", "")
    return Settings(
        rules=parse(groups) if groups.strip() else DEFAULT_RULES,
        cameras=parse_cameras(env.get("CAMERAS", "")) or DEFAULT_CAMERAS,
    )
