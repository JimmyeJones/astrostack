"""Drizzle deposit bookkeeping is confined to the frame's own window
(audit 2026-11-26 perf I-3) and stays bit-identical to the full-canvas version.

``DrizzleStacker.add_frame`` used to snapshot, compare and add over the *whole*
output canvas three times a sub. On a mosaic canvas one sub covers ~1/20 of
it, so that bookkeeping cost 0.6–1.5 s a sub. It now works on the window the
frame can reach. These tests pin that the frame-count map, the image and the
weights are exactly what the full-canvas version produces, for every kernel,
several drizzle scales, rotated frames, frames hanging off the canvas edge,
and a frame entirely off the canvas.
"""
import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("drizzle")

from astropy.wcs import WCS  # noqa: E402

from seestack.stack import drizzle_path  # noqa: E402
from seestack.stack.drizzle_path import DrizzleParams, DrizzleStacker  # noqa: E402

SCALE_ARCSEC = 5.0


def _wcs(width: int, height: int, *, dx_px: float = 0.0, dy_px: float = 0.0,
         rot_deg: float = 0.0) -> WCS:
    """A TAN WCS whose centre sits ``(dx_px, dy_px)`` reference pixels away
    from the canvas centre, rotated by ``rot_deg``."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    s = SCALE_ARCSEC / 3600.0
    w.wcs.crval = [83.6 - dx_px * s, -5.4 + dy_px * s]
    w.wcs.crpix = [width / 2 + 0.5, height / 2 + 0.5]
    t = np.deg2rad(rot_deg)
    w.wcs.cd = np.array([[-s * np.cos(t), s * np.sin(t)],
                         [s * np.sin(t), s * np.cos(t)]])
    return w


# (dx, dy, rotation): inside, over the left edge, over a corner, rotated over
# the bottom edge, and entirely off the canvas (deposits nothing).
PLACEMENTS = [(0, 0, 0.0), (-80, 10, 3.0), (85, -60, 0.0), (20, 75, 27.0),
              (400, 0, 0.0)]


def _run(params: DrizzleParams, *, full_canvas: bool, clip: bool,
         monkeypatch) -> DrizzleStacker:
    canvas = (120, 160)
    ref = _wcs(canvas[1], canvas[0])
    if full_canvas:
        monkeypatch.setattr(
            drizzle_path, "_deposit_window",
            lambda pm, ib, shape, scale: ((slice(0, shape[0]), slice(0, shape[1]))
                                          if ib.any() else None))
    else:
        monkeypatch.undo()
    rng = np.random.default_rng(7)
    frames = []
    for dx, dy, rot in PLACEMENTS:
        rgb = (rng.random((50, 70, 3)) * 100 + 50).astype(np.float32)
        rgb[3:6, 10:14, 1] = np.nan          # a little no-data
        rgb[20, 30, :] = 5000.0               # an outlier for the clip to drop
        frames.append((rgb, _wcs(70, 50, dx_px=dx, dy_px=dy, rot_deg=rot)))
    if clip:
        stats = DrizzleStacker(ref, canvas, params, compute_stats=True)
        for rgb, w in frames:
            stats.add_frame(rgb, w)
        ref_clip = stats.clip_reference(3.0)
    out = DrizzleStacker(ref, canvas, params, record_rejection_map=clip)
    for i, (rgb, w) in enumerate(frames):
        out.add_frame(rgb, w, weight=1.0 + 0.1 * i,
                      clip=ref_clip if clip else None)
    return out


@pytest.mark.parametrize("kernel", ["square", "turbo", "gaussian", "lanczos2", "lanczos3"])
@pytest.mark.parametrize("scale,pixfrac", [(1.0, 1.0), (1.5, 0.8), (2.0, 0.6), (3.0, 1.0)])
def test_window_bookkeeping_matches_the_full_canvas(kernel, scale, pixfrac, monkeypatch):
    if kernel.startswith("lanczos") and pixfrac != 1.0:
        pytest.skip("the drizzle library requires pixfrac=1 for lanczos kernels")
    params = DrizzleParams(scale=scale, pixfrac=pixfrac, kernel=kernel)
    for clip in (False, True):
        full = _run(params, full_canvas=True, clip=clip, monkeypatch=monkeypatch)
        win = _run(params, full_canvas=False, clip=clip, monkeypatch=monkeypatch)
        assert full.frame_coverage.max() > 0
        np.testing.assert_array_equal(win.frame_coverage, full.frame_coverage)
        np.testing.assert_array_equal(win.coverage, full.coverage)
        np.testing.assert_array_equal(win.result(), full.result())
        assert win.rejection_counts() == full.rejection_counts()


def test_the_window_is_much_smaller_than_a_mosaic_canvas():
    """The point of the change: one sub's window is its own footprint, not
    the canvas."""
    canvas = (600, 900)
    ref = _wcs(canvas[1], canvas[0])
    st = DrizzleStacker(ref, canvas, DrizzleParams(scale=1.0, pixfrac=1.0))
    pm = drizzle_path._build_pixmap(_wcs(70, 50, dx_px=200, dy_px=100), st.out_wcs, 50, 70)
    h, w = st.out_shape
    ib = ((pm[..., 0] >= -0.5) & (pm[..., 0] <= w - 0.5)
          & (pm[..., 1] >= -0.5) & (pm[..., 1] <= h - 0.5))
    wy, wx = drizzle_path._deposit_window(pm, ib, st.out_shape, 1.0)
    area = (wy.stop - wy.start) * (wx.stop - wx.start)
    assert area < 0.02 * h * w


def test_the_stack_builds_each_pixmap_on_a_worker_not_the_consumer(tmp_path, monkeypatch):
    """perf I-3's other half: the pixmap is pure per-frame work, so the drizzle
    pass builds it on the worker threads and hands it to ``add_frame`` — the
    serial consumer no longer pays ~0.65 s a sub for it."""
    import threading

    from seestack.stack.stacker import StackOptions, run_stack
    from tests.test_drizzle import _build_project

    built_on: list[int] = []
    handed: list[bool] = []
    real_pixmap_for = DrizzleStacker.pixmap_for
    real_add = DrizzleStacker.add_frame

    def spy_pixmap_for(self, in_wcs, in_shape):
        built_on.append(threading.get_ident())
        return real_pixmap_for(self, in_wcs, in_shape)

    def spy_add(self, rgb, in_wcs, **kw):
        handed.append(kw.get("pixmap") is not None)
        return real_add(self, rgb, in_wcs, **kw)

    monkeypatch.setattr(DrizzleStacker, "pixmap_for", spy_pixmap_for)
    monkeypatch.setattr(DrizzleStacker, "add_frame", spy_add)
    consumer = threading.get_ident()
    proj = _build_project(tmp_path, n=3)
    try:
        result = run_stack(proj, StackOptions(
            drizzle=True, drizzle_scale=1.5, drizzle_pixfrac=0.8,
            background_flatten=False, max_workers=2, output_name="driz"))
    finally:
        proj.close()
    assert result.n_frames_used == 3
    assert handed and all(handed)
    assert built_on and consumer not in built_on


def test_the_in_flight_bound_charges_the_pixmap_on_drizzle():
    """Each in-flight drizzle payload now carries a float64 (x, y) pixmap
    (16 B/px) beside its RGB float32 frame (12 B/px); the worker-buffer cap must
    charge both, or the move could OOM a run the guard passed."""
    from seestack.stack.stacker import _estimate_peak_bytes, _memory_bounded_in_flight

    big = (4000, 6000)
    budget_gb = 4.0
    peak, _ = _estimate_peak_bytes(big, drizzle=True, drizzle_scale=1.0)
    want = int((budget_gb * 1e9 - peak) // (big[0] * big[1] * (12 + 16)))
    got = _memory_bounded_in_flight(big, big, max_in_flight=64, drizzle=True,
                                    drizzle_scale=1.0, memory_budget_gb=budget_gb)
    assert got == max(2, want)
    assert got < _memory_bounded_in_flight(big, big, max_in_flight=64,
                                           memory_budget_gb=budget_gb)
