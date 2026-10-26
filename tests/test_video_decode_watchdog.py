"""The video decode can always be stopped: Cancel, and a decoder that went quiet.

``iter_frames`` used to block in ``proc.stdout.read`` with no deadline, so an
ffmpeg that stopped producing frames (a stalled read on the share, a
pathological file) could not be cancelled and held the single job worker until
the container restarted. These run a stub ``ffmpeg`` (a shell script) so the
stall is deterministic; no real decoder is needed.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

import pytest

from seestack.video import ffmpeg as ff
from seestack.video.ffmpeg import VideoDecoderStalled, VideoStackCancelled, iter_frames
from seestack.video.lucky import VideoStackCancelled as LuckyCancelled

pytestmark = pytest.mark.skipif(os.name != "posix", reason="shell-script stub ffmpeg")

W, H = 2, 2
FRAME = W * H * 3


def _stub(tmp_path: Path, body: str) -> Path:
    exe = tmp_path / "ffmpeg"
    exe.write_text("#!/bin/sh\n" + body + "\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe


def _frames(tmp_path, monkeypatch, body, **kwargs):
    monkeypatch.setenv("SEESTACK_FFMPEG_PATH", str(_stub(tmp_path, body)))
    return iter_frames(tmp_path / "clip.mp4", width=W, height=H, pix_fmt="yuv420p", **kwargs)


def test_cancel_stops_a_decoder_that_never_sends_a_frame(tmp_path, monkeypatch):
    cancel = threading.Event()
    gen = _frames(tmp_path, monkeypatch, "exec sleep 120", should_cancel=cancel.is_set)
    threading.Timer(0.5, cancel.set).start()
    t0 = time.monotonic()
    with pytest.raises(VideoStackCancelled):
        next(gen)
    assert time.monotonic() - t0 < 10


def test_cancel_mid_clip_raises_rather_than_ending_like_a_short_clip(tmp_path, monkeypatch):
    """One frame, then silence: Cancel must not read as "the clip ended here"."""
    cancel = threading.Event()
    gen = _frames(tmp_path, monkeypatch, f"head -c {FRAME} /dev/zero; exec sleep 120",
                  should_cancel=cancel.is_set)
    assert next(gen).shape == (H, W, 3)
    threading.Timer(0.5, cancel.set).start()
    with pytest.raises(VideoStackCancelled):
        next(gen)


def test_lucky_catches_the_same_cancel_class():
    """``webapp/video.py`` catches ``lucky.VideoStackCancelled`` — it must be this one."""
    assert LuckyCancelled is VideoStackCancelled


def test_a_decoder_that_goes_quiet_is_killed_with_a_plain_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ff, "_WATCHDOG_POLL_S", 0.05)
    gen = _frames(tmp_path, monkeypatch, f"head -c {FRAME} /dev/zero; exec sleep 120",
                  stall_timeout_s=0.5)
    assert next(gen) is not None
    t0 = time.monotonic()
    with pytest.raises(VideoDecoderStalled, match="stopped sending frames from clip.mp4"):
        next(gen)
    assert time.monotonic() - t0 < 10


def test_a_slow_consumer_is_not_a_stalled_decoder(tmp_path, monkeypatch):
    """Only time spent waiting on ffmpeg counts toward the stall deadline."""
    monkeypatch.setattr(ff, "_WATCHDOG_POLL_S", 0.05)
    gen = _frames(tmp_path, monkeypatch, f"head -c {3 * FRAME} /dev/zero", stall_timeout_s=0.3)
    got = []
    for frame in gen:
        got.append(frame)
        time.sleep(0.6)   # twice the deadline, spent here rather than in the read
    assert len(got) == 3


def test_a_truncated_tail_still_ends_the_clip_cleanly(tmp_path, monkeypatch):
    """The cut-short path is untouched: a short final write is a finished clip."""
    gen = _frames(tmp_path, monkeypatch, f"head -c {2 * FRAME + 5} /dev/zero",
                  should_cancel=lambda: False)
    assert len(list(gen)) == 2


def test_the_decoder_is_reaped_after_a_cancel(tmp_path, monkeypatch):
    pidfile = tmp_path / "pid"
    cancel = threading.Event()
    gen = _frames(tmp_path, monkeypatch, f"echo $$ > {pidfile}; exec sleep 120",
                  should_cancel=cancel.is_set)
    threading.Timer(0.5, cancel.set).start()
    with pytest.raises(VideoStackCancelled):
        next(gen)
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
