"""Shared pytest fixtures for the engine test suite."""

import sys
import types

import numpy as np
import pytest


@pytest.fixture
def fake_cupy(monkeypatch):
    """Back CuPy / cupyx.scipy.ndimage with NumPy / SciPy so the engine's GPU
    code paths (``bg/per_frame.py::_subtract_background_gpu`` and friends) run on
    an ordinary CPU host.

    ``tests/test_bg_gpu.py`` skips **wholesale** whenever real CuPy is absent
    (`pytest.skip(..., allow_module_level=True)`), so on CPU-only CI the entire
    GPU path is untested — the exact structural blind spot that let a hardcoded
    5px object-mask dilation ignore ``dilate_object_mask_px`` sit unnoticed until
    an adversarial parity audit (fixed v0.119.7). This shim drives the **real**
    GPU functions through NumPy/SciPy (same API surface) so the path is exercised
    in ordinary CI; the real-CuPy path stays preferred whenever CuPy is present.

    Only the attributes the GPU functions actually use are mapped — extend this
    list if a GPU path starts using a new ``cp.*`` symbol."""
    import scipy.ndimage as ndi

    cupy = types.ModuleType("cupy")
    for name in ("asarray", "float32", "nanmedian", "abs", "indices", "stack",
                 "nan", "where", "isfinite", "nanmean"):
        setattr(cupy, name, getattr(np, name))
    cupy.asnumpy = lambda a: np.asarray(a)

    cupyx = types.ModuleType("cupyx")
    cupyx_scipy = types.ModuleType("cupyx.scipy")
    cupyx_ndi = types.ModuleType("cupyx.scipy.ndimage")
    cupyx_ndi.map_coordinates = ndi.map_coordinates
    cupyx_ndi.maximum_filter = ndi.maximum_filter
    cupyx_ndi.binary_dilation = ndi.binary_dilation
    cupyx_scipy.ndimage = cupyx_ndi
    cupyx.scipy = cupyx_scipy

    monkeypatch.setitem(sys.modules, "cupy", cupy)
    monkeypatch.setitem(sys.modules, "cupyx", cupyx)
    monkeypatch.setitem(sys.modules, "cupyx.scipy", cupyx_scipy)
    monkeypatch.setitem(sys.modules, "cupyx.scipy.ndimage", cupyx_ndi)
    return cupy
