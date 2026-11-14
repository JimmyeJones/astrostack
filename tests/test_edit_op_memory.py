"""Editor ops hold as few whole-canvas copies as their arithmetic needs.

The full-resolution export (``webapp.pipeline._render_recipe_fullres``) runs every
recipe op at the picture's own size, so each temporary an op allocates is a whole
canvas — 288 MB for a 6000×4000 RGB float32 mosaic, and the owner's big rasters are
larger than that. Measured with ``tracemalloc`` (NumPy reports its allocations to
it), as the peak *new* memory over the input's own size, before → after:

* ``detail.sharpen``     6.4× → 3.1× (clip, result, clip again, and an ``astype``
  that copied a float32 array to float32 — on Auto's clean-stack path);
* ``tone.saturation``    4.7× → 2.7× (on every Auto recipe);
* ``stars.boost_nebula`` 9.4× → 4.4×;
* ``_with_nan_filled`` (sharpen / denoise / deconvolve / hot pixels) copied the
  picture twice to fill it once (2.85× → 1.85× on its own; denoise 9.1× → 8.2×,
  deconvolve 6.3× → 5.3×);
* and the export loop kept the loaded master alive beside every op's output.

Every change is byte-identical output (checked over 204 op/parameter/scale cases
while writing it) — they remove copies, not computation. The **ratio** is pinned,
not an absolute, so each test is the same claim at any size; the bounds sit
between the measured before and after.
"""

from __future__ import annotations

import gc
import tracemalloc
import weakref

import numpy as np
import pytest

from seestack.edit.registry import EditContext, get_op


def _picture(h: int = 480, w: int = 640) -> np.ndarray:
    rng = np.random.default_rng(7)
    img = (rng.random((h, w, 3), dtype=np.float32) * 0.6 + 0.05).astype(np.float32)
    img[:40, :120] = np.nan  # a mosaic-style uncovered corner
    return img


def _peak_over_input(fn, img: np.ndarray) -> float:
    fn(img.copy())  # warm imports and caches out of the count
    work = img.copy()
    gc.collect()
    tracemalloc.start()
    try:
        out = fn(work)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert out.dtype == np.float32
    return peak / img.nbytes


def _op(op_id: str, params: dict):
    spec = get_op(op_id)
    return lambda a: spec.apply(a, params, EditContext(is_proxy=False, proxy_scale=1.0))


@pytest.mark.parametrize("op_id,params,bound", [
    ("detail.sharpen", {"amount": 1.0, "radius": 2.0}, 4.5),     # 6.4× before
    ("tone.saturation", {"amount": 1.3}, 3.5),                   # 4.7× before
    ("stars.boost_nebula", {"amount": 0.3, "size": 4}, 6.5),     # 9.4× before
])
def test_op_peak_memory_is_bounded(op_id, params, bound):
    ratio = _peak_over_input(_op(op_id, params), _picture())
    assert ratio < bound, f"{op_id}: peak {ratio:.2f}× the picture"


def test_nan_fill_wrapper_copies_the_picture_once():
    from seestack.edit.ops.detail import _with_nan_filled

    # An identity ``fn`` isolates the wrapper's own copies: one to fill (and
    # return) plus the mask and the per-channel median's scratch — 1.85×, where
    # copying twice measured 2.85×.
    ratio = _peak_over_input(lambda a: _with_nan_filled(a, lambda f: f), _picture())
    assert ratio < 2.3, f"_with_nan_filled: peak {ratio:.2f}× the picture"


def test_nan_fill_wrapper_still_restores_gaps_and_leaves_the_input_alone():
    from seestack.edit.ops.detail import _with_nan_filled

    img = _picture()
    before = img.copy()
    seen = {}

    def fn(f):
        seen["finite"] = bool(np.isfinite(f).all())
        f *= 2.0  # the wrapper's copy is the op's to overwrite
        return f

    out = _with_nan_filled(img, fn)
    assert seen["finite"]
    assert np.array_equal(np.isnan(out), np.isnan(before))
    assert np.array_equal(img, before, equal_nan=True)


@pytest.mark.parametrize("op_id,params", [
    ("detail.sharpen", {"amount": 1.0, "radius": 2.0}),
    ("tone.saturation", {"amount": 1.3}),
    ("stars.boost_nebula", {"amount": 0.3, "size": 4}),
])
def test_op_does_not_modify_its_input(op_id, params):
    img = _picture()
    before = img.copy()
    _op(op_id, params)(img)
    assert np.array_equal(img, before, equal_nan=True)


def test_saturation_keeps_a_partly_covered_pixel_untouched():
    img = _picture()
    img[100, 200, 1] = np.nan
    out = _op("tone.saturation", {"amount": 1.5})(img.copy())
    assert np.array_equal(out[100, 200], img[100, 200], equal_nan=True)
    assert np.all(np.isnan(out[:40, :120]))


def test_export_lets_the_loaded_master_go_after_the_first_op(monkeypatch):
    """The export loop held the loaded master under its own name for the whole
    render, so it sat beside every op's output — one extra canvas at every peak."""
    from seestack.edit import proxy as edit_proxy
    from seestack.edit import registry
    from seestack.stack import output as stack_output
    from webapp import pipeline

    refs: list[weakref.ref] = []

    def _load(_path):
        master = _picture(60, 80)
        refs.append(weakref.ref(master))
        return master, None

    monkeypatch.setattr(pipeline, "_load_full_rgb_wcs", _load)
    monkeypatch.setattr(pipeline, "_preview_curve_fits", lambda *a, **k: None)
    monkeypatch.setattr(edit_proxy, "load_coverage", lambda _p: None)
    monkeypatch.setattr(edit_proxy, "load_frame_coverage", lambda _p: None)
    monkeypatch.setattr(stack_output, "fits_is_display_space", lambda _p: False)

    alive_at_second_op: list[bool] = []
    real = registry.get_op("tone.saturation")
    calls = {"n": 0}

    def _apply(rgb, params, ctx):
        calls["n"] += 1
        if calls["n"] == 2:
            alive_at_second_op.append(refs[0]() is not None)
        return real.apply(rgb, params, ctx)

    probe = registry.OpSpec(id=real.id, label=real.label, group=real.group,
                            stage=real.stage, apply=_apply, params=real.params)
    monkeypatch.setattr(registry, "get_op", lambda op_id: probe)

    recipe = {"ops": [{"id": "tone.saturation", "params": {"amount": 1.2}},
                      {"id": "tone.saturation", "params": {"amount": 1.1}}]}
    out, _recipe = pipeline._render_recipe_fullres("x.fits", recipe, lambda *a, **k: None)
    assert out.shape == (60, 80, 3)
    assert alive_at_second_op == [False]
