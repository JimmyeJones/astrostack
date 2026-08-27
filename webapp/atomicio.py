"""Durable atomic writes for the app's small JSON state files.

``config.json`` and the calibration registry are tiny files that carry settings
and master-calibration metadata the owner cannot easily reconstruct. Both are
written with the usual temp-file-then-``os.replace`` dance so a crash *mid-write*
can never be observed as a half-written file — but the rename alone is not the
whole story.

``os.replace`` makes the *directory entry* swap atomically. It says nothing about
when the new file's **data blocks** reach the disk. On a hard power loss the
kernel can have persisted the rename while the bytes behind it are still in
page cache, and the file comes back on the next boot as zero-length or partial —
which is the exact "silently revert every setting to defaults" failure the
atomic write exists to prevent. Closing the gap needs two `fsync`s: one on the
temp file (so its contents are durable *before* anything points at them), and
one on the containing directory (so the rename itself is durable).

Both are cheap here: these files are a few kilobytes and are written only when
the owner changes a setting or a master is built or deleted, never on the
ingest/stack hot path. An `fsync` that the platform or filesystem refuses is
swallowed — a best-effort flush is strictly better than failing a save the
caller could otherwise have completed.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path


def write_text_durably(path: Path, text: str, *, suffix: str = ".tmp") -> None:
    """Replace ``path`` with ``text``, atomically and durably.

    Writes a sibling temp file, flushes it to stable storage, renames it over
    ``path``, then flushes the directory so the rename survives a power loss too.
    The temp file is removed if anything fails before the rename, so a failed
    save never leaves litter beside the real file.

    ``suffix`` names the temp file's extension, kept as a parameter only so
    existing call sites can preserve the exact temp names they already use (an
    interrupted older version may have left one behind, and reusing the name
    means it gets cleaned up rather than accumulating).
    """
    tmp = path.with_suffix(suffix)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            # The data must be on disk *before* the rename publishes it; without
            # this the entry can point at blocks that were never written.
            with contextlib.suppress(OSError):
                os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    """Flush a directory entry, best-effort.

    Not every platform or filesystem allows opening a directory for `fsync`
    (Windows does not, and some network mounts refuse it), so a refusal is
    ignored: the rename is still atomic, it is simply not yet durable, which is
    exactly where we were before.
    """
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)
