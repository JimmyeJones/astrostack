"""A Moon/Sun capture cut short (still copying in) says so instead of stacking silently.

The Seestar's ``…-Solar-RAW.avi`` carries its full frame count in the AVI header,
so a file read while it is still being copied into ``incoming/`` probes as
**exact** while ffmpeg reads only the frames that have arrived and then ends
cleanly. Before :func:`seestack.video.lucky.cut_short_warning` the stack ended
``done`` with ``warnings: []``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seestack.video import ffmpeg_available, grade_video, probe_video, stack_video
from seestack.video.lucky import LuckyOptions, cut_short_warning
from tests.videosynth import lunar_video, solar_raw_video


def test_an_exact_count_read_in_full_warns_nothing():
    assert cut_short_warning(200, 200, 1, exact=True) is None


def test_a_frame_or_two_short_of_an_exact_count_is_tail_rounding_not_a_cut():
    assert cut_short_warning(198, 200, 1, exact=True) is None
    assert cut_short_warning(197, 200, 1, exact=True) is None


def test_a_file_read_at_forty_percent_is_called_cut_short():
    msg = cut_short_warning(80, 200, 1, exact=True)
    assert msg is not None
    assert "first 80 of this capture's 200 frames" in msg
    assert "still copying?" in msg
    assert "Stack it again once it has finished" in msg


def test_an_estimated_count_is_never_trusted_to_call_a_file_cut_short():
    # duration × fps can be off by far more than any slack worth having.
    assert cut_short_warning(80, 200, 1, exact=False) is None
    assert cut_short_warning(0, 0, 1, exact=True) is None


def test_a_sampled_long_capture_counts_in_sampled_frames():
    # 3,001 frames at stride 3 yields ceil(3001 / 3) = 1,001 frames, not 1,000:
    # reading all of them must not warn, and the slack is 2 % of the sampled count.
    assert cut_short_warning(1001, 3001, 3, exact=True) is None
    assert cut_short_warning(981, 3001, 3, exact=True) is None
    msg = cut_short_warning(400, 3001, 3, exact=True)
    assert msg is not None
    assert "about the first 1200 of this capture's 3001 frames" in msg


needs_ffmpeg = pytest.mark.skipif(
    not ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed (bundled in the Docker image; see AGENTS.md §7)",
)


def _cut(path: Path, fraction: float) -> Path:
    data = path.read_bytes()
    cut = path.with_name("cut" + path.suffix)
    cut.write_bytes(data[: int(len(data) * fraction)])
    return cut


@needs_ffmpeg
def test_the_owners_raw_avi_cut_to_forty_percent_still_probes_exact(tmp_path):
    """The premise: the header still claims every frame — why the count is trusted."""
    full = solar_raw_video(tmp_path / "clip.avi", n_frames=50, w=64, h=48)
    info = probe_video(_cut(full, 0.4))
    assert info.n_frames == 50
    assert info.n_frames_exact


@needs_ffmpeg
def test_grading_a_cut_short_raw_avi_warns(tmp_path):
    full = solar_raw_video(tmp_path / "clip.avi", n_frames=50, w=64, h=48)
    graded = grade_video(_cut(full, 0.4))
    assert graded.n_graded < 25
    assert any("cut short" in w for w in graded.warnings), graded.warnings


@needs_ffmpeg
def test_stacking_a_cut_short_raw_avi_carries_the_warning(tmp_path):
    full = solar_raw_video(
        tmp_path / "clip.avi", n_frames=50, w=64, h=48, sharp_indices=range(40, 50),
    )
    result = stack_video(_cut(full, 0.4), LuckyOptions(keep_percent=30))
    assert any(
        "of this capture's 50 frames could be read" in w for w in result.warnings
    ), result.warnings


@needs_ffmpeg
def test_the_whole_file_and_an_ordinary_mp4_warn_nothing(tmp_path):
    full = solar_raw_video(tmp_path / "clip.avi", n_frames=50, w=64, h=48)
    assert not any("cut short" in w for w in grade_video(full).warnings)
    mp4 = lunar_video(tmp_path / "moon.mp4", n_frames=12, sharp_indices=(3,))
    assert not any("cut short" in w for w in stack_video(mp4).warnings)
