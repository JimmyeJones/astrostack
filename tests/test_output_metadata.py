"""FITS export carries a self-describing integration/instrument summary.

The scientific ``master.fits`` used to be an anonymous pixel cube; downstream
tools (Siril, PixInsight) and the user should be able to read how many subs
were combined and the total integration straight from the header. These tests
lock the header cards produced by :func:`build_stack_header_meta` and verify
they actually land in the written FITS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from seestack.stack.output import build_stack_header_meta, write_stack_outputs


@dataclass
class _Frame:
    exposure_s: float | None = None
    gain: float | None = None
    sensor_temp_c: float | None = None
    timestamp_utc: str | None = None


def test_meta_summarises_exposure_and_instrument():
    frames = [
        _Frame(exposure_s=10.0, gain=80.0, sensor_temp_c=-5.0, timestamp_utc="2024-01-01T00:00:00Z"),
        _Frame(exposure_s=10.0, gain=80.0, sensor_temp_c=-5.5, timestamp_utc="2024-01-01T00:10:00Z"),
        _Frame(exposure_s=10.0, gain=80.0, sensor_temp_c=-4.5, timestamp_utc="2024-01-01T00:05:00Z"),
    ]
    meta = build_stack_header_meta(frames, n_used=3, method="sigma-clip kappa=3", mono=False)

    assert meta["NCOMBINE"][0] == 3
    assert meta["EXPTIME"][0] == 10.0
    # Total integration = median sub (10s) × frames combined (3).
    assert meta["TOTALEXP"][0] == 30.0
    assert meta["GAIN"][0] == 80.0
    assert meta["CCD-TEMP"][0] == -5.0  # median of -5, -5.5, -4.5
    # Obs window is the sorted timestamp range, not input order.
    assert meta["DATE-OBS"][0] == "2024-01-01T00:00:00Z"
    assert meta["DATE-END"][0] == "2024-01-01T00:10:00Z"
    assert meta["STACKMTD"][0] == "sigma-clip kappa=3"
    assert meta["CFA"][0] is True  # colour (not mono)


def test_total_exposure_counts_only_combined_frames():
    # 5 accepted frames, but only 3 actually reprojected/combined.
    frames = [_Frame(exposure_s=30.0) for _ in range(5)]
    meta = build_stack_header_meta(frames, n_used=3)
    assert meta["NCOMBINE"][0] == 3
    assert meta["TOTALEXP"][0] == 90.0  # 30s × 3, not × 5


def test_meta_degrades_gracefully_without_exposure_data():
    # Synthetic frames with no exposure/gain/temp/timestamp yield just the count.
    frames = [_Frame() for _ in range(4)]
    meta = build_stack_header_meta(frames, n_used=4)
    assert meta["NCOMBINE"][0] == 4
    for absent in ("EXPTIME", "TOTALEXP", "GAIN", "CCD-TEMP", "DATE-OBS", "DATE-END"):
        assert absent not in meta


def test_meta_ignores_nan_and_missing_values():
    frames = [
        _Frame(exposure_s=10.0, gain=float("nan")),
        _Frame(exposure_s=float("nan"), gain=100.0),
        _Frame(exposure_s=10.0),
    ]
    meta = build_stack_header_meta(frames, n_used=3)
    # Only the two finite exposures feed the median.
    assert meta["EXPTIME"][0] == 10.0
    assert meta["GAIN"][0] == 100.0


def test_mono_sets_cfa_false():
    meta = build_stack_header_meta([_Frame(exposure_s=5.0)], n_used=1, mono=True)
    assert meta["CFA"][0] is False


def test_metadata_written_into_fits_header(tmp_path):
    from astropy.io import fits

    frames = [
        _Frame(exposure_s=15.0, gain=120.0, timestamp_utc="2024-03-01T22:00:00Z"),
        _Frame(exposure_s=15.0, gain=120.0, timestamp_utc="2024-03-01T22:30:00Z"),
    ]
    meta = build_stack_header_meta(frames, n_used=2, method="drizzle pixfrac=0.8 scale=1.5", mono=False)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    coverage = np.ones((8, 8), dtype=np.float32)
    paths = write_stack_outputs(
        project_dir=project_dir,
        rgb=rgb,
        coverage=coverage,
        wcs_text=None,
        meta=meta,
    )

    header = fits.getheader(paths["fits"])
    assert header["NCOMBINE"] == 2
    assert header["EXPTIME"] == 15.0
    assert header["TOTALEXP"] == 30.0
    assert header["GAIN"] == 120.0
    assert header["DATE-OBS"] == "2024-03-01T22:00:00Z"
    assert header["STACKMTD"].startswith("drizzle")


def test_write_stack_outputs_meta_is_optional(tmp_path):
    # Back-compat: callers that don't pass meta still get a valid FITS.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    rgb = np.zeros((4, 4, 3), dtype=np.float32)
    coverage = np.ones((4, 4), dtype=np.float32)
    paths = write_stack_outputs(
        project_dir=project_dir, rgb=rgb, coverage=coverage, wcs_text=None,
    )
    from astropy.io import fits

    header = fits.getheader(paths["fits"])
    assert "NCOMBINE" not in header  # nothing forced when no meta supplied
    assert header["CREATOR"] == "Seestack"
