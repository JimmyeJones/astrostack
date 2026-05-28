"""xp shim should expose a working numpy-or-cupy module."""

import numpy as np

from seestack.core.xp import GPU_AVAILABLE, device_summary, get_array_module, to_cpu, xp


def test_xp_basic_ops():
    a = xp.zeros((4, 4), dtype=xp.float32)
    a += 1
    assert float(a.sum()) == 16.0


def test_to_cpu_returns_numpy():
    a = xp.ones((2, 2), dtype=xp.float32)
    out = to_cpu(a)
    assert isinstance(out, np.ndarray)
    assert out.shape == (2, 2)


def test_get_array_module_handles_numpy():
    a = np.zeros(4)
    assert get_array_module(a) is np


def test_device_summary_is_string():
    s = device_summary()
    assert isinstance(s, str) and s
    if GPU_AVAILABLE:
        assert "GPU" in s or "cupy" in s.lower()
    else:
        assert "CPU" in s or "numpy" in s.lower()
