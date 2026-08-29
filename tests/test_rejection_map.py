""""See what stacking removed": the per-pixel rejection map
(``StackOptions.record_rejection_map``).

The header has always carried *how much* outlier rejection clipped (``REJFRAC``
— "sigma clipping dropped 0.3% of samples"). These tests pin down the other
half: **where**. When asked, a run records a per-pixel count of the samples
rejection dropped and writes it beside the picture as ``{base}_rejected.fits``,
so the app can lay the satellite trails and cosmic rays it quietly removed over
the finished image.

The properties that matter, in order:

* it lands **on the trail** — a planted satellite streak, on both data-driven
  rejection paths (κ-σ and two-pass drizzle);
* it is **purely observational** — the picture is bit-for-bit what it would have
  been without it;
* it is **off by default**, and a run that records nothing writes no sibling
  (which every consumer reads as "no overlay available");
* the extra plane is **charged through the OOM guard**, at its true size.
"""

from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.edit.proxy import rejection_map_path_for  # noqa: E402
from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.output import RUN_ARTEFACT_SUFFIXES  # noqa: E402
from seestack.stack.stacker import (  # noqa: E402
    StackOptions,
    _estimate_peak_bytes,
    _records_rejection_map,
    run_stack,
)

# ---- fixtures ------------------------------------------------------------

def _build_project(tmp_path, frames_spec) -> Project:
    """A project of synthetic Seestar subs — the same shape the drizzle-reject
    suite uses, so the planted-trail geometry below is the proven one."""
    from tests.synth import make_synth_wcs_text as _wcs_text
    from tests.synth import write_seestar_fits

    proj = Project.create(tmp_path / "p", name="rejmap_test")
    raws = tmp_path / "raws"
    raws.mkdir()
    for i, spec in enumerate(frames_spec):
        spec = dict(spec)
        shift = spec.pop("shift", (0.0, 0.0))
        path = write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, star_shift=shift, **spec,
        )
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=_wcs_text(crpix_shift=shift),
            ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    return proj


#: 16 subs, the ninth carrying a satellite streak along ``y = x + 10`` — the
#: exact scene ``test_drizzle_reject.test_e2e_satellite_trail_rejected`` proved
#: rejection actually cleans up, so a map of that rejection has a known answer.
_TRAIL_SPEC = [
    {"seed": 7, "noise_seed": 100 + i, "n_stars": 10, "streak": (i == 8)}
    for i in range(16)
]

_BASE_OPTS = dict(
    background_flatten=False, suppress_hot_pixels=False,
    max_workers=2, output_name="out",
)


def _run(tmp_path, spec, **overrides):
    """Stack ``spec`` and return ``(result, master_pixels, rejection_map|None)``."""
    from astropy.io import fits

    proj = _build_project(tmp_path, spec)
    try:
        result = run_stack(proj, StackOptions(**{**_BASE_OPTS, **overrides}))
    finally:
        proj.close()
    with fits.open(result.fits_path) as hdul:
        master = np.asarray(hdul[0].data, dtype=np.float32)
        header = dict(hdul[0].header)
    map_path = rejection_map_path_for(result.fits_path)
    rej = None
    if map_path.exists():
        with fits.open(map_path) as hdul:
            rej = np.asarray(hdul[0].data)
    return result, master, header, rej


def _trail_vs_offtrail(rej):
    """``(on_trail, off_trail)`` median drop counts, sampled along the planted
    streak and along a parallel line 30 columns to its right."""
    ts = list(range(60, 240, 12))
    on = float(np.median([rej[30 + t, 20 + t] for t in ts]))
    off = float(np.median([rej[30 + t, 50 + t] for t in ts]))
    return on, off


# ---- it lands on the trail ----------------------------------------------

def test_kappa_sigma_map_lands_on_the_planted_trail(tmp_path):
    """The κ-σ path's map marks the satellite streak and (almost) nothing else."""
    _r, _m, header, rej = _run(
        tmp_path, _TRAIL_SPEC, sigma_clip=True, record_rejection_map=True)
    assert rej is not None, "a run that asked to record should write the sibling"
    assert rej.dtype == np.uint16
    on, off = _trail_vs_offtrail(rej)
    assert on >= 1.0, f"the trail's pixels should carry a drop, got {on}"
    assert off == 0.0, f"clean sky should carry none, got {off}"
    assert header.get("REJMAP") is True


def test_drizzle_reject_map_lands_on_the_planted_trail(tmp_path):
    """…and so does the two-pass drizzle path's, in the drizzle output grid."""
    pytest.importorskip("drizzle")
    _r, _m, header, rej = _run(
        tmp_path, _TRAIL_SPEC,
        drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
        drizzle_reject=True, record_rejection_map=True)
    assert rej is not None
    on, off = _trail_vs_offtrail(rej)
    assert on >= 1.0, f"the trail's pixels should carry a drop, got {on}"
    assert off == 0.0, f"clean sky should carry none, got {off}"
    assert header.get("REJMAP") is True


# ---- it changes nothing --------------------------------------------------

def test_recording_does_not_change_a_single_pixel(tmp_path):
    """THE safety property. The map watches the same keep/drop decision the
    combine already applied, so the finished picture must be bit-for-bit what it
    would have been with the option off."""
    _r1, without, h_without, rej_off = _run(
        tmp_path / "off", _TRAIL_SPEC, sigma_clip=True)
    _r2, with_map, _h, rej_on = _run(
        tmp_path / "on", _TRAIL_SPEC, sigma_clip=True, record_rejection_map=True)
    assert rej_off is None, "off by default → no sibling, no card"
    assert "REJMAP" not in h_without
    assert rej_on is not None
    np.testing.assert_array_equal(without, with_map)


def test_off_by_default(tmp_path):
    """An unchanged StackOptions records nothing — every existing install's runs
    keep writing exactly the file set they always have."""
    assert StackOptions().record_rejection_map is False
    _r, _m, header, rej = _run(tmp_path, _TRAIL_SPEC[:6], sigma_clip=True)
    assert rej is None
    assert "REJMAP" not in header


# ---- the paths that deliberately record nothing --------------------------

def test_single_pass_drizzle_records_nothing(tmp_path):
    """No clip ran, so there is nothing to record — no sibling, and no card
    claiming an empty map."""
    pytest.importorskip("drizzle")
    _r, _m, header, rej = _run(
        tmp_path, _TRAIL_SPEC[:8],
        drizzle=True, drizzle_scale=1.0, drizzle_pixfrac=1.0,
        drizzle_reject=False, record_rejection_map=True)
    assert rej is None
    assert "REJMAP" not in header


def test_min_max_reject_records_nothing_deliberately(tmp_path):
    """Min/max's drop is *structural* — every pixel with ≥3 samples loses 2k of
    them — so a map of it is a flat wash over the whole canvas that would imply
    damage that isn't there. It is left unrecorded on purpose, not by omission."""
    _r, _m, header, rej = _run(
        tmp_path, _TRAIL_SPEC[:8],
        sigma_clip=False, min_max_reject=True, record_rejection_map=True)
    assert rej is None
    assert "REJMAP" not in header


def test_records_rejection_map_truth_table():
    """The one predicate the memory guard, the in-flight cap and the pre-submit
    estimate all read, so none of them can charge a plane the run doesn't
    allocate (or miss one it does)."""
    on = StackOptions(record_rejection_map=True)
    # κ-σ: needs the option, the method, and enough frames to reject at all.
    assert _records_rejection_map(on, 8) is True
    assert _records_rejection_map(on, 3) is False
    assert _records_rejection_map(StackOptions(), 8) is False
    assert _records_rejection_map(replace(on, sigma_clip=False), 8) is False
    # min/max takes precedence on the standard path and records nothing.
    assert _records_rejection_map(replace(on, min_max_reject=True), 8) is False
    # Drizzle: only the two-pass form has a clip to record.
    dz = replace(on, drizzle=True)
    assert _records_rejection_map(replace(dz, drizzle_reject=True), 8) is True
    assert _records_rejection_map(replace(dz, drizzle_reject=True), 3) is False
    assert _records_rejection_map(dz, 8) is False


# ---- memory --------------------------------------------------------------

def test_the_extra_plane_is_charged_at_its_true_size():
    """Charged, so asking for the overlay can't quietly OOM a run the guard just
    certified — but at 2 bytes/px, not rounded up to a whole RGB float32 array,
    which would price it at six times what it costs."""
    shape = (1000, 800)
    base, _ = _estimate_peak_bytes(shape, drizzle=False, drizzle_scale=1.0)
    with_map, _ = _estimate_peak_bytes(
        shape, drizzle=False, drizzle_scale=1.0, rejection_map=True)
    assert with_map - base == 1000 * 800 * 2
    # …and on the drizzle path it follows the *output* canvas, which is what is
    # actually allocated.
    dz_base, (out_h, out_w) = _estimate_peak_bytes(
        shape, drizzle=True, drizzle_scale=2.0)
    dz_map, _ = _estimate_peak_bytes(
        shape, drizzle=True, drizzle_scale=2.0, rejection_map=True)
    assert dz_map - dz_base == out_h * out_w * 2


# ---- the file, and the rest of the run's file set ------------------------

def test_an_all_zero_map_writes_no_file(tmp_path):
    """"Nothing was removed" is a real answer, but a canvas-sized file saying it
    is waste — and the absence already says exactly that."""
    from seestack.stack.output import write_stack_outputs

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    rgb = np.ones((8, 10, 3), dtype=np.float32)
    cov = np.ones((8, 10), dtype=np.float32)
    paths = write_stack_outputs(
        project_dir=proj_dir, rgb=rgb, coverage=cov, wcs_text=None,
        out_basename="m", rejection_map=np.zeros((8, 10), dtype=np.uint16))
    assert "rejection_map" not in paths
    assert not rejection_map_path_for(paths["fits"]).exists()

    paths = write_stack_outputs(
        project_dir=proj_dir, rgb=rgb, coverage=cov, wcs_text=None,
        out_basename="m2", rejection_map=np.array(
            [[0] * 10] * 7 + [[0, 0, 3] + [0] * 7], dtype=np.uint16))
    assert "rejection_map" in paths
    assert rejection_map_path_for(paths["fits"]).exists()


def test_the_sibling_is_part_of_the_runs_artefact_set():
    """So a re-stack archives it beside the picture it belongs to, instead of
    leaving the previous run's overlay pointing at the new run's pixels."""
    assert RUN_ARTEFACT_SUFFIXES["rejection_map"] == "_rejected.fits"


def test_rejection_map_path_resolves_from_the_fits_basename():
    from pathlib import Path

    assert rejection_map_path_for(Path("/x/output/master.fits")) == Path(
        "/x/output/master_rejected.fits")


# ---- how the map is drawn ------------------------------------------------

def _overlay_alpha(rej, size):
    """The alpha channel of :func:`rejection_overlay_png` for ``rej``."""
    import io

    from PIL import Image

    from seestack.render.thumbnail import rejection_overlay_png

    with Image.open(io.BytesIO(rejection_overlay_png(rej, size))) as im:
        assert im.mode == "RGBA"
        return np.array(np.asarray(im)[:, :, 3])


def test_a_lone_hot_pixel_does_not_hide_the_trail():
    """The property that decides whether the overlay is any use. A hot pixel is
    rejected in *every* sub, so scaling the tint against the map's maximum would
    make a satellite trail — rejected in one sub of many — as good as invisible.
    Scaling against a high percentile keeps the trail plainly visible and simply
    saturates the hot pixel."""
    rej = np.zeros((60, 60), dtype=np.uint16)
    for i in range(8, 52):
        rej[i, i] = 1                      # the trail: one sub
    rej[5, 40] = 200                       # a hot pixel: every sub, many times over
    alpha = _overlay_alpha(rej, (60, 60))
    assert min(int(alpha[i, i]) for i in range(8, 52)) > 200
    assert alpha[5, 40] == 255


def test_pixels_that_lost_nothing_stay_fully_transparent():
    """It is an *overlay*: the picture underneath must show through everywhere
    rejection didn't touch."""
    rej = np.zeros((40, 40), dtype=np.uint16)
    rej[20, 20] = 3
    alpha = _overlay_alpha(rej, (40, 40))
    assert alpha[20, 20] == 255
    alpha[19:22, 19:22] = 0
    assert alpha.max() == 0


def test_an_empty_map_draws_nothing_at_all():
    """"Rejection removed nothing" renders as a fully transparent layer, not as a
    divide-by-zero or a canvas-wide wash."""
    alpha = _overlay_alpha(np.zeros((16, 16), dtype=np.uint16), (16, 16))
    assert alpha.max() == 0


def test_shrinking_dilutes_speckle_but_keeps_a_trail():
    """Rejection legitimately clips a scattering of lone pixels (the tails of the
    noise), which are not what the user is being shown. Area-averaging the counts
    down onto the preview grid turns the map into a local *density*, so the dense
    line survives while isolated specks fade — the difference between an overlay
    that reads as "here is your satellite" and one that reads as static."""
    rng = np.random.default_rng(11)
    rej = np.zeros((160, 160), dtype=np.uint16)
    speck = rng.random((160, 160)) < 0.01
    rej[speck] = 1
    rej[np.arange(20, 140), np.arange(20, 140)] = 1   # the trail
    rej[np.arange(20, 140), np.arange(21, 141)] = 1   # …two pixels wide
    alpha = _overlay_alpha(rej, (40, 40))
    trail = np.array([alpha[i // 4, i // 4] for i in range(24, 136, 4)])
    off = alpha.copy()
    for i in range(20, 140):
        off[max(0, i // 4 - 1):i // 4 + 2, max(0, i // 4 - 1):i // 4 + 2] = 0
    assert trail.min() > int(off.max()), (
        f"the trail ({trail.min()}) must read stronger than the speckle ({off.max()})")
