"""GPU bg-flatten parity, exercised on a CPU-only host via the ``fake_cupy`` shim.

``tests/test_bg_gpu.py`` covers the GPU path only when *real* CuPy is present,
skipping the whole module otherwise — so on ordinary (CPU-only) CI the entire
``_subtract_background_gpu`` path went untested, which is exactly how a hardcoded
5px object-mask dilation that ignored ``dilate_object_mask_px`` shipped unnoticed
until an adversarial parity audit (fixed v0.119.7).

These tests close that structural blind spot: the shared ``fake_cupy`` fixture
(``tests/conftest.py``) backs ``cupy`` / ``cupyx.scipy.ndimage`` with NumPy/SciPy
so the **real** GPU function runs on the host, and we assert the same
gradient-removal + CPU↔GPU parity properties ``test_bg_gpu.py`` checks on a real
GPU. The real-CuPy path stays preferred wherever CuPy is available (that module
runs there); this one just guarantees the code is exercised everywhere else.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("scipy")

from seestack.bg.per_frame import (  # noqa: E402
    BackgroundOptions,
    _subtract_background_cpu,
)


def _gradient_image(seed: int = 0) -> np.ndarray:
    """A smooth per-channel gradient + noise — the same shape of input
    ``test_bg_gpu.py`` uses to check the sky model is removed."""
    rng = np.random.default_rng(seed)
    h, w = 320, 480
    yy, xx = np.indices((h, w), dtype=np.float32)
    grad_r = (xx / w) * 200 + 1000
    grad_g = (yy / h) * 150 + 1100
    grad_b = ((xx + yy) / (h + w)) * 100 + 950
    noise = rng.normal(scale=10.0, size=(h, w, 3)).astype(np.float32)
    return np.stack([grad_r, grad_g, grad_b], axis=-1).astype(np.float32) + noise


@pytest.mark.filterwarnings("ignore:All-NaN slice encountered")
@pytest.mark.filterwarnings("ignore:Mean of empty slice")
def test_gpu_path_removes_gradient_on_cpu_host(fake_cupy):
    """The real ``_subtract_background_gpu``, driven through the NumPy/SciPy shim,
    leaves a near-zero-median residual just like the CPU path — the same check
    ``test_bg_gpu.py::test_gpu_path_removes_gradient`` makes on a real GPU."""
    from seestack.bg.per_frame import _subtract_background_gpu

    rgb = _gradient_image(seed=7)
    out = _subtract_background_gpu(rgb, BackgroundOptions(box_size=64, enabled=True))
    for c in range(3):
        assert abs(np.median(out[..., c])) < 5.0
        assert np.std(out[..., c]) < 25.0


@pytest.mark.filterwarnings("ignore:All-NaN slice encountered")
@pytest.mark.filterwarnings("ignore:Mean of empty slice")
def test_gpu_and_cpu_paths_agree_on_cpu_host(fake_cupy):
    """The GPU and CPU paths use different algorithms but should land on a
    similar residual median — mirrors ``test_bg_gpu.py::
    test_gpu_and_cpu_paths_produce_similar_results`` without a real GPU."""
    from seestack.bg.per_frame import _subtract_background_gpu

    rgb = _gradient_image(seed=8)
    opts = BackgroundOptions(box_size=64, enabled=True)
    cpu_out = _subtract_background_cpu(rgb, opts)
    gpu_out = _subtract_background_gpu(rgb, opts)
    for c in range(3):
        assert abs(np.median(cpu_out[..., c]) - np.median(gpu_out[..., c])) < 5.0


@pytest.mark.filterwarnings("ignore:All-NaN slice encountered")
@pytest.mark.filterwarnings("ignore:Mean of empty slice")
def test_gpu_path_masks_exactly_what_the_cpu_path_masks(fake_cupy):
    """Both backends must exclude the *same* pixels from the sky fit.

    The GPU path used to build its own object mask from a whole-frame median/MAD
    threshold. That was the starved-mask bug (on a light-polluted sub the bright
    half reads as "object" and is excluded from the fit meant to remove it) *and*
    a silent divergence from the CPU backend — the same class of parity gap as the
    hardcoded dilation fixed in v0.119.7. It now calls the shared builder, so this
    asserts the sky the GPU tiles see is exactly the sky the CPU fit sees.
    """
    from seestack.bg.per_frame import _build_object_mask_for_bg, _subtract_background_gpu

    # A light-polluted sub: the case where a global threshold and a local one
    # disagree most (the whole bright side, ~60% of a fifth, used to be masked).
    h, w = 320, 480
    yy, xx = np.indices((h, w), dtype=np.float32)
    rng = np.random.default_rng(3)
    ramp = (xx / (w - 1)) * 0.75 + (yy / (h - 1)) * 0.25
    rgb = np.stack([lvl * (1.0 + 0.18 * ramp) for lvl in (1050.0, 1650.0, 820.0)],
                   axis=-1).astype(np.float32)
    rgb += rng.normal(scale=45.0, size=rgb.shape).astype(np.float32)

    opts = BackgroundOptions(box_size=64, enabled=True)
    expected = _build_object_mask_for_bg(rgb, dilate_px=opts.dilate_object_mask_px)
    seen: list[np.ndarray] = []
    from seestack.bg import per_frame

    real = per_frame._build_object_mask_for_bg

    def spy(*args, **kwargs):
        mask = real(*args, **kwargs)
        seen.append(mask)
        return mask

    per_frame._build_object_mask_for_bg = spy
    try:
        _subtract_background_gpu(rgb, opts)
    finally:
        per_frame._build_object_mask_for_bg = real

    assert seen, "the GPU path did not use the shared object-mask builder"
    np.testing.assert_array_equal(seen[0], expected)
    # And the shared mask is the *unstarved* one: the bright fifth is not what
    # the fit is denied.
    fifth = w // 5
    assert expected[:, -fifth:].mean() < max(2.0 * expected[:, :fifth].mean(), 0.05)
