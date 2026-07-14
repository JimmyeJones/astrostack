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
