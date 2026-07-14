"""Preview↔export parity for the object-mask dilation in `background.subtract`.

`bg/per_frame.py::subtract_background` dilates an object mask (to keep
stars/nebulosity out of the sky fit) by a fixed *full-resolution* pixel count.
The editor op used to leave it at the hardcoded 4 on both the full-res export and
the decimated live-preview proxy, so on a ×N proxy it masked an N×-larger physical
halo than the export — a preview↔export sky-model mismatch (worst on dense star
fields at a heavy proxy, e.g. the globular_cluster preset). The dilation is now a
`BackgroundOptions` field the editor scales by `proxy_scale`; the stack/export
path (`proxy_scale == 1`) leaves the default 4, byte-for-byte unchanged.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")

from seestack.bg.per_frame import (
    BackgroundOptions,
    _build_object_mask_for_bg,
    subtract_background,
)


def _star_field(h=120, w=160, seed=0):
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 8.0, size=(h, w, 3)).astype(np.float32)
    r = 2
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
    psf = np.exp(-((dy ** 2 + dx ** 2) / (2 * 1.2 ** 2)))
    for _ in range(40):
        cy = int(rng.integers(r, h - r))
        cx = int(rng.integers(r, w - r))
        img[cy - r:cy + r + 1, cx - r:cx + r + 1, :] += (12000.0 * psf)[..., None]
    return img


def test_object_mask_dilation_scales_the_masked_halo():
    """The mask grows with dilate_px (and a scaled-down dilate_px masks less) —
    the mechanism the editor relies on to keep the proxy halo physically matched."""
    img = _star_field()
    n0 = int(_build_object_mask_for_bg(img, dilate_px=0).sum())
    n1 = int(_build_object_mask_for_bg(img, dilate_px=1).sum())
    n4 = int(_build_object_mask_for_bg(img, dilate_px=4).sum())
    assert n0 < n1 < n4, f"dilation should grow the mask: {n0} < {n1} < {n4}"


def test_subtract_background_threads_the_dilation_option_default_unchanged():
    img = _star_field(seed=1)
    # The default must be byte-for-byte identical to an explicit 4 (the value the
    # stack/export path relies on) — proves the new field defaults faithfully.
    base = subtract_background(img, BackgroundOptions(box_size=32))
    explicit4 = subtract_background(
        img, BackgroundOptions(box_size=32, dilate_object_mask_px=4))
    np.testing.assert_array_equal(base, explicit4)
    # And a different dilation actually reaches the fit (so the option is wired,
    # not ignored) — an undilated mask changes the sky model on a dense field.
    none = subtract_background(
        img, BackgroundOptions(box_size=32, dilate_object_mask_px=0))
    assert not np.allclose(base, none)


def test_for_image_size_preserves_the_dilation_option():
    """The tiny-image box_size adjustment must carry the new field through, not
    silently reset it to the default."""
    opts = BackgroundOptions(box_size=512, dilate_object_mask_px=1)
    adjusted = opts.for_image_size(40, 40)          # forces a box_size shrink
    assert adjusted.box_size < 512
    assert adjusted.dilate_object_mask_px == 1


def test_editor_subtract_op_scales_the_dilation_by_proxy_scale(monkeypatch):
    """Regression: the editor's background.subtract op now passes an object-mask
    dilation scaled by proxy_scale (4 full-res px → 1 px on a ×4 proxy), where it
    previously left the hardcoded 4 on both the proxy and the export. Spy on the
    BackgroundOptions the op hands to subtract_background at each scale."""
    import seestack.bg.per_frame as per_frame
    from seestack.edit.ops.background import _subtract
    from seestack.edit.registry import EditContext

    seen: list[int] = []

    def _spy(rgb, options=None, *, use_gpu=None, errors=None):
        seen.append(options.dilate_object_mask_px)
        return rgb.astype(np.float32, copy=True)

    monkeypatch.setattr(per_frame, "subtract_background", _spy)

    img = _star_field(seed=2)
    export = EditContext(proxy_scale=1.0, is_proxy=False, wcs=None, coverage=None)
    proxy4 = EditContext(proxy_scale=4.0, is_proxy=True, wcs=None, coverage=None)
    _subtract(img, {"box_size": 128}, export)
    _subtract(img[::4, ::4], {"box_size": 128}, proxy4)

    # Export unchanged (4 full-res px); ×4 proxy masks the same *physical* halo
    # with 1 proxy px — not the 4 it used before, which was a 16-px-equiv halo.
    assert seen == [4, 1]


def _bright_object_field(h=200, w=200, seed=4):
    """Sky + a bright compact object whose dilated halo reaches nearby tiles, so
    the object-mask dilation measurably changes the per-tile sky fit."""
    rng = np.random.default_rng(seed)
    img = rng.normal(100.0, 2.0, size=(h, w, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    obj = 5000.0 * np.exp(-(((yy - h // 2) ** 2 + (xx - w // 2) ** 2)
                            / (2 * 6.0 ** 2)))
    return (img + obj.astype(np.float32)[..., None]).astype(np.float32)


@pytest.mark.filterwarnings("ignore:All-NaN slice encountered")
@pytest.mark.filterwarnings("ignore:Mean of empty slice")
def test_gpu_path_honours_the_dilation_option(fake_cupy):
    """Regression: `_subtract_background_gpu` used a hardcoded 5px max-filter that
    ignored `dilate_object_mask_px` entirely, so on a GPU host the editor's
    proxy_scale-scaled dilation was discarded — a CPU↔GPU divergence and a
    preview↔export parity break. It now mirrors the CPU
    `binary_dilation(iterations=dilate_object_mask_px)`, so changing the dilation
    changes the sky model. Fails before (fixed 5px → identical output)."""
    from seestack.bg.per_frame import _subtract_background_gpu

    img = _bright_object_field()

    def run(dp):
        return _subtract_background_gpu(
            img.copy(), BackgroundOptions(box_size=20, dilate_object_mask_px=dp))

    out1 = run(1)
    out8 = run(8)
    # A wider dilation masks more of the object halo → a different per-tile sky.
    assert not np.allclose(out1, out8, equal_nan=True), (
        "GPU path ignored dilate_object_mask_px (hardcoded dilation)")
    # And dropping the dilation to 0 also reaches the fit (option genuinely wired).
    out0 = run(0)
    assert not np.allclose(out0, run(4), equal_nan=True)


def test_editor_level_coverage_op_scales_the_dilation_by_proxy_scale(monkeypatch):
    """Regression: the editor's background.level_coverage op now passes an
    object-mask dilation scaled by proxy_scale (4 full-res px → 1 px on a ×4
    proxy), where it previously left `level_by_coverage`'s default 4 on both the
    proxy and the export — so on a ×N proxy it dilated the mask by N× the physical
    halo, feeding a different sky population into each coverage level's median (a
    preview↔export panel-offset mismatch). Sibling of the background.subtract fix
    above. Spy on the dilation the op hands to level_by_coverage at each scale."""
    import seestack.bg.coverage_leveling as cov_mod
    import seestack.edit.ops.background as bg_ops
    from seestack.edit.registry import EditContext

    seen: list[int] = []

    def _spy(rgb, coverage, *, object_sigma=2.0, dilate_object_mask_px=4,
             proxy_scale=1.0, **kw):
        seen.append(dilate_object_mask_px)
        return rgb.astype(np.float32, copy=True)

    monkeypatch.setattr(cov_mod, "level_by_coverage", _spy)

    img = _star_field(seed=3)
    cov = np.ones(img.shape[:2], dtype=np.int32)
    export = EditContext(proxy_scale=1.0, is_proxy=False, wcs=None, coverage=cov)
    img4 = img[::4, ::4]
    proxy4 = EditContext(proxy_scale=4.0, is_proxy=True, wcs=None,
                         coverage=cov[::4, ::4])
    bg_ops._level_coverage(img, {}, export)
    bg_ops._level_coverage(img4, {}, proxy4)

    # Export unchanged (4 full-res px); ×4 proxy masks the same *physical* halo
    # with 1 proxy px — not the 4 it used before (a 16-full-res-px-equiv halo).
    assert seen == [4, 1]
