"""The frame depth at the crop the noise ratio was measured over.

The √N yardstick and the measurement have to describe the same pixels. On a
single field they always do; on a **mosaic** they never did — the ratio's central
crop only ever saw its own panel's subs while ``n_frames_used`` counts the whole
target's, so a healthy four-panel mosaic 100 subs deep per panel achieved √100
and was asked for √400. v0.331.2 fixed that false alarm by *silence*, because
nothing recorded the crop's own depth. These tests pin the honest version: the
depth read off the per-pixel frame-count sibling the run already wrote, over
exactly the crop ``_crop_origin`` takes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow

_CANVAS = (320, 480)


def _write_linear_master(path: Path, *, sigma: float = 2.0,
                         shape=_CANVAS, seed: int = 0, channels: int = 3) -> None:
    """A linear master of the given canvas — 3-channel like a real one, or 2-D
    when a test only needs the canvas shape and wants it cheap."""
    rng = np.random.default_rng(seed)
    size = (channels, *shape) if channels > 1 else shape
    fits.PrimaryHDU(
        data=rng.normal(100.0, sigma, size=size).astype(np.float32),
    ).writeto(path, overwrite=True)


def _write_framecov(master: Path, counts: np.ndarray) -> Path:
    """Write the per-pixel frame-count sibling beside ``master``."""
    from seestack.edit.proxy import frame_coverage_path_for

    path = frame_coverage_path_for(master)
    fits.PrimaryHDU(data=counts.astype(np.float32)).writeto(path, overwrite=True)
    return path


def _register_run(data_root, safe: str, master: Path, *,
                  is_mosaic: bool | None = False, n_frames_used: int = 400) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(master), tiff_path=None,
                preview_path=None, n_frames_used=n_frames_used,
                canvas_h=_CANVAS[0], canvas_w=_CANVAS[1],
                coverage_min=1, coverage_max=n_frames_used,
                # A real StackOptions shape — the "How's my stack?" panel only
                # grades runs that parse as a genuine stack.
                options_json=json.dumps({"output_name": "master"}),
                total_exposure_s=1260.0, is_mosaic=is_mosaic,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _master_path(data_root, safe: str, name: str) -> Path:
    lib = Library.open_or_create(data_root / "library")
    try:
        return Path(lib.target_dir(lib.find_target(safe))) / name
    finally:
        lib.close()


def _fixed_ratio(monkeypatch, value: float | None):
    """Pin the measured ratio so a test can assert the *verdict* rather than a
    property of whatever noise the synthetic master happens to carry."""
    from webapp.routers import stack as stack_router

    monkeypatch.setattr(stack_router, "_measure_noise_ratio",
                        lambda *a, **kw: value)


# ---- the measurement itself -------------------------------------------------

def test_the_crop_depth_is_the_median_over_the_crop_not_the_deepest_pixel(tmp_path):
    """``coverage_max`` is the deepest pixel *anywhere* on the canvas, so on a
    lopsided mosaic — a 200-sub panel outside the crop, a 100-sub one inside —
    it over-expects and puts the false alarm straight back, just less often. The
    honest number is the depth of the pixels the ratio actually rests on."""
    from webapp.routers.stack import _NOISE_CROP_PX, _crop_origin, _measure_crop_depth

    shape = (1400, 1400)
    master = tmp_path / "wide.fits"
    _write_linear_master(master, shape=shape, channels=1)
    counts = np.full(shape, 200.0, dtype=np.float32)
    y0, x0 = _crop_origin(*shape)
    counts[y0:y0 + _NOISE_CROP_PX, x0:x0 + _NOISE_CROP_PX] = 100.0
    _write_framecov(master, counts)

    assert _measure_crop_depth(str(master)) == 100
    # …and the number a naive `coverage_max` would have used is genuinely there
    # to be picked wrongly.
    assert float(counts.max()) == 200.0


def test_uncovered_pixels_are_not_counted_as_zero_subs_deep(tmp_path):
    """NaN is "no coverage", not "no frames" — the engine's standing rule. Half a
    crop with nothing in it must not halve the depth of the half that has."""
    from webapp.routers.stack import _measure_crop_depth

    master = tmp_path / "half.fits"
    _write_linear_master(master, channels=1)
    counts = np.full(_CANVAS, 60.0, dtype=np.float32)
    counts[:, : _CANVAS[1] // 4] = 0.0
    counts[:, _CANVAS[1] // 4: _CANVAS[1] // 2] = np.nan
    _write_framecov(master, counts)

    assert _measure_crop_depth(str(master)) == 60


def test_no_coverage_sibling_means_no_depth(tmp_path):
    """Every run stacked before the sibling existed, and every tidied output
    dir. The mosaic stays exactly as silent as it is today."""
    from webapp.routers.stack import _measure_crop_depth

    master = tmp_path / "bare.fits"
    _write_linear_master(master, channels=1)
    assert _measure_crop_depth(str(master)) is None


def test_a_sibling_from_a_different_canvas_is_refused(tmp_path):
    """A hand-tidied output dir or a restored backup can leave a coverage map
    from another picture beside this one. Judging one image by another's map is
    worse than saying nothing."""
    from webapp.routers.stack import _measure_crop_depth

    master = tmp_path / "mismatch.fits"
    _write_linear_master(master, channels=1)
    _write_framecov(master, np.full((64, 64), 50.0, dtype=np.float32))
    assert _measure_crop_depth(str(master)) is None


def test_an_entirely_uncovered_crop_declines(tmp_path):
    from webapp.routers.stack import _measure_crop_depth

    master = tmp_path / "empty.fits"
    _write_linear_master(master, channels=1)
    _write_framecov(master, np.zeros(_CANVAS, dtype=np.float32))
    assert _measure_crop_depth(str(master)) is None


def test_an_unreadable_sibling_declines_rather_than_raising(tmp_path):
    from seestack.edit.proxy import frame_coverage_path_for
    from webapp.routers.stack import _measure_crop_depth

    master = tmp_path / "broken.fits"
    _write_linear_master(master, channels=1)
    frame_coverage_path_for(master).write_bytes(b"not a FITS file at all")
    assert _measure_crop_depth(str(master)) is None


# ---- what the endpoint does with it -----------------------------------------

def test_a_healthy_mosaic_is_told_it_is_healthy(client, solved_library, monkeypatch):
    """The whole point: the four-panel shape that read "low" at every depth now
    reads "expected" — judged against the 100 subs on the crop, not the 400 on
    the target."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "mosaic_ok.fits")
    _write_linear_master(master)
    _write_framecov(master, np.full(_CANVAS, 100.0, dtype=np.float32))
    run_id = _register_run(solved_library, safe, master, is_mosaic=True,
                           n_frames_used=400)
    _fixed_ratio(monkeypatch, 10.0)

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise").json()
    assert body["expected_verdict"] == "expected"
    assert body["expected_frames"] == 100
    assert body["expected_basis"] == "mosaic_centre"


def test_a_mosaic_that_really_did_underperform_still_says_so(
    client, solved_library, monkeypatch,
):
    """The suppression must not have become a blanket amnesty — a mosaic 100
    subs deep that only managed 4× is genuinely worth a word."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "mosaic_low.fits")
    _write_linear_master(master)
    _write_framecov(master, np.full(_CANVAS, 100.0, dtype=np.float32))
    run_id = _register_run(solved_library, safe, master, is_mosaic=True,
                           n_frames_used=400)
    _fixed_ratio(monkeypatch, 4.0)

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise").json()
    assert body["expected_verdict"] == "low"
    assert body["expected_frames"] == 100


def test_a_mosaic_with_no_coverage_sibling_is_still_withheld(
    client, solved_library, monkeypatch,
):
    """No depth, no verdict — the v0.331.2 behaviour, kept for every run whose
    map is gone."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "mosaic_bare.fits")
    _write_linear_master(master)
    run_id = _register_run(solved_library, safe, master, is_mosaic=True,
                           n_frames_used=400)
    _fixed_ratio(monkeypatch, 10.0)

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise").json()
    assert body["ratio"] == 10.0          # the number itself is still served
    assert body["expected_verdict"] is None
    assert body["expected_frames"] is None
    assert body["expected_basis"] is None


def test_a_single_field_is_judged_on_its_own_frame_count_and_reads_no_sibling(
    client, solved_library, monkeypatch,
):
    """Upgrade safety at the endpoint: a single field's verdict is what it always
    was, and it must not pay for a measurement only mosaics use — a coverage map
    sitting beside it is never even opened."""
    from webapp.routers import stack as stack_router

    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "single.fits")
    _write_linear_master(master)
    # A sibling that would give a *different* answer if it were consulted.
    _write_framecov(master, np.full(_CANVAS, 9.0, dtype=np.float32))
    run_id = _register_run(solved_library, safe, master, is_mosaic=False,
                           n_frames_used=100)
    _fixed_ratio(monkeypatch, 10.0)
    opened: list[str] = []
    real = stack_router._measure_crop_depth
    monkeypatch.setattr(stack_router, "_measure_crop_depth",
                        lambda p: (opened.append(p), real(p))[1])

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise").json()
    assert body["expected_verdict"] == "expected"
    assert body["expected_frames"] == 100
    assert body["expected_basis"] == "stack"
    assert opened == []


def test_an_older_stamp_gains_its_depth_without_re_measuring_the_ratio(
    client, solved_library, monkeypatch,
):
    """A stamp written before the depth existed is a *hit*, not a miss: the ratio
    it carries is as good as it ever was. The mosaic heals on the one request
    that needs the depth — one windowed read of a map already on disk, never a
    re-debayer of a full-resolution sub."""
    from webapp.routers import stack as stack_router
    from webapp.routers.stack import NOISE_RATIO_META_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "mosaic_heal.fits")
    _write_linear_master(master)
    _write_framecov(master, np.full(_CANVAS, 144.0, dtype=np.float32))
    run_id = _register_run(solved_library, safe, master, is_mosaic=True,
                           n_frames_used=400)

    measurements: list[int] = []
    monkeypatch.setattr(
        stack_router, "_measure_noise_ratio",
        lambda *a, **kw: (measurements.append(1), 12.0)[1])

    url = f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise"
    first = client.get(url).json()
    assert first["expected_frames"] == 144
    assert len(measurements) == 1

    # Now forge the pre-depth stamp shape (v0.331.2 and earlier): same
    # fingerprint, ratio present, no `crop_depth` key at all.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            key = f"{NOISE_RATIO_META_PREFIX}{run_id}"
            stamp = json.loads(proj.get_meta(key))
            stamp.pop("crop_depth", None)
            proj.set_meta(key, json.dumps(stamp))
        finally:
            proj.close()
    finally:
        lib.close()

    measurements.clear()
    healed = client.get(url).json()
    # The ratio came off the stamp — no second measurement — and the depth was
    # filled in from the sibling.
    assert measurements == []
    assert healed["ratio"] == 12.0
    assert healed["expected_frames"] == 144
    assert healed["expected_verdict"] == "expected"

    # …and it was written back, so the next view reads it rather than the map.
    depths: list[str] = []
    real = stack_router._measure_crop_depth
    monkeypatch.setattr(stack_router, "_measure_crop_depth",
                        lambda p: (depths.append(p), real(p))[1])
    again = client.get(url).json()
    assert again["expected_frames"] == 144
    assert depths == []


# ---- the canvas flag the celebratory badge needs ----------------------------
#
# `expected_basis` only exists when a *verdict* does, and a mosaic whose coverage
# map is gone has no verdict — but the badge above the yardstick sentence still
# credits the ratio to a sub count, and on any mosaic that count is the whole
# target's while the measurement is one panel's. So the raw canvas flag is served
# in its own right, on every path.

def test_the_canvas_flag_is_served_even_when_the_verdict_is_withheld(
    client, solved_library, monkeypatch,
):
    """The mosaic the yardstick stays silent about is exactly the one the badge
    must not congratulate on 400 subs."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "mosaic_flag_bare.fits")
    _write_linear_master(master)          # no coverage sibling → no depth
    run_id = _register_run(solved_library, safe, master, is_mosaic=True,
                           n_frames_used=400)
    _fixed_ratio(monkeypatch, 10.0)

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise").json()
    assert body["expected_basis"] is None      # nothing to judge against…
    assert body["is_mosaic"] is True           # …but the canvas is still known


def test_a_single_field_says_so_and_an_older_run_says_nothing(
    client, solved_library, monkeypatch,
):
    """`false` is a fact the badge acts on (keep the count); `null` — a run
    stacked before schema 8 — is an absence it must not read as either."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    single = _master_path(solved_library, safe, "flag_single.fits")
    _write_linear_master(single)
    single_id = _register_run(solved_library, safe, single, is_mosaic=False,
                              n_frames_used=100)
    legacy = _master_path(solved_library, safe, "flag_legacy.fits")
    _write_linear_master(legacy)
    legacy_id = _register_run(solved_library, safe, legacy, is_mosaic=None,
                              n_frames_used=100)
    _fixed_ratio(monkeypatch, 10.0)

    base = f"/api/targets/{safe}/stack-runs"
    assert client.get(
        f"{base}/{single_id}/one-sub-vs-stack/noise").json()["is_mosaic"] is False
    assert client.get(
        f"{base}/{legacy_id}/one-sub-vs-stack/noise").json()["is_mosaic"] is None


def test_the_health_note_reads_the_same_depth_the_card_does(
    client, solved_library, monkeypatch,
):
    """One measurement, two surfaces. "How's my stack?" never measures — it reads
    the stamp the reveal card left — so this also pins that the depth travels on
    that stamp rather than being re-derived on a page render."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_path(solved_library, safe, "mosaic_note.fits")
    _write_linear_master(master)
    _write_framecov(master, np.full(_CANVAS, 100.0, dtype=np.float32))
    run_id = _register_run(solved_library, safe, master, is_mosaic=True,
                           n_frames_used=400)
    _fixed_ratio(monkeypatch, 4.0)

    # Before anything measures, the panel says nothing about noise.
    health = client.get(
        f"/api/targets/{safe}/stack-health?run_id={run_id}").json()
    assert "noise_low" not in [n["kind"] for n in health["notes"]]

    client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise")

    health = client.get(
        f"/api/targets/{safe}/stack-health?run_id={run_id}").json()
    note = next((n for n in health["notes"] if n["kind"] == "noise_low"), None)
    assert note is not None
    # The panel depth, in plain words — and never the target's 400.
    assert "About 100 subs cover the middle of this mosaic" in note["message"]
    assert "400" not in note["message"]
