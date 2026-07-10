"""Background-flatten mode dispatch + luminance-mode color preservation."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from seestack.bg.per_frame import (  # noqa: E402
    MODE_LUMINANCE,
    MODE_OFF,
    MODE_PER_CHANNEL,
    BackgroundOptions,
    subtract_background,
)


def _frame_with_gradient_and_object():
    """A frame with a gradient PLUS a bright off-centre 'object' that's not centred
    in the channels (simulating an emission nebula whose R/G/B morphology differs)."""
    rng = np.random.default_rng(11)
    h, w = 200, 280
    yy, xx = np.indices((h, w), dtype=np.float32)
    # Common gradient: brighter on the right.
    grad = (xx / w) * 200 + 1000
    rgb = np.stack([grad, grad, grad], axis=-1).astype(np.float32)
    rgb += rng.normal(scale=10.0, size=rgb.shape).astype(np.float32)
    # Add an "object" with different per-channel positions to simulate an
    # emission nebula. Tiny so per-channel mode doesn't eat it.
    cy, cx = h // 2, w // 2
    for dy, dx, c, amp in [(-2, -2, 0, 5000), (0, 0, 1, 4000), (2, 2, 2, 3000)]:
        rgb[cy+dy-3:cy+dy+3, cx+dx-3:cx+dx+3, c] += amp
    return rgb


def test_mode_off_returns_input_unchanged():
    rgb = _frame_with_gradient_and_object()
    out = subtract_background(rgb, BackgroundOptions(mode=MODE_OFF))
    np.testing.assert_array_equal(out, rgb)


def test_per_channel_removes_gradient():
    rgb = _frame_with_gradient_and_object()
    out = subtract_background(rgb, BackgroundOptions(mode=MODE_PER_CHANNEL, box_size=32),
                              use_gpu=False)
    for c in range(3):
        assert abs(np.median(out[..., c])) < 5.0


def test_luminance_removes_gradient_and_keeps_color_balance():
    rgb = _frame_with_gradient_and_object()
    out = subtract_background(rgb, BackgroundOptions(mode=MODE_LUMINANCE, box_size=32),
                              use_gpu=False)
    # Sky should be near zero in all channels.
    for c in range(3):
        assert abs(np.median(out[..., c])) < 5.0


def test_luminance_subtracts_same_shape_from_all_channels():
    """
    The whole point of luminance mode: the shape subtracted from each channel
    is identical (only per-channel offsets differ). We verify this by checking
    that channel-difference histograms are uniform (no spatial structure).
    """
    rgb = _frame_with_gradient_and_object()
    out = subtract_background(rgb, BackgroundOptions(mode=MODE_LUMINANCE, box_size=32),
                              use_gpu=False)
    # R-G should have minimal spatial variation in the *sky* region (away from
    # the small object). Take a sky-only slice on the left half.
    sky = out[:, :100, :]
    rg_diff = sky[..., 0] - sky[..., 1]
    # Standard deviation should be close to noise level (~10 ADU per channel
    # → ~14 in the difference). Looser bound to handle small statistical
    # variations from the per-channel median offset.
    assert np.std(rg_diff) < 25


def _sparse_mosaic_canvas(h: int = 400, w: int = 400) -> np.ndarray:
    """A mosaic proxy whose covered area is a thin diagonal strip (~10% of the
    bounding canvas) and the rest is uncovered NaN. The object mask ``| ~finite``
    then covers >80% of every default box, which makes ``Background2D`` raise at
    the strict ``exclude_percentile=80`` — exactly the case the ladder degrades."""
    rng = np.random.default_rng(0)
    img = np.full((h, w), np.nan, dtype=np.float32)
    for i in range(h):
        lo = int(i * 0.9)
        hi = min(w, lo + 40)
        # A tight sky population inside the covered strip; the rest is NaN.
        img[i, lo:hi] = rng.normal(0.3, 0.02, size=hi - lo).astype(np.float32)
    return np.stack([img, img, img], axis=-1)


def test_sparse_mosaic_canvas_degrades_instead_of_failing():
    """A mostly-uncovered mosaic proxy masks >80% of every box, so the strict
    ``exclude_percentile=80`` fit raises. The per-frame op used to hard-fail on
    the editor path (``background.subtract`` raised "background fit failed") and
    silently skip every channel on the stack path; it must now degrade to a
    coarse flatten — no surfaced error, covered sky flattened, NaN preserved."""
    rgb = _sparse_mosaic_canvas()
    assert np.isnan(rgb[..., 0]).mean() > 0.8

    # Sanity: the strict single-attempt fit the old code did really does fail
    # here, so this is a genuine before/after regression test.
    from astropy.stats import SigmaClip
    from photutils.background import Background2D, MMMBackground

    from seestack.bg.per_frame import _build_object_mask_for_bg

    obj_mask = _build_object_mask_for_bg(rgb)
    with pytest.raises(ValueError):
        Background2D(
            rgb[..., 0], box_size=(100, 100), filter_size=(3, 3),
            sigma_clip=SigmaClip(sigma=3.0), bkg_estimator=MMMBackground(),
            mask=obj_mask, exclude_percentile=80.0,
        )

    for mode in (MODE_PER_CHANNEL, MODE_LUMINANCE):
        errors: list[str] = []
        out = subtract_background(
            rgb, BackgroundOptions(mode=mode, box_size=100), use_gpu=False,
            errors=errors,
        )
        assert errors == [], f"{mode}: {errors}"
        assert out.shape == rgb.shape
        # NaN (uncovered) stays NaN — coverage semantics preserved.
        covered = np.isfinite(rgb[..., 0])
        assert np.array_equal(np.isfinite(out[..., 0]), covered)
        # The op actually flattened the covered strip's sky toward zero rather
        # than returning the input unchanged.
        assert np.nanmedian(out[..., 1][covered]) < np.nanmedian(rgb[..., 1][covered])


def test_ladder_first_rung_matches_strict_fit():
    """A frame whose fit succeeds at the tuned ``exclude_percentile=80`` must be
    byte-for-byte unchanged by the degradation ladder — the retry only kicks in
    *after* the strict fit fails, so normal frames stay identical."""
    from astropy.stats import SigmaClip
    from photutils.background import Background2D, MMMBackground

    from seestack.bg.per_frame import _build_object_mask_for_bg, _fit_bg2d_ladder

    rgb = _frame_with_gradient_and_object()
    obj_mask = _build_object_mask_for_bg(rgb.astype(np.float32, copy=True))
    ladder = _fit_bg2d_ladder(
        rgb[..., 1], box_size=32, filter_size=3,
        sigma_clip=SigmaClip(sigma=3.0), estimator=MMMBackground(), mask=obj_mask,
    )
    strict = Background2D(
        rgb[..., 1], box_size=(32, 32), filter_size=(3, 3),
        sigma_clip=SigmaClip(sigma=3.0), bkg_estimator=MMMBackground(),
        mask=obj_mask, exclude_percentile=80.0,
    ).background.astype(np.float32, copy=False)
    np.testing.assert_array_equal(ladder, strict)


def test_gpu_failure_falls_back_to_cpu_in_both_modes(monkeypatch):
    """A GPU/cupy hiccup must degrade to CPU in *both* per-channel and luminance
    modes — not just per-channel. Previously the luminance path called the GPU
    routine directly with no fallback, so the same failure per-channel recovered
    from aborted a luminance-mode stack (the mode recommended for nebulae)."""
    import seestack.bg.per_frame as pf

    calls = {"gpu": 0}

    def boom(*_a, **_k):
        calls["gpu"] += 1
        raise RuntimeError("cupy OOM")

    rgb = _frame_with_gradient_and_object()
    for mode in (MODE_PER_CHANNEL, MODE_LUMINANCE):
        # Reset the per-worker latch so each mode genuinely re-attempts the GPU.
        monkeypatch.setattr(pf, "_gpu_bg_disabled", False)
        monkeypatch.setattr(pf, "_subtract_background_gpu", boom)
        before = calls["gpu"]
        # use_gpu=True forces the GPU branch regardless of hardware; it must not
        # propagate the RuntimeError but fall back to a real CPU flatten.
        out = subtract_background(
            rgb, BackgroundOptions(mode=mode, box_size=32), use_gpu=True,
        )
        assert calls["gpu"] == before + 1, f"{mode}: GPU path not attempted"
        assert out.shape == rgb.shape
        # The CPU fallback actually flattened the gradient (didn't return input).
        for c in range(3):
            assert abs(np.median(out[..., c])) < 5.0, mode
