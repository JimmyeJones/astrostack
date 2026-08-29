"""The all-sky "My map" — the whole sky drawn from the owner's own pictures alone.

Two rules carry the feature. **"Only map parts of images with enough detail"**:
each picture is masked by its own per-pixel frame count, so a mosaic's ragged
fringe fades out instead of smearing a noisy rectangle across the sky. And
**"rough"**: every picture is drawn larger than life by one *shared* factor, so
they are visible at all-sky scale while their relative sizes stay honest.
"""

from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg", force=True)

from seestack.edit.coverage_trim import well_covered_mask
from seestack.post.skymap import (
    DEFAULT_PICTURE_EXAGGERATION,
    MapPicture,
    SkyMapOptions,
    _drawn_half_width_deg,
    my_map_png,
    render_my_map,
)


def _rgba(w: int = 12, h: int = 8) -> np.ndarray:
    a = np.zeros((h, w, 4), dtype=np.uint8)
    a[..., :3] = 120
    a[..., 3] = 255
    return a


# ---- "enough detail" ----------------------------------------------------

def test_well_covered_mask_keeps_only_the_well_covered_pixels():
    """The same rule the editor's one-click border trim already uses: finite, and
    at least half the peak frame count."""
    cov = np.array([[0.0, 1.0, 4.0, 4.0],
                    [0.0, 2.0, 4.0, np.nan]], dtype=np.float32)
    mask = well_covered_mask(cov, 0.5)
    assert mask is not None
    assert mask.tolist() == [[False, False, True, True],
                             [False, True, True, False]]


def test_well_covered_mask_has_no_opinion_on_a_useless_map():
    assert well_covered_mask(np.zeros((4, 4), dtype=np.float32)) is None
    assert well_covered_mask(np.full((4, 4), np.nan, dtype=np.float32)) is None
    assert well_covered_mask(np.zeros((0, 0), dtype=np.float32)) is None
    assert well_covered_mask(np.zeros(4, dtype=np.float32)) is None   # not 2-D


def test_stack_detail_mask_is_stricter_than_the_has_data_footprint(tmp_path):
    """A mosaic's thin single-frame fringe *has* data but isn't worth mapping."""
    from astropy.io import fits

    from seestack.render.thumbnail import stack_coverage_mask, stack_detail_mask

    h, w = 10, 16
    cube = np.full((3, h, w), 0.3, dtype=np.float32)
    cube[:, :, :2] = np.nan                     # genuinely uncovered edge
    fp = tmp_path / "m.fits"
    fits.PrimaryHDU(data=cube).writeto(fp)

    counts = np.full((h, w), 8.0, dtype=np.float32)
    counts[:, 2:5] = 1.0                        # a thin, badly-covered fringe
    fits.PrimaryHDU(data=counts).writeto(tmp_path / "m_framecov.fits")

    covered = stack_coverage_mask(fp)
    detail = stack_detail_mask(fp)
    assert covered[:, 2:5].all()                # the fringe has data…
    assert not detail[:, 2:5].any()             # …but not enough of it
    assert detail[:, 5:].all()                  # the good interior survives
    assert not detail[:, :2].any()              # and NaN is still uncovered


def test_stack_detail_mask_falls_back_when_there_is_no_frame_count(tmp_path):
    """An older run with no ``_framecov`` sibling still maps its real shape
    rather than vanishing off the map."""
    from astropy.io import fits

    from seestack.render.thumbnail import stack_coverage_mask, stack_detail_mask

    cube = np.full((3, 6, 6), 0.3, dtype=np.float32)
    cube[:, 0, 0] = np.nan
    fp = tmp_path / "old.fits"
    fits.PrimaryHDU(data=cube).writeto(fp)
    assert np.array_equal(stack_detail_mask(fp), stack_coverage_mask(fp))


def test_overlay_rgba_array_matches_the_png_it_backs(tmp_path):
    """The array helper and the PNG helper must not drift — the map draws one and
    the sky overlay serves the other from the same pixels."""
    import io

    from PIL import Image

    from seestack.render.thumbnail import overlay_rgba_array, overlay_rgba_png

    buf = io.BytesIO()
    Image.fromarray(np.full((6, 9, 3), 77, dtype=np.uint8), mode="RGB").save(
        buf, format="PNG")
    mask = np.zeros((6, 9), dtype=bool)
    mask[2:5, 3:8] = True
    arr = overlay_rgba_array(buf.getvalue(), mask)
    from_png = np.asarray(Image.open(io.BytesIO(
        overlay_rgba_png(buf.getvalue(), mask))).convert("RGBA"))
    assert np.array_equal(arr, from_png)


# ---- "rough": one shared exaggeration -----------------------------------

def test_relative_sizes_stay_honest():
    """A six-panel mosaic really is drawn bigger than a single field — the whole
    point of one shared factor rather than a per-target fudge."""
    single = _drawn_half_width_deg(1.3, 0.7, DEFAULT_PICTURE_EXAGGERATION)
    mosaic = _drawn_half_width_deg(2.6, 1.4, DEFAULT_PICTURE_EXAGGERATION)
    assert mosaic > single


def test_a_picture_is_never_invisible_and_never_swamps_the_sky():
    tiny = _drawn_half_width_deg(0.02, 0.02, DEFAULT_PICTURE_EXAGGERATION)
    huge = _drawn_half_width_deg(40.0, 40.0, DEFAULT_PICTURE_EXAGGERATION)
    assert 1.0 < tiny * 2 <= 4.0            # at least the floor, in degrees
    assert huge * 2 <= 24.0                  # and capped well short of the sky


def test_the_drawn_shape_keeps_the_picture_s_aspect():
    """A wide picture stays wide: the clamp scales both edges together."""
    half_w = _drawn_half_width_deg(4.0, 1.0, DEFAULT_PICTURE_EXAGGERATION)
    # Long edge clamped to the ceiling; the width *is* the long edge here.
    assert half_w * 2 == pytest.approx(22.0, rel=1e-6)
    half_w_tall = _drawn_half_width_deg(1.0, 4.0, DEFAULT_PICTURE_EXAGGERATION)
    # Now the *height* is the long edge, so the drawn width is a quarter of it.
    assert half_w_tall * 2 == pytest.approx(22.0 / 4.0, rel=1e-6)


# ---- the renderer -------------------------------------------------------

def test_renders_an_empty_sky_without_raising():
    """A fresh install has no pictures; the map must still be a valid sky."""
    fig = render_my_map([])
    assert fig is not None


def test_places_every_picture_it_is_given():
    pics = [
        MapPicture("M 42", 83.8, -5.4, _rgba(), 1.3, 0.7),
        MapPicture("M 31", 10.7, 41.3, _rgba(20, 10), 2.6, 1.3),
    ]
    fig = render_my_map(pics, options=SkyMapOptions(title="t"), subtitle="s")
    ax = fig.axes[0]
    from matplotlib.offsetbox import AnnotationBbox

    boxes = [a for a in ax.artists if isinstance(a, AnnotationBbox)]
    assert len(boxes) == len(pics)
    # The bigger picture is drawn bigger on the map (same shared exaggeration).
    widths = [b.offsetbox.get_zoom() * b.offsetbox.get_data().shape[1]
              for b in boxes]
    assert widths[1] > widths[0]


def test_my_map_png_is_a_real_png():
    png = my_map_png([MapPicture("M 42", 83.8, -5.4, _rgba(), 1.3, 0.7)])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 5000            # a real all-sky figure, not a stub


def test_the_desktop_all_sky_map_is_untouched(tmp_path):
    """`render_skymap` is the existing Qt surface — "My map" is additive, so its
    signature and behaviour must be exactly as before."""
    from seestack.io.library import Library
    from seestack.post.skymap import render_skymap

    lib = Library.create(tmp_path / "lib")
    try:
        lib.create_target("M 42", ra_deg=83.6, dec_deg=-5.4)
        assert render_skymap(lib, SkyMapOptions(title="campaign")) is not None
    finally:
        lib.close()


def test_a_picture_is_drawn_at_the_size_it_was_asked_for():
    """The exaggeration has to be a *number of degrees on the map*, not a fudge
    factor: measure the drawn picture against the projection's own scale.

    Without this the drawn size silently picked up matplotlib's points→pixels
    correction (dpi/72 ≈ 1.5× at the default dpi), so "shown ~8× life size" was a
    lie and two maps rendered at different dpi disagreed with each other."""
    import io

    from PIL import Image

    from seestack.post.skymap import _aitoff_px_per_deg

    arr = np.zeros((40, 40, 4), dtype=np.uint8)
    arr[..., 0] = 255
    arr[..., 3] = 255
    # Long edge 2° × 8 = 16° drawn, inside the 3°–22° clamp.
    pic = MapPicture("X", 0.0, 0.0, arr, 2.0, 2.0)
    fig = render_my_map([pic], options=SkyMapOptions(
        title=None, show_bright_stars=False, show_galactic_plane=False,
        show_grid=False, label_targets=False))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=fig.dpi, facecolor=fig.get_facecolor())
    px = np.asarray(Image.open(buf).convert("RGB"))
    red = (px[..., 0] > 200) & (px[..., 1] < 80)
    cols = np.where(red.any(axis=0))[0]
    drawn_px = cols.max() - cols.min() + 1
    expected_px = 16.0 * _aitoff_px_per_deg(fig.axes[0])
    assert drawn_px == pytest.approx(expected_px, rel=0.03)


def test_the_detail_mask_is_bounded_in_memory_on_a_big_canvas(tmp_path, monkeypatch):
    """A mosaic's frame-count map is a full-canvas float32 array — hundreds of MB
    on a real mosaic — and the mask only ever drives a ≤1024 px preview's alpha.
    It must be read strided, not whole."""
    from astropy.io import fits

    from seestack.edit import proxy as proxy_mod
    from seestack.render import thumbnail as thumb

    h, w = 40, 4200                       # long axis past the strided ceiling
    cube = np.full((3, h, w), 0.3, dtype=np.float32)
    fp = tmp_path / "big.fits"
    fits.PrimaryHDU(data=cube).writeto(fp)
    counts = np.full((h, w), 6.0, dtype=np.float32)
    counts[:, :1000] = 1.0
    fits.PrimaryHDU(data=counts).writeto(tmp_path / "big_framecov.fits")

    seen: list[int] = []
    real = proxy_mod.load_frame_coverage

    def spy(path, *, step=1):
        seen.append(step)
        return real(path, step=step)

    monkeypatch.setattr(proxy_mod, "load_frame_coverage", spy)
    mask = thumb.stack_detail_mask(fp)
    assert seen and seen[0] > 1, "the frame-count map was read at full resolution"
    # …and the answer still lines up with the canvas it will be composited on.
    assert mask.shape == (h, w)
    assert not mask[:, :900].any()        # the badly-covered end is excluded
    assert mask[:, 1100:].all()           # the good end survives
