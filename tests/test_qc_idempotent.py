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


def test_only_new_skips_done_and_terminal_errors_but_retries_a_first_failure(tmp_path):
    f = tmp_path / "frame.fit"
    f.write_bytes(b"x")
    frames = [
        _Frame(1, source_path=str(f)),                                  # fresh
        _Frame(2, star_count=12, source_path=str(f)),                   # already QC'd
        _Frame(3, reject_reason="qc_error:bad header", source_path=str(f)),   # failed once
        _Frame(4, reject_reason="qc_error_final:bad header", source_path=str(f)),  # failed twice
    ]

    # Default (manual full re-QC): every readable frame is included, even a
    # terminal error — a manual re-check always retries.
    assert {a[0] for a in build_qc_arglist(_Project(frames))} == {1, 2, 3, 4}

    # only_new: the unprocessed frame *and* a first-time failure (retried once
    # for a transient blip); a successfully-QC'd frame and a terminal error are
    # skipped so re-scans don't redo work or re-loop on a genuinely-corrupt file.
    assert {a[0] for a in build_qc_arglist(_Project(frames), only_new=True)} == {1, 3}


def test_only_new_skips_missing_files(tmp_path):
    frames = [_Frame(1, source_path=str(tmp_path / "gone.fit"))]
    assert build_qc_arglist(_Project(frames), only_new=True) == []
