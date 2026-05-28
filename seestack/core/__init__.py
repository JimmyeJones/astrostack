"""Core utilities: GPU/CPU shim, cache management, job runner."""

from seestack.core.xp import GPU_AVAILABLE, get_array_module, xp

__all__ = ["GPU_AVAILABLE", "get_array_module", "xp"]
