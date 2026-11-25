"""Scrub rules: named groups, what each may remove, and what none may ever remove."""

import json
import shutil
import struct
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageCms

from gphoto import incoming, scrub
from tests.test_incoming import LARGE_THUMBNAIL, UNDEFINED, has_mpf, make_jpeg, pixels

needs_exiftool = pytest.mark.skipif(shutil.which("exiftool") is None, reason="no exiftool")

SERIAL = "7654321"
SINCE = date(2026, 11, 24)
EVERYTHING = ",".join(scrub.GROUPS)


def write(path: Path, *args: str) -> None:
    subprocess.run(["exiftool", "-q", "-m", "-overwrite_original", *args, str(path)], check=True)


def read(path: Path, *args: str) -> dict[str, object]:
    out = subprocess.run(
        ["exiftool", "-j", "-G1", "-a", *args, str(path)], capture_output=True, check=True
    ).stdout
    return json.loads(out)[0]


def nikon_notes(zone: int = 480, summer: int = 0) -> bytes:
    """A small Nikon type 3 maker note: version, serial, colour space, world time, count."""
    entries = [
        (0x0001, 7, 4, b"0211"),
        (0x001D, 2, 8, SERIAL.encode() + b"\x00"),
        (0x001E, 3, 1, struct.pack("<HH", 1, 0)),
        (0x0024, 7, 4, struct.pack("<hBB", zone, summer, 0)),
        (0x00A7, 4, 1, struct.pack("<L", 123456)),
    ]
    at = 8 + 2 + 12 * len(entries) + 4
    table, data = struct.pack("<H", len(entries)), b""
    for tag, kind, count, value in entries:
        table += struct.pack("<HHL", tag, kind, count)
        if len(value) > 4:
            table += struct.pack("<L", at + len(data))
            data += value
        else:
            table += value
    return b"Nikon\x00\x02\x10\x00\x00" + b"II*\x00\x08\x00\x00\x00" + table + bytes(4) + data


def add_notes(path: Path, notes: bytes) -> None:
    """exiftool cannot create a maker note, so the EXIF segment is rebuilt by Pillow."""
    with Image.open(path) as im:
        exif = im.getexif()
        exif.get_ifd(0x8769)[0x927C] = notes
        raw = exif.tobytes()
    if not raw.startswith(b"Exif\x00\x00"):
        raw = b"Exif\x00\x00" + raw
    data = path.read_bytes()
    start = data.index(b"\xff\xe1")
    size = struct.unpack(">H", data[start + 2 : start + 4])[0]
    segment = b"\xff\xe1" + struct.pack(">H", len(raw) + 2) + raw
    path.write_bytes(data[:start] + segment + data[start + 2 + size :])


KEPT_ARGS = (
    "-ExifIFD:OffsetTime=+08:00",
    "-ExifIFD:OffsetTimeOriginal=+08:00",
    "-ExifIFD:OffsetTimeDigitized=+08:00",
    "-ExifIFD:SubSecTimeOriginal=12",
    "-ExifIFD:CreateDate=2026:11:24 18:04:46",
    "-IFD0:ModifyDate=2026:11:24 18:04:46",
    "-IFD0:Orientation#=6",
    "-IFD0:Model=NIKON D7100",
    "-ExifIFD:ColorSpace#=65535",
    "-InteropIFD:InteropIndex=R03",
    "-XMP-tiff:Make=NIKON CORPORATION",
    "-XMP-xmp:CreateDate=2026:11:24 18:04:46+08:00",
    "-XMP-photoshop:DateCreated=2026:11:24",
    "-IPTC:DateCreated=2026:11:24",
    "-IPTC:TimeCreated=18:04:46+08:00",
)
KEPT = (
    "IFD0:Make",
    "IFD0:Model",
    "IFD0:Orientation",
    "IFD0:ModifyDate",
    "ExifIFD:DateTimeOriginal",
    "ExifIFD:CreateDate",
    "ExifIFD:SubSecTimeOriginal",
    "ExifIFD:OffsetTime",
    "ExifIFD:OffsetTimeOriginal",
    "ExifIFD:OffsetTimeDigitized",
    "ExifIFD:ColorSpace",
    "InteropIFD:InteropIndex",
    "ICC-header:ColorSpaceData",
    "ICC_Profile:ProfileDescription",
    "XMP-tiff:Make",
    "XMP-xmp:CreateDate",
    "XMP-photoshop:DateCreated",
    "IPTC:DateCreated",
    "IPTC:TimeCreated",
)
DIRT = {
    "serial": (
        "-ExifIFD:SerialNumber=AB-99881",
        "-ExifIFD:LensSerialNumber=LL55667",
        "-XMP-aux:SerialNumber=AB-99881",
        "-XMP-aux:LensSerialNumber=LL55667",
    ),
    "gps": (
        "-GPS:GPSLatitude=31.9",
        "-GPS:GPSLatitudeRef=S",
        "-GPS:GPSLongitude=115.8",
        "-GPS:GPSLongitudeRef=E",
        "-XMP-exif:GPSLatitude=31.9",
    ),
    "names": (
        "-IFD0:Artist=A Person",
        "-IFD0:Copyright=A Person 2026",
        "-ExifIFD:OwnerName=A Person",
        "-ExifIFD:UserComment=hello",
        "-IFD0:ImageDescription=a dance",
        "-IFD0:XPAuthor=A Person",
        "-XMP-dc:Creator=A Person",
        "-XMP-dc:Rights=A Person",
        "-XMP-dc:Description=a dance",
        "-XMP-aux:OwnerName=A Person",
        "-IPTC:By-line=A Person",
        "-IPTC:CopyrightNotice=A Person",
        "-IPTC:Caption-Abstract=a dance",
        "-File:Comment=hello",
    ),
}


def photo(path: Path, *groups: str, notes: bytes | None = None, mpf: bool = False) -> Path:
    """A camera photo with everything that must stay, plus the named groups."""
    make_jpeg(path, second_image=LARGE_THUMBNAIL if mpf else None)
    if notes:
        add_notes(path, notes)
    if "previews" in groups:
        thumb = path.with_suffix(".thumb")
        Image.new("RGB", (16, 12), "red").save(thumb, "JPEG")
        write(path, f"-ThumbnailImage<={thumb}")
        thumb.unlink()
    profile = path.with_suffix(".icc")
    profile.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    write(path, f"-ICC_Profile<={profile}")
    profile.unlink()
    write(path, *KEPT_ARGS, *(a for g in groups for a in DIRT.get(g, ())))
    return path


def run(path: Path, names: str) -> tuple[Path, list[str]]:
    target = path.with_name("out.jpg")
    return target, incoming.scrub_to(path, target, scrub.parse(names))


# --- reading the settings ----------------------------------------------------


def test_the_groups():
    assert set(scrub.GROUPS) == {"mpf", "serial", "gps", "previews", "names", "maker"}


def test_parse_reads_a_list():
    assert scrub.parse(" MPF, serial ,").names == ("mpf", "serial")


def test_parse_ignores_order_and_repeats():
    assert scrub.parse("serial,mpf,serial") == scrub.parse("mpf,serial")


@pytest.mark.parametrize("text", ["mpf,serail", "all", "DateTimeOriginal", "mpf;serial"])
def test_parse_refuses_unknown_names(text):
    with pytest.raises(ValueError, match="unknown.*mpf.*serial"):
        scrub.parse(text)


@pytest.mark.parametrize("text", ["", " , "])
def test_parse_refuses_an_empty_list(text):
    with pytest.raises(ValueError, match="names no group"):
        scrub.parse(text)


@pytest.mark.parametrize("env", [{}, {"SCRUB": "", "CAMERAS": " "}])
def test_settings_default_to_nikon_and_mpf(env):
    settings = scrub.from_env(env)
    assert settings.rules == scrub.DEFAULT_RULES == scrub.parse("mpf")
    assert settings.cameras == scrub.DEFAULT_CAMERAS == ("NIKON",)


def test_settings_from_env():
    settings = scrub.from_env({"SCRUB": "mpf,gps", "CAMERAS": "nikon, Canon,"})
    assert settings.rules.names == ("mpf", "gps")
    assert settings.cameras == ("NIKON", "CANON")


def test_settings_read_the_real_environment(monkeypatch):
    monkeypatch.setenv("SCRUB", "maker")
    assert scrub.from_env().rules.names == ("maker",)


def test_settings_refuse_a_bad_name():
    with pytest.raises(ValueError, match="sreial"):
        scrub.from_env({"SCRUB": "sreial"})


# --- decide ------------------------------------------------------------------


LARGE = ("Large Thumbnail (full HD equivalent)",)


def decide(make="NIKON", mpf=(), found=(), cameras=scrub.DEFAULT_CAMERAS, rules="mpf") -> str:
    info = incoming.PhotoInfo(make, datetime(2026, 11, 24, 18), mpf, frozenset(found))
    return incoming.decide(info, SINCE, cameras, scrub.parse(rules)).action.value


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, "send"),
        ({"mpf": LARGE, "found": {"mpf", "previews"}}, "strip"),
        ({"make": "Canon"}, "skip"),
        ({"make": "Canon", "cameras": ("NIKON", "CANON")}, "send"),
        ({"make": "canon", "cameras": ("Canon",)}, "send"),
        ({"make": "", "cameras": ("CANON",)}, "skip"),
        ({"cameras": ("CANON",)}, "skip"),
        ({"found": {"serial"}}, "send"),
        ({"found": {"serial"}, "rules": "mpf,serial"}, "strip"),
        ({"found": {"gps"}, "rules": "mpf,serial"}, "send"),
        ({"make": "Xiaomi", "mpf": ("Undefined",), "cameras": ("XIAOMI",)}, "skip"),
        ({"mpf": ("Undefined",), "found": {"serial"}, "rules": "serial"}, "skip"),
        ({"mpf": (*LARGE, "Undefined"), "found": {"mpf"}}, "skip"),
        ({"mpf": LARGE, "found": {"mpf"}, "rules": "gps"}, "send"),
    ],
)
def test_decide(kwargs, expected):
    assert decide(**kwargs) == expected


@needs_exiftool
def test_inspect_finds_the_groups(tmp_path):
    p = photo(tmp_path / "a.JPG", "gps", "names", "previews", notes=nikon_notes())
    assert incoming.inspect(p).found == {"serial", "gps", "previews", "names", "maker"}


@needs_exiftool
def test_inspect_finds_nothing_in_a_clean_file(tmp_path):
    assert incoming.inspect(photo(tmp_path / "a.JPG")).found == frozenset()


@needs_exiftool
def test_blank_fields_are_not_worth_a_rewrite(tmp_path):
    # A Nikon always writes these, blank when the owner set nothing.
    p = photo(tmp_path / "a.JPG")
    write(p, "-IFD0:Artist=   ", "-ExifIFD:UserComment=  ", "-GPS:GPSVersionID=2.3.0.0")
    assert "IFD0:Artist" in read(p)
    assert incoming.inspect(p).found == frozenset()


# --- mpf stays exactly as it was ---------------------------------------------


def old_strip(path: Path) -> bytes:
    """What main did at 3f8e74a, so the bytes Google already holds keep matching."""
    return subprocess.run(
        ["exiftool", "-mpf:all=", "-trailer:all=", "-o", "-", str(path)],
        capture_output=True,
        check=True,
    ).stdout


@needs_exiftool
@pytest.mark.parametrize("names", ["mpf", "mpf,serial,gps,names"])
def test_mpf_gives_the_same_bytes_as_before(tmp_path, names):
    p = make_jpeg(tmp_path / "a.JPG")
    target, done = run(p, names)
    assert done == ["mpf"]
    assert target.read_bytes() == old_strip(p)


@needs_exiftool
def test_strip_in_place_gives_the_same_bytes_as_before(tmp_path):
    p = make_jpeg(tmp_path / "a.JPG")
    want = old_strip(p)
    assert incoming.strip_in_place(p) == ["mpf"]
    assert p.read_bytes() == want


@needs_exiftool
def test_a_file_without_mpf_is_untouched(tmp_path):
    p = photo(tmp_path / "a.JPG", "gps", "names", notes=nikon_notes())
    target, done = run(p, "mpf")
    assert done == []
    assert target.read_bytes() == p.read_bytes()
    assert target.stat().st_mtime == p.stat().st_mtime


@needs_exiftool
def test_in_place_does_not_replace_a_file_with_nothing_to_remove(tmp_path, monkeypatch):
    p = photo(tmp_path / "a.JPG")
    monkeypatch.setattr(incoming.os, "replace", lambda *a: pytest.fail("replaced the file"))
    assert incoming.strip_in_place(p) == []
    assert [x.name for x in tmp_path.iterdir()] == ["a.JPG"]


@needs_exiftool
def test_in_place_takes_rules(tmp_path):
    p = photo(tmp_path / "a.JPG", "gps")
    assert incoming.strip_in_place(p, scrub.parse("gps")) == ["gps"]
    assert "GPS:GPSLatitude" not in read(p)


@needs_exiftool
@pytest.mark.parametrize("names", ["mpf", "serial", "previews", EVERYTHING])
def test_a_gain_map_is_never_removed(tmp_path, names):
    p = make_jpeg(tmp_path / "a.JPG", second_image=UNDEFINED)
    with pytest.raises(incoming.StripError, match="unknown MPF"):
        run(p, names)
    assert [x.name for x in tmp_path.iterdir()] == ["a.JPG"]


@needs_exiftool
def test_mpf_left_alone_keeps_its_image(tmp_path):
    p = photo(tmp_path / "a.JPG", "gps", mpf=True)
    target, done = run(p, "gps")
    assert done == ["gps"]
    image = [
        subprocess.run(
            ["exiftool", "-b", "-MPImage2:PreviewImage", str(x)], capture_output=True, check=True
        ).stdout
        for x in (p, target)
    ]
    assert image[0] and image[0] == image[1]


# --- one group at a time -----------------------------------------------------


@needs_exiftool
@pytest.mark.parametrize("group", sorted(DIRT))
def test_a_group_removes_its_own_tags_and_no_others(tmp_path, group):
    p = photo(tmp_path / "a.JPG", *DIRT)
    before = read(p)
    target, done = run(p, group)
    after = read(target)
    assert done == [group]
    for other, args in DIRT.items():
        for name in (a[1:].split("=")[0] for a in args):
            assert name in before, name
            assert (name in after) == (other != group), name
    assert pixels(target) == pixels(p)


@needs_exiftool
@pytest.mark.parametrize(
    "group, dirt",
    [
        ("names", "-IPTC:By-line=A Person"),
        ("names", "-XMP-dc:Creator=A Person"),
        ("names", "-XMP-dc:Description-fr=une danse"),
        ("names", "-XMP-iptcCore:CreatorWorkEmail=a@example.invalid"),
        ("gps", "-XMP-iptcExt:LocationCreatedGPSLatitude=31.9"),
    ],
)
def test_a_block_may_go_with_its_last_entry(tmp_path, group, dirt):
    p = make_jpeg(tmp_path / "a.JPG", second_image=None)
    write(p, dirt)
    target, done = run(p, group)
    assert done == [group]
    assert dirt[1:].split("=")[0] not in read(target)


@needs_exiftool
def test_the_editing_program_is_not_a_name(tmp_path):
    p = make_jpeg(tmp_path / "a.JPG", second_image=None)
    write(p, "-XMP-xmp:CreatorTool=Some Editor")
    assert incoming.inspect(p).found == frozenset()


@needs_exiftool
def test_previews_removes_the_thumbnail_and_the_mpf_image(tmp_path):
    p = photo(tmp_path / "a.JPG", "previews", mpf=True)
    target, done = run(p, "previews")
    assert done == ["previews"]
    assert not has_mpf(target)
    assert not [k for k in read(target) if "Thumbnail" in k or k.startswith("IFD1:")]
    assert pixels(target) == pixels(p)


@needs_exiftool
def test_maker_removes_the_maker_notes_only(tmp_path):
    p = photo(tmp_path / "a.JPG", "gps", "names", notes=nikon_notes())
    target, done = run(p, "maker")
    assert done == ["maker"]
    after = read(target)
    gone = {k for k in read(p) if k not in after and not k.startswith("Composite:")}
    assert gone and all(k.startswith("Nikon:") for k in gone)


@needs_exiftool
def test_serial_takes_the_maker_notes_because_the_count_cannot_go_alone(tmp_path):
    p = photo(tmp_path / "a.JPG", "serial", notes=nikon_notes())
    assert str(read(p)["Nikon:SerialNumber"]) == SERIAL
    assert "Nikon:ShutterCount" in read(p)
    target, done = run(p, "serial")
    assert done == ["serial"]
    deep = read(target, "-u", "-U", "-ee")
    assert not [k for k in deep if k.startswith("Nikon:") or "erial" in k or "ShutterCount" in k]
    data = target.read_bytes()
    for text in (SERIAL, "99881", "LL55667"):
        assert text.encode() not in data
        assert text.encode("utf-16-le") not in data


@needs_exiftool
def test_every_group_that_did_something_is_named(tmp_path):
    p = photo(tmp_path / "a.JPG", "gps", notes=nikon_notes(), mpf=True)
    _, done = run(p, "mpf,serial,gps,names,maker")
    assert done == ["mpf", "serial", "gps", "maker"]


# --- what can never be removed -----------------------------------------------


@needs_exiftool
@pytest.mark.parametrize("names", [*scrub.GROUPS, EVERYTHING])
def test_what_must_stay_stays(tmp_path, names):
    p = photo(tmp_path / "a.JPG", *DIRT, "previews", notes=nikon_notes(), mpf=True)
    before = read(p)
    target, done = run(p, names)
    after = read(target)
    assert done
    for name in KEPT:
        assert name in before, name
        assert after.get(name) == before[name], name
    assert pixels(target) == pixels(p)
    profiles = []
    for path in (p, target):
        with Image.open(path) as im:
            profiles.append(im.info["icc_profile"])
    assert profiles[0] == profiles[1]


@pytest.mark.parametrize("group", scrub.GROUPS)
@pytest.mark.parametrize("name", sorted(scrub.KEEP))
def test_no_group_covers_what_must_stay(group, name):
    places = [("EXIF", "IFD0"), ("EXIF", "ExifIFD"), ("XMP", "XMP-tiff"), ("IPTC", "IPTC")]
    for place in places:
        assert not scrub.parse(group).covers(scrub.Tag(*place, name), drops_notes=True)


@pytest.mark.parametrize("group", scrub.GROUPS)
def test_no_group_covers_the_colour_profile(group):
    tag = scrub.Tag("ICC_Profile", "ICC_Profile", "ProfileCopyright")
    assert not scrub.parse(group).covers(tag, drops_notes=True)


@needs_exiftool
@pytest.mark.parametrize(
    "harm",
    [
        "-ExifIFD:DateTimeOriginal=",
        "-ExifIFD:OffsetTimeOriginal=",
        "-IFD0:Orientation=",
        "-IFD0:Orientation#=1",
        "-ICC_Profile:all=",
        "-ExifIFD:ColorSpace=",
        "-IFD0:Make=",
        "-IFD0:Model=",
        "-ExifIFD:ExposureTime=1/60",
        "-XMP-dc:Subject=extra",
    ],
)
def test_any_other_difference_is_refused(tmp_path, monkeypatch, harm):
    p = photo(tmp_path / "a.JPG", *DIRT, notes=nikon_notes())
    before = p.read_bytes()
    real = incoming._remove

    def worse(src, dst, args):
        real(src, dst, args)
        write(dst, harm)

    monkeypatch.setattr(incoming, "_remove", worse)
    with pytest.raises(incoming.StripError):
        run(p, EVERYTHING)
    assert p.read_bytes() == before
    assert [x.name for x in tmp_path.iterdir()] == ["a.JPG"]


@needs_exiftool
def test_changed_pixels_are_refused(tmp_path, monkeypatch):
    p = photo(tmp_path / "a.JPG", "gps")
    real = incoming._remove

    def damage(src, dst, args):
        real(src, dst, args)
        data = bytearray(dst.read_bytes())
        data[-40] ^= 1  # image data, so every tag still matches
        dst.write_bytes(data)

    monkeypatch.setattr(incoming, "_remove", damage)
    with pytest.raises(incoming.StripError, match="pixels would change"):
        run(p, "gps")
    assert not (tmp_path / "out.jpg").exists()


@needs_exiftool
def test_a_tag_that_did_not_go_is_refused(tmp_path, monkeypatch):
    p = photo(tmp_path / "a.JPG", "gps")
    monkeypatch.setattr(incoming, "_remove", lambda s, d, a: shutil.copyfile(s, d))
    with pytest.raises(incoming.StripError, match="gps still present"):
        run(p, "gps")
    assert not (tmp_path / "out.jpg").exists()


@needs_exiftool
def test_serial_text_left_anywhere_is_refused(tmp_path):
    # The serial repeated in a field the group does not own.
    p = photo(tmp_path / "a.JPG", "serial", notes=nikon_notes())
    write(p, f"-XMP-dc:Subject=camera {SERIAL}")
    with pytest.raises(incoming.StripError, match="serial number text") as error:
        run(p, "serial")
    assert SERIAL not in str(error.value)
    assert not (tmp_path / "out.jpg").exists()


# --- what only the maker notes hold ------------------------------------------


def without_offsets(path: Path, notes: bytes) -> Path:
    photo(path, notes=notes)
    write(path, *(f"-ExifIFD:OffsetTime{x}=" for x in ("", "Original", "Digitized")))
    return path


@needs_exiftool
@pytest.mark.parametrize("names", ["serial", "maker"])
@pytest.mark.parametrize("zone, text", [(480, "+08:00"), (-210, "-03:30")])
def test_a_time_zone_held_only_by_the_maker_notes_is_carried_over(tmp_path, names, zone, text):
    p = without_offsets(tmp_path / "a.JPG", nikon_notes(zone))
    target, _ = run(p, names)
    assert read(target)["ExifIFD:OffsetTimeOriginal"] == text


@needs_exiftool
def test_a_time_zone_in_exif_is_not_rewritten(tmp_path):
    p = photo(tmp_path / "a.JPG", notes=nikon_notes(zone=60))
    target, _ = run(p, "maker")
    assert read(target)["ExifIFD:OffsetTimeOriginal"] == "+08:00"


@needs_exiftool
def test_a_time_zone_that_would_be_a_guess_is_refused(tmp_path):
    p = without_offsets(tmp_path / "a.JPG", nikon_notes(60, summer=1))
    with pytest.raises(incoming.StripError, match="time zone"):
        run(p, "maker")
    assert not (tmp_path / "out.jpg").exists()


@needs_exiftool
def test_a_colour_space_held_only_by_the_maker_notes_is_not_lost(tmp_path):
    p = photo(tmp_path / "a.JPG", notes=nikon_notes())
    write(p, "-ExifIFD:ColorSpace=")
    with pytest.raises(incoming.StripError, match="ColorSpace"):
        run(p, "maker")
