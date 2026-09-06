"""The "you already have darks in incoming/" detector.

The safety property under test is the *asymmetry*: only a frame's own recognised
``IMAGETYP`` card produces an offer, and everything else — a light, a missing
card, a mixed folder — stays silent. A false positive here builds a "master
dark" out of somebody's subs, which then subtracts a picture of the sky out of
every stack it touches, so every test below is about refusing rather than
finding.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from seestack.calibrate import discover

pytest.importorskip("astropy")


def write_frame(
    path: Path, *, imagetyp: str | None = None, exposure_s: float = 30.0,
    gain: float = 80.0, temp_c: float = -5.0, size: tuple[int, int] = (8, 6),
) -> Path:
    """A tiny FITS frame that declares (or pointedly does not declare) a kind."""
    from astropy.io import fits

    h, w = size
    hdu = fits.PrimaryHDU(data=np.zeros((h, w), dtype=np.uint16))
    hdu.header["EXPTIME"] = exposure_s
    hdu.header["GAIN"] = gain
    hdu.header["CCD-TEMP"] = temp_c
    hdu.header["BAYERPAT"] = "RGGB"
    if imagetyp is not None:
        hdu.header["IMAGETYP"] = imagetyp
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu.writeto(path, overwrite=True)
    return path


def write_folder(folder: Path, n: int, **kw) -> Path:
    for i in range(n):
        write_frame(folder / f"frame_{i:03d}.fit", **kw)
    return folder


def test_a_folder_of_declared_darks_is_offered(tmp_path):
    write_folder(tmp_path / "Dark", 8, imagetyp="Dark Frame")

    found = discover.find_calibration_folders(tmp_path)

    assert len(found) == 1
    f = found[0]
    assert f.kind == "dark"
    assert f.folder_name == "Dark"
    assert f.rel_path == "Dark"
    assert f.n_frames == 8
    assert f.declared == {"dark": discover.SAMPLE_HEADERS}
    assert f.exposure_s == pytest.approx(30.0)
    assert f.gain == pytest.approx(80.0)
    assert f.sensor_temp_c == pytest.approx(-5.0)
    assert (f.width_px, f.height_px) == (6, 8)  # size is (h, w)


def test_lights_are_never_offered(tmp_path):
    """The whole point: a night's subs must not become a master dark."""
    write_folder(tmp_path / "M 42_sub", 40, imagetyp="Light Frame")

    assert discover.find_calibration_folders(tmp_path) == []


def test_a_folder_that_does_not_say_is_not_offered(tmp_path):
    """Silence, not a guess — a camera that writes no ``IMAGETYP`` gets no offer
    however suggestively its folder is named."""
    write_folder(tmp_path / "Darks", 20, imagetyp=None)

    assert discover.find_calibration_folders(tmp_path) == []


def test_a_folder_named_darks_full_of_lights_is_not_offered(tmp_path):
    """The frames decide, never the name."""
    write_folder(tmp_path / "darks", 20, imagetyp="Light")

    assert discover.find_calibration_folders(tmp_path) == []


def test_a_mixed_folder_is_not_offered(tmp_path):
    """Half darks, half subs: we don't know what a master built from it would
    be, so we don't offer one."""
    folder = tmp_path / "Mixed"
    for i in range(10):
        write_frame(folder / f"a_{i:03d}.fit", imagetyp="Dark")
    for i in range(10):
        write_frame(folder / f"z_{i:03d}.fit", imagetyp="Light")

    assert discover.find_calibration_folders(tmp_path) == []


def test_one_undeclared_frame_in_the_sample_silences_the_offer(tmp_path):
    folder = tmp_path / "Dark"
    write_folder(folder, 10, imagetyp="Dark")
    write_frame(folder / "zzz_last.fit", imagetyp=None)

    assert discover.find_calibration_folders(tmp_path) == []


def test_too_few_frames_is_not_offered(tmp_path):
    write_folder(tmp_path / "Dark", discover.MIN_FRAMES - 1, imagetyp="Dark")

    assert discover.find_calibration_folders(tmp_path) == []


def test_flats_and_bias_get_their_own_slots(tmp_path):
    write_folder(tmp_path / "Flat", 6, imagetyp="Flat Field")
    write_folder(tmp_path / "Bias", 6, imagetyp="Bias Frame", exposure_s=0.001)

    found = {f.kind: f for f in discover.find_calibration_folders(tmp_path)}

    assert set(found) == {"flat", "bias"}
    assert found["flat"].folder_name == "Flat"
    assert found["bias"].folder_name == "Bias"


def test_flat_darks_fill_the_dark_slot_but_keep_their_own_word(tmp_path):
    """A flat-dark is physically a dark, so it belongs in the dark slot — but the
    tally echoes what the frames actually said rather than relabelling them."""
    write_folder(tmp_path / "FlatDark", 6, imagetyp="Flat Dark")

    (f,) = discover.find_calibration_folders(tmp_path)

    assert f.kind == "dark"
    assert set(f.declared) == {"dark_flat"}


def test_darks_and_flat_darks_together_still_fill_the_dark_slot(tmp_path):
    folder = tmp_path / "Dark"
    for i in range(6):
        write_frame(folder / f"a_{i:03d}.fit", imagetyp="Dark")
    for i in range(6):
        write_frame(folder / f"z_{i:03d}.fit", imagetyp="Dark Flat")

    (f,) = discover.find_calibration_folders(tmp_path)

    assert f.kind == "dark"
    assert set(f.declared) == {"dark", "dark_flat"}


def test_a_nested_folder_one_level_down_is_found(tmp_path):
    write_folder(tmp_path / "2026-09-01" / "Dark", 6, imagetyp="Dark")

    (f,) = discover.find_calibration_folders(tmp_path)

    assert f.rel_path == "2026-09-01/Dark"
    assert f.id == "2026-09-01_Dark"


def test_nothing_below_the_depth_limit_is_walked(tmp_path):
    write_folder(tmp_path / "a" / "b" / "Dark", 6, imagetyp="Dark")

    assert discover.find_calibration_folders(tmp_path) == []


def test_two_folders_of_the_same_name_get_distinct_ids(tmp_path):
    write_folder(tmp_path / "n1" / "Dark", 6, imagetyp="Dark")
    write_folder(tmp_path / "n2" / "Dark", 6, imagetyp="Dark")

    found = discover.find_calibration_folders(tmp_path)

    assert len(found) == 2
    assert len({f.id for f in found}) == 2


def test_a_missing_root_is_empty_not_an_error(tmp_path):
    assert discover.find_calibration_folders(tmp_path / "nope") == []


def test_ordinary_target_folders_cost_one_header_read_each(tmp_path):
    """The cheap-common-case guarantee: a library of light-sub folders must not
    turn a page load into a header read per frame."""
    for n in range(6):
        write_folder(tmp_path / f"target_{n}", 30, imagetyp="Light")

    reads: list[Path] = []
    real = discover  # module-level import of load_header happens inside

    def counting_load_header(path):
        reads.append(Path(path))
        from seestack.io.fits_loader import load_header
        return load_header(path)

    assert real.find_calibration_folders(
        tmp_path, load_header=counting_load_header) == []
    assert len(reads) == 6


def test_find_one_by_id_round_trips(tmp_path):
    write_folder(tmp_path / "Dark", 6, imagetyp="Dark")
    (f,) = discover.find_calibration_folders(tmp_path)

    assert discover.find_calibration_folder(tmp_path, f.id) == f
    assert discover.find_calibration_folder(tmp_path, "not-a-folder") is None


def test_suggested_name_reads_like_something_you_can_tell_apart(tmp_path):
    write_folder(tmp_path / "Dark", 6, imagetyp="Dark",
                 exposure_s=30.0, gain=80.0, temp_c=-5.0)
    (f,) = discover.find_calibration_folders(tmp_path)

    assert discover.suggested_master_name(f) == "Dark 30s gain 80 −5°C"


def test_suggested_name_falls_back_to_the_folder_when_nothing_was_recorded():
    bare = discover.CalibrationFolder(
        id="x", folder_name="Dark_2026", rel_path="Dark_2026", folder="/x",
        kind="dark", declared={"dark": 4}, n_frames=9, n_sampled=4,
        exposure_s=None, gain=None, sensor_temp_c=None,
        width_px=None, height_px=None,
    )

    assert discover.suggested_master_name(bare) == "Dark Dark_2026"


def test_sample_indices_span_the_folder():
    """Evenly spaced, first one first — so the single-header rule-out reads a
    file that is definitely there and the rest catch a set that changes kind."""
    assert discover._sample_indices(3, 4) == [0, 1, 2]
    assert discover._sample_indices(100, 4) == [0, 33, 66, 99]
    assert discover._sample_indices(10, 1) == [0]
