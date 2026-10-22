"""A clip that carries a rotation tag decodes in the shape ffprobe reported.

ffmpeg auto-rotates by default: a stream tagged with a 90° display matrix (a
phone recording, or a clip re-saved through a phone's gallery) comes off the
wire ``height × width`` while ``ffprobe`` still reports the coded
``width × height``. :func:`~seestack.video.ffmpeg.iter_frames` reshapes the
byte stream by the probed size, and the byte count is the same either way, so
every frame came back scrambled into horizontal streaks — no error, a garbage
still. ``-noautorotate`` keeps the decode in the coded orientation, which is
the one every other step (the probe, the CFA phase) already assumes.
"""
from __future__ import annotations

import subprocess

import numpy as np
import pytest

from seestack.video import ffmpeg_available, iter_frames, probe_video
from tests.videosynth import lunar_video

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed (bundled in the Docker image; see AGENTS.md §7)",
)


def _tag_rotated(src, dst) -> None:
    """Copy ``src`` to ``dst`` with a 90° rotation tag and no re-encode."""
    from seestack.video.ffmpeg import ffmpeg_path

    attempts = (
        [ffmpeg_path(), "-v", "error", "-y", "-display_rotation", "90",
         "-i", str(src), "-c", "copy", str(dst)],
        # ffmpeg < 6 has no -display_rotation; the old metadata key does the same.
        [ffmpeg_path(), "-v", "error", "-y", "-i", str(src), "-c", "copy",
         "-metadata:s:v:0", "rotate=90", str(dst)],
    )
    for cmd in attempts:
        if subprocess.run(cmd, capture_output=True, check=False).returncode == 0:
            return
    pytest.skip("this ffmpeg cannot write a rotation tag")


def test_a_rotation_tagged_clip_decodes_the_same_pixels(tmp_path):
    plain = lunar_video(tmp_path / "plain.mp4", n_frames=4, w=96, h=64)
    rotated = tmp_path / "rotated.mp4"
    _tag_rotated(plain, rotated)

    info = probe_video(rotated)
    assert (info.width, info.height) == (96, 64)

    want = list(iter_frames(plain))
    got = list(iter_frames(rotated))
    assert len(got) == len(want) == 4
    for a, b in zip(want, got):
        assert b.shape == (64, 96, 3)
        # Same coded pixels, not a 64×96 decode reshaped into 96×64 streaks.
        assert np.array_equal(a, b)
