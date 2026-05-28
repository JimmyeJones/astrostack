"""
NumPy / CuPy compatibility shim.

The hot loops in seestack (warp, drizzle, accumulator updates) are written against
``xp`` instead of ``numpy`` directly. When CuPy is installed and a CUDA device is
visible, ``xp`` is CuPy and those loops run on the GPU. Otherwise it falls back to
NumPy with no behavioural change.

Use it like::

    from seestack.core.xp import xp, to_cpu

    a = xp.zeros((1024, 1024), dtype=xp.float32)
    result_cpu = to_cpu(a)  # always a numpy array

For functions that must accept either a numpy or cupy array, use
``get_array_module(arr)`` to pick the right module dynamically.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as _np

log = logging.getLogger(__name__)


def _try_import_cupy() -> Any | None:
    """Import CuPy if available *and* a CUDA device is visible. Otherwise None."""
    if os.environ.get("SEESTACK_FORCE_CPU") == "1":
        log.info("SEESTACK_FORCE_CPU=1, using numpy backend")
        return None
    try:
        # CuPy emits a UserWarning at import when it can't find a *system*
        # CUDA install. With the cupy-cuda12x pip wheels everything CuPy needs
        # is bundled, so the warning is noise — suppress it for a clean launch.
        import warnings as _warnings
        with _warnings.catch_warnings():
            _warnings.filterwarnings(
                "ignore", message=".*CUDA path could not be detected.*"
            )
            import cupy as _cp  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        n = _cp.cuda.runtime.getDeviceCount()
    except Exception as exc:  # pragma: no cover — depends on driver
        log.warning("CuPy import succeeded but CUDA unusable: %s", exc)
        return None
    if n == 0:
        return None
    return _cp


_cp = _try_import_cupy()
GPU_AVAILABLE: bool = _cp is not None
xp: Any = _cp if GPU_AVAILABLE else _np


def get_array_module(arr: Any) -> Any:
    """Return numpy or cupy depending on the input array's type."""
    if GPU_AVAILABLE:
        return _cp.get_array_module(arr)
    return _np


def to_cpu(arr: Any) -> _np.ndarray:
    """Bring an array to host memory as a numpy array (no-op if already numpy)."""
    if GPU_AVAILABLE and isinstance(arr, _cp.ndarray):
        return _cp.asnumpy(arr)
    return _np.asarray(arr)


def to_device(arr: Any) -> Any:
    """Move a numpy array to GPU if available, otherwise return it unchanged."""
    if GPU_AVAILABLE and not isinstance(arr, _cp.ndarray):
        return _cp.asarray(arr)
    return arr


def device_summary() -> str:
    """One-line description of the active backend, for the GUI status bar."""
    if not GPU_AVAILABLE:
        return "CPU (numpy)"
    try:
        props = _cp.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else props["name"]
        mem_gb = _cp.cuda.runtime.memGetInfo()[1] / 1024**3
        return f"GPU: {name} ({mem_gb:.1f} GB)"
    except Exception:
        return "GPU (cupy)"
