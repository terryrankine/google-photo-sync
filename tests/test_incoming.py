"""Incoming photo rules: wait, strip Nikon MPF in place, hand over to staging."""

import hashlib
import io
import os
import shutil
import struct
import subprocess
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from gphoto import incoming

pytestmark = pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool not installed")

LARGE_THUMBNAIL = 0x010002
UNDEFINED = 0x000000
HOUR = 3600


def make_jpeg(
    path: Path,
    make: str = "NIKON CORPORATION",
    taken: str = "2026:11:24 18:04:46",
    second_image: int | None = LARGE_THUMBNAIL,
    seed: int = 1,
) -> Path:
    """Write a small JPEG. second_image is the MPF type of an embedded second image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    main = Image.frombytes("RGB", (64, 48), hashlib.shake_256(bytes([seed])).digest(64 * 48 * 3))
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = make
    exif.get_ifd(0x8769)[0x9003] = taken
    if second_image is None:
        main.save(buf, "JPEG", quality=90, exif=exif)
        data = buf.getvalue()
    else:
        main.save(
            buf, "MPO", save_all=True, append_images=[main.resize((32, 24))], quality=90, exif=exif
        )
        data = buf.getvalue()
        # Pillow writes the second entry as Undefined. Cameras write a real type.
        start = data.index(b"MPF\x00") + 4
        order = "<" if data[start : start + 2] == b"II" else ">"
        # The entry table starts 50 bytes after the MPF header, 16 bytes per image.
        entry = start + 50 + 16
        data = data[:entry] + struct.pack(order + "L", second_image) + data[entry + 4 :]
    path.write_bytes(data)
    stamp = 1795514686  # 2026-11-24 18:04:46 +08:00
    os.utime(path, (stamp, stamp))
    return path


def pixels(path: Path) -> bytes:
    with Image.open(path) as im:
        return im.convert("RGB").tobytes()


def has_mpf(path: Path) -> bool:
    return bool(
        subprocess.run(
            ["exiftool", "-s3", "-MPF:MPFVersion", str(path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )


class Clock:
    def __init__(self) -> None:
        self.now = 1_795_600_000.0

    def __call__(self) -> float:
        return self.now


class Box:
    """A fake NAS, staging folder and clock."""

    def __init__(self, tmp_path: Path) -> None:
        self.root, self.staging = tmp_path / "pics", tmp_path / "staging"
        self.root.mkdir()
        (self.root / "2026").mkdir()
        self.staging.mkdir()
        self.db = tmp_path / "state.db"
        self.clock = Clock()
        self.folder = self.root / "2026" / "20261124-dance"
        self.landed: dict[str, float] = {}

    def runner(self, **kwargs):
        return incoming.Runner(
            root=self.root,
            staging=self.staging,
            db_path=self.db,
            since=date(2026, 11, 24),
            wait_seconds=4 * HOUR,
            clock=self.clock,
            landed_at=lambda p: self.landed.get(p.name, self.clock.now),
            **kwargs,
        )

    def landed_long_ago(self, *names: str) -> None:
        for name in names:
            self.landed[name] = self.clock.now - 5 * HOUR

    def sent(self) -> list[str]:
        return sorted(p.name for p in self.staging.iterdir())


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# --- strip ---------------------------------------------------------------


def test_fixture_is_a_nikon_with_large_thumbnail(tmp_path):
    info = incoming.inspect(make_jpeg(tmp_path / "a.JPG"))
    assert info.make.startswith("NIKON")
    assert info.mpf_types == ("Large Thumbnail (full HD equivalent)",)


def test_strip_removes_mpf(tmp_path):
    p = make_jpeg(tmp_path / "a.JPG")
    incoming.strip_in_place(p)
    assert not has_mpf(p)


def test_strip_keeps_pixels_and_file_date(tmp_path):
    p = make_jpeg(tmp_path / "a.JPG")
    before, mtime = pixels(p), p.stat().st_mtime
    incoming.strip_in_place(p)
    assert pixels(p) == before
    assert p.stat().st_mtime == mtime


def test_strip_leaves_no_temp_file(tmp_path):
    p = make_jpeg(tmp_path / "a.JPG")
    incoming.strip_in_place(p)
    assert [x.name for x in tmp_path.iterdir()] == ["a.JPG"]


def test_strip_keeps_original_when_pixels_would_change(tmp_path, monkeypatch):
    p = make_jpeg(tmp_path / "a.JPG")
    before = p.read_bytes()

    def damage(src: Path, dst: Path) -> None:
        make_jpeg(dst, second_image=None, seed=9)

    monkeypatch.setattr(incoming, "_remove_mpf", damage)
    with pytest.raises(incoming.StripError):
        incoming.strip_in_place(p)
    assert p.read_bytes() == before
    assert [x.name for x in tmp_path.iterdir()] == ["a.JPG"]


def test_strip_keeps_original_when_other_tags_would_change(tmp_path, monkeypatch):
    p = make_jpeg(tmp_path / "a.JPG")
    before = p.read_bytes()
    real = incoming._remove_mpf

    def lose_make(src: Path, dst: Path) -> None:
        real(src, dst)
        subprocess.run(
            ["exiftool", "-q", "-overwrite_original", "-Make=", str(dst)], check=True
        )

    monkeypatch.setattr(incoming, "_remove_mpf", lose_make)
    with pytest.raises(incoming.StripError):
        incoming.strip_in_place(p)
    assert p.read_bytes() == before


def test_strip_keeps_file_edited_while_stripping(tmp_path, monkeypatch):
    p = make_jpeg(tmp_path / "a.JPG")
    real = incoming._remove_mpf

    def edit_during(src: Path, dst: Path) -> None:
        real(src, dst)
        os.utime(p, (1795600000, 1795600000))

    monkeypatch.setattr(incoming, "_remove_mpf", edit_during)
    with pytest.raises(incoming.StripError):
        incoming.strip_in_place(p)
    assert has_mpf(p)


# --- rules ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, "strip"),
        ({"second_image": None}, "send"),
        ({"make": "Xiaomi", "second_image": UNDEFINED}, "skip"),
        ({"make": "Xiaomi", "second_image": None}, "skip"),
        ({"second_image": UNDEFINED}, "skip"),
        ({"taken": "2026:11:23 23:59:59"}, "skip"),
        ({"taken": "2026:11:24 00:00:00"}, "strip"),
    ],
    ids=[
        "nikon-mpf",
        "nikon-plain",
        "phone-hdr",
        "phone-plain",
        "nikon-unknown-mpf",
        "day-before-since",
        "first-second-of-since",
    ],
)
def test_decide(tmp_path, kwargs, expected):
    info = incoming.inspect(make_jpeg(tmp_path / "a.JPG", **kwargs))
    assert incoming.decide(info, date(2026, 11, 24)).action.value == expected


# --- runner --------------------------------------------------------------


def test_waits_four_hours_after_landing(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    r.tick()
    box.clock.now += 4 * HOUR - 1
    r.tick()
    assert box.sent() == []
    box.clock.now += 1
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_old_landing_time_is_sent_at_once(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_sent_file_is_the_same_bytes_as_the_stripped_original(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner(in_place=True).tick()
    assert not has_mpf(p)
    assert (box.staging / "DSC_1.JPG").read_bytes() == p.read_bytes()


def test_deleted_within_four_hours_is_never_sent(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    make_jpeg(box.folder / "DSC_2.JPG", seed=2)
    r = box.runner()
    r.tick()
    box.clock.now += 3 * HOUR
    p.unlink()
    r.tick()
    box.clock.now += 2 * HOUR
    r.tick()
    assert box.sent() == ["DSC_2.JPG"]


def test_still_copying_restarts_the_wait(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    r.tick()
    box.clock.now += 3 * HOUR
    make_jpeg(p, seed=5, second_image=None)
    r.tick()
    box.clock.now += 2 * HOUR
    r.tick()
    assert box.sent() == []
    box.clock.now += 2 * HOUR
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_phone_file_is_untouched_and_not_sent(box):
    p = make_jpeg(box.folder / "IMG_1.jpg", make="Xiaomi", second_image=UNDEFINED)
    before = p.read_bytes()
    box.landed_long_ago("IMG_1.jpg")
    box.runner().tick()
    assert box.sent() == []
    assert p.read_bytes() == before


def test_sends_once_across_restarts(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    (box.staging / "DSC_1.JPG").unlink()
    box.runner().tick()
    assert box.sent() == []


def test_same_bytes_in_two_folders_sent_once(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    make_jpeg(box.root / "2026" / "copy" / "DSC_1b.JPG")
    box.landed_long_ago("DSC_1.JPG", "DSC_1b.JPG")
    box.runner().tick()
    assert len(box.sent()) == 1


def test_same_name_different_photo_keeps_both(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    make_jpeg(box.root / "2026" / "other" / "DSC_1.JPG", seed=2)
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    assert len(box.sent()) == 2


def test_one_bad_file_does_not_stop_the_rest(box):
    bad = box.folder / "DSC_0.JPG"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"not a jpeg")
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_0.JPG", "DSC_1.JPG")
    r = box.runner()
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]
    assert r.status("2026/20261124-dance/DSC_0.JPG") == "failed"


def test_empty_root_means_mount_lost_not_files_deleted(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    r = box.runner()
    r.tick()
    shutil.rmtree(box.root / "2026")
    (box.root / "Camera Roll").mkdir()
    with pytest.raises(incoming.RootUnavailable):
        r.tick()
    make_jpeg(p)
    box.clock.now += 4 * HOUR
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_edit_after_send_is_not_sent_again(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    r = box.runner()
    r.tick()
    make_jpeg(p, seed=8, second_image=None)
    box.clock.now += 9 * HOUR
    r.tick()
    box.clock.now += 9 * HOUR
    r.tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_ignores_synology_folders(box):
    make_jpeg(box.folder / "@eaDir" / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    assert box.sent() == []


def test_dry_run_changes_nothing(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    before = p.read_bytes()
    box.landed_long_ago("DSC_1.JPG")
    box.runner(dry_run=True).tick()
    assert box.sent() == []
    assert p.read_bytes() == before
    box.runner().tick()
    assert box.sent() == ["DSC_1.JPG"]


def test_files_that_landed_before_the_cutoff_are_not_even_opened(box, monkeypatch):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed["DSC_1.JPG"] = box.clock.now - 72 * HOUR
    monkeypatch.setattr(incoming, "inspect", lambda p: pytest.fail("opened an old file"))
    r = box.runner()
    r.tick()
    assert r.status("2026/20261124-dance/DSC_1.JPG") is None


def test_old_year_folders_are_not_walked(box):
    make_jpeg(box.root / "2025" / "x" / "DSC_1.JPG")
    make_jpeg(box.root / "Camera Roll" / "DSC_2.JPG", seed=2)
    box.landed_long_ago("DSC_1.JPG", "DSC_2.JPG")
    box.runner().tick()
    assert box.sent() == ["DSC_2.JPG"]


def test_staged_file_is_readable_by_the_browser_user(box):
    p = make_jpeg(box.folder / "DSC_1.JPG", second_image=None)
    p.chmod(0o550)
    box.landed_long_ago("DSC_1.JPG")
    box.runner().tick()
    assert (box.staging / "DSC_1.JPG").stat().st_mode & 0o444 == 0o444


def test_strip_never_changes_permissions(tmp_path, monkeypatch):
    # chmod on a Synology share replaces the inherited ACL.
    p = make_jpeg(tmp_path / "a.JPG")
    monkeypatch.setattr(os, "chmod", lambda *a, **k: pytest.fail("chmod on the NAS file"))
    incoming.strip_in_place(p)
    assert not has_mpf(p)


def test_loop_exits_when_the_photo_folder_is_lost(tmp_path, monkeypatch):
    # Docker then restarts the container, which picks the mount up again.
    (tmp_path / "pics").mkdir()
    monkeypatch.setattr(incoming.time, "sleep", lambda s: pytest.fail("kept running"))
    code = incoming.main(
        ["--root", str(tmp_path / "pics"), "--staging", str(tmp_path), "--db",
         str(tmp_path / "s.db"), "--since", "2026-11-24", "--interval", "60"]
    )
    assert code == 1


def test_copy_mode_leaves_the_nas_file_alone(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    before = p.read_bytes()
    box.landed_long_ago("DSC_1.JPG")
    box.runner(in_place=False).tick()
    assert p.read_bytes() == before
    assert not has_mpf(box.staging / "DSC_1.JPG")


def test_copy_mode_sends_the_same_bytes_as_in_place(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner(in_place=False).tick()
    incoming.strip_in_place(p)
    assert (box.staging / "DSC_1.JPG").read_bytes() == p.read_bytes()


def test_copy_mode_keeps_the_file_date(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner(in_place=False).tick()
    assert (box.staging / "DSC_1.JPG").stat().st_mtime == p.stat().st_mtime


def test_copy_mode_needs_no_write_access_to_the_nas(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.folder.chmod(0o555)
    try:
        box.runner(in_place=False).tick()
    finally:
        box.folder.chmod(0o755)
    assert box.sent() == ["DSC_1.JPG"]


def test_copy_mode_leaves_no_work_files(box):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner(in_place=False).tick()
    assert list((box.db.parent / "work").iterdir()) == []


def test_in_place_switch_later_does_not_send_again(box):
    p = make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")
    box.runner(in_place=False).tick()
    (box.staging / "DSC_1.JPG").unlink()
    box.runner(in_place=True).tick()
    assert box.sent() == []


@pytest.mark.parametrize("in_place", [True, False])
def test_percent_sign_in_a_name_is_kept(box, in_place):
    # exiftool expands %f and friends in an output name.
    p = make_jpeg(box.folder / "100%f DSC_1.JPG")
    box.landed_long_ago(p.name)
    box.runner(in_place=in_place).tick()
    assert box.sent() == [p.name]
    assert [x.name for x in box.folder.iterdir()] == [p.name]


def test_missing_exiftool_is_retried_not_a_vanished_photo(box, monkeypatch):
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_1.JPG")

    def no_exiftool(*args, **kwargs):
        raise FileNotFoundError("exiftool")

    monkeypatch.setattr(incoming.subprocess, "run", no_exiftool)
    r = box.runner()
    r.tick()
    assert r.status("2026/20261124-dance/DSC_1.JPG") == "waiting"
    assert box.sent() == []


def test_photo_deleted_while_it_is_handled_does_not_stop_the_rest(box, monkeypatch):
    gone = make_jpeg(box.folder / "DSC_0.JPG", seed=3)
    make_jpeg(box.folder / "DSC_1.JPG")
    box.landed_long_ago("DSC_0.JPG", "DSC_1.JPG")
    real = incoming.inspect

    def delete_first(path):
        if path.name == "DSC_0.JPG":
            gone.unlink()
            raise RuntimeError("exiftool failed: file not found")
        return real(path)

    monkeypatch.setattr(incoming, "inspect", delete_first)
    box.runner().tick()
    assert box.sent() == ["DSC_1.JPG"]
