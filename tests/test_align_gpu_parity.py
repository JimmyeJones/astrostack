"""
GPU/CPU parity for the reproject hot loop.

Skipped automatically when CuPy isn't installed. When it is, we verify that
the GPU path produces the same result as the CPU path (within float tolerance)
on a real-sized array.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")

from seestack.core.xp import GPU_AVAILABLE  # noqa: E402

if not GPU_AVAILABLE:
    pytest.skip("CuPy not available", allow_module_level=True)

from seestack.stack.align import _reproject_rgb_cpu, _reproject_rgb_gpu  # noqa: E402


def test_gpu_matches_cpu_for_identity_map():
    """Identity coordinate map: output equals input (interior)."""
    rng = np.random.default_rng(3)
    h, w = 256, 384
    src = rng.random((h, w, 3), dtype=np.float32)
    yy, xx = np.indices((h, w), dtype=np.float32)
    cpu = _reproject_rgb_cpu(src, yy, xx, order=1)
    gpu = _reproject_rgb_gpu(src, yy, xx, order=1)
    # Interior pixels (away from boundaries) should be very close.
    np.testing.assert_allclose(cpu[2:-2, 2:-2], gpu[2:-2, 2:-2], rtol=1e-4, atol=1e-4)


def test_gpu_matches_cpu_for_shifted_map():
    rng = np.random.default_rng(4)
    h, w = 256, 384
    src = rng.random((h, w, 3), dtype=np.float32)
    yy, xx = np.indices((h, w), dtype=np.float32)
    src_y = yy + 1.5
    src_x = xx - 2.5
    cpu = _reproject_rgb_cpu(src, src_y, src_x, order=1)
    gpu = _reproject_rgb_gpu(src, src_y, src_x, order=1)
    # Restrict comparison to where both samples are in-bounds.
    valid = (
        (src_x >= 0) & (src_x <= w - 1) & (src_y >= 0) & (src_y <= h - 1)
    )
    valid_3 = np.broadcast_to(valid[..., None], cpu.shape)
    np.testing.assert_allclose(
        np.where(valid_3, cpu, 0), np.where(valid_3, gpu, 0),
        rtol=1e-4, atol=1e-4,
    )
