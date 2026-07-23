"""Backwards-compatible shim.

The thumbnail / autostretch code moved to :mod:`seestack.render.thumbnail` so it
can be imported server-side without dragging in PySide6. This module re-exports
the public names so existing imports (``seestack.gui.thumbnail``) keep working.
"""

from __future__ import annotations

from seestack.render.thumbnail import (  # noqa: F401
    THUMB_SIZE,
    THUMB_VERSION,
    THUMBS_DIRNAME,
    autostretch,
    ensure_thumb_cache_current,
    generate_thumbnail,
    invalidate_frame_thumbs,
    thumb_path_for,
    thumbs_dir,
)

__all__ = [
    "THUMB_SIZE",
    "THUMB_VERSION",
    "THUMBS_DIRNAME",
    "autostretch",
    "ensure_thumb_cache_current",
    "generate_thumbnail",
    "thumb_path_for",
    "thumbs_dir",
]
