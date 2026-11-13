"""The editor's Rotate and enlarging Resize hold the picture once, not twice.

Both ops build their result with a SciPy resampler that already returns
``float32`` and then called ``.astype(np.float32)`` on it — which copies even
when the dtype already matches, so the full-resolution export briefly held two
copies of the rotated / enlarged canvas. Measured with ``tracemalloc`` (NumPy
reports its allocations to it): Rotate peaked at **2.00×** its output and a
×1.5 Resize at **2.00×**; after, both sit at ~1.0×. On a mosaic-sized export
that copy is the whole canvas again (a 6000×4000 RGB float32 picture is
288 MB; the ×1.5 enlargement of it 648 MB), on the path whose memory bounds
AGENTS.md calls deliberate. The **ratio** is pinned, not an absolute, so the
test is the same claim at any size.

Output must be byte-identical — the change removes a copy, not a computation.
"""

from __future__ import annotations

import tracemalloc

import numpy as np
import pytest

from seestack.edit.registry import EditContext, get_op


def _picture(h: int = 600, w: int = 800) -> np.ndarray:
    rng = np.random.default_rng(3)
    img = (rng.random((h, w, 3), dtype=np.float32) * 0.3 + 0.1).astype(np.float32)
    img[:40] = np.nan  # a mosaic-style uncovered strip
    return img


def _peak_over_output(op_id: str, params: dict) -> float:
    spec = get_op(op_id)
    img = _picture()
    ctx = EditContext(is_proxy=False, proxy_scale=1.0)
    spec.apply(img, params, ctx)  # warm imports out of the count
    tracemalloc.start()
    try:
        out = spec.apply(img, params, ctx)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert out.dtype == np.float32
    return peak / out.nbytes


@pytest.mark.parametrize("op_id,params", [
    ("geometry.rotate", {"angle": 7.0, "expand": True}),
    ("geometry.rotate", {"angle": -30.0, "expand": False}),
    ("geometry.rotate", {"angle": 90.0}),
    ("geometry.resize", {"scale": 1.5}),
    ("geometry.resize", {"scale": 2.0}),
])
def test_rotate_and_enlarge_do_not_copy_the_result(op_id, params):
    ratio = _peak_over_output(op_id, params)
    # 2.00× before (result + its astype copy); ~1.0× after.
    assert ratio < 1.5, f"{op_id} {params}: peak {ratio:.2f}× its output"


@pytest.mark.parametrize("op_id,params", [
    ("geometry.rotate", {"angle": 7.0, "expand": True}),
    ("geometry.resize", {"scale": 1.5}),
])
def test_result_is_still_float32_and_keeps_its_gaps(op_id, params):
    out = get_op(op_id).apply(_picture(), params, EditContext())
    assert out.dtype == np.float32
    assert np.isnan(out).any() and np.isfinite(out).any()
