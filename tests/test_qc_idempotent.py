"""QC arglist idempotency: only_new skips already-processed frames."""

from __future__ import annotations

from seestack.qc.runner import build_qc_arglist


class _Frame:
    def __init__(self, fid, *, star_count=None, reject_reason=None, source_path):
        self.id = fid
        self.star_count = star_count
        self.reject_reason = reject_reason
        self.cached_path = None
        self.source_path = source_path
        self.bayer_pattern = "RGGB"


class _Project:
    def __init__(self, frames):
        self._frames = frames

    def iter_frames(self):
        return iter(self._frames)


def test_only_new_skips_qc_done_and_errored(tmp_path):
    f = tmp_path / "frame.fit"
    f.write_bytes(b"x")
    frames = [
        _Frame(1, source_path=str(f)),                                  # fresh
        _Frame(2, star_count=12, source_path=str(f)),                   # already QC'd
        _Frame(3, reject_reason="qc_error:bad header", source_path=str(f)),  # permanently failed
    ]

    # Default: every readable frame is included.
    assert {a[0] for a in build_qc_arglist(_Project(frames))} == {1, 2, 3}

    # only_new: just the unprocessed frame — re-scans don't redo work or
    # re-loop on frames that always fail QC.
    assert {a[0] for a in build_qc_arglist(_Project(frames), only_new=True)} == {1}


def test_only_new_skips_missing_files(tmp_path):
    frames = [_Frame(1, source_path=str(tmp_path / "gone.fit"))]
    assert build_qc_arglist(_Project(frames), only_new=True) == []
