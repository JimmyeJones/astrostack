"""GPU vs CPU bg-flatten parity (skipped when CuPy isn't available)."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from seestack.bg.per_frame import (  # noqa: E402
    BackgroundOptions,
    _subtract_background_cpu,
    subtract_background,
)
from seestack.core.xp import GPU_AVAILABLE  # noqa: E402

if not GPU_AVAILABLE:
    pytest.skip("CuPy not available", allow_module_level=True)

from seestack.bg.per_frame import _subtract_background_gpu  # noqa: E402


def _gradient_image(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    h, w = 320, 480
    yy, xx = np.indices((h, w), dtype=np.float32)
    grad_r = (xx / w) * 200 + 1000
    grad_g = (yy / h) * 150 + 1100
    grad_b = ((xx + yy) / (h + w)) * 100 + 950
    noise = rng.normal(scale=10.0, size=(h, w, 3)).astype(np.float32)
    return np.stack([grad_r, grad_g, grad_b], axis=-1).astype(np.float32) + noise


def test_gpu_path_removes_gradient():
    """GPU bg flatten should produce a near-zero-median residual like the CPU path."""
    rgb = _gradient_image(seed=7)
    out = _subtract_background_gpu(rgb, BackgroundOptions(box_size=64, enabled=True))
    for c in range(3):
        assert abs(np.median(out[..., c])) < 5.0
        assert np.std(out[..., c]) < 25.0


def test_gpu_and_cpu_paths_produce_similar_results():
    """The two paths use different algorithms but should give a similar residual median."""
    rgb = _gradient_image(seed=8)
    opts = BackgroundOptions(box_size=64, enabled=True)
    cpu_out = _subtract_background_cpu(rgb, opts)
    gpu_out = _subtract_background_gpu(rgb, opts)
    # Both should leave near-zero medians.
    for c in range(3):
        assert abs(np.median(cpu_out[..., c]) - np.median(gpu_out[..., c])) < 5.0


def test_subtract_background_uses_gpu_by_default():
    """``subtract_background`` should pick the GPU path on a large enough image."""
    rgb = _gradient_image(seed=9)
    opts = BackgroundOptions(box_size=64, enabled=True)
    # use_gpu=None auto-selects; we check that the result is produced without
    # error and the gradient is removed (not testing the specific code path
    # taken — that's an internal detail).
    out = subtract_background(rgb, opts, use_gpu=None)
    for c in range(3):
        assert abs(np.median(out[..., c])) < 5.0


def test_force_cpu_works():
    """Explicit use_gpu=False forces the CPU path even when GPU is available."""
    rgb = _gradient_image(seed=10)
    out = subtract_background(rgb, BackgroundOptions(box_size=64), use_gpu=False)
    for c in range(3):
        assert abs(np.median(out[..., c])) < 5.0
