"""Lucky-imaging video stack: decode, grade, keep-the-best, align, average.

Every test drives a real ffmpeg-encoded synthetic capture (``tests/videosynth``)
rather than a stubbed decoder, so the container's actual decode path is what's
under test.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.video import (
    LuckyOptions,
    ffmpeg_available,
    iter_frames,
    normalize_for_display,
    probe_video,
    stack_video,
)
from seestack.video.lucky import (
    MIN_FRAMES,
    VideoStackCancelled,
    _sampling_stride,
    frame_luma,
    frame_sharpness,
)
from tests.videosynth import lunar_frame, lunar_video, write_video

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed (bundled in the Docker image; see AGENTS.md §7)",
)


# --------------------------------------------------------------------------
# decode
# --------------------------------------------------------------------------

def test_probe_reports_dimensions_and_frame_count(tmp_path):
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=10, w=64, h=48)
    info = probe_video(path)
    assert (info.width, info.height) == (64, 48)
    assert info.n_frames == 10
    assert info.fps == pytest.approx(10.0, rel=0.05)


def test_probe_rejects_a_non_video_file(tmp_path):
    junk = tmp_path / "notes.mp4"
    junk.write_bytes(b"this is not a video")
    with pytest.raises(ValueError):
        probe_video(junk)


def test_iter_frames_streams_every_frame_at_the_right_shape(tmp_path):
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=7, w=64, h=48)
    frames = list(iter_frames(path))
    assert len(frames) == 7
    assert all(f.shape == (48, 64, 3) and f.dtype == np.uint8 for f in frames)
    # Decoded frames must be writable — downstream code does in-place maths.
    frames[0][0, 0, 0] = 1


def test_iter_frames_stride_keeps_every_nth_frame(tmp_path):
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=12, w=64, h=48)
    every = list(iter_frames(path))
    strided = list(iter_frames(path, stride=3))
    assert len(strided) == 4
    # Same frames as indices 0, 3, 6, 9 of the full decode — this identity is
    # what lets pass 2 re-decode exactly the frames pass 1 graded.
    for k, frame in enumerate(strided):
        assert np.array_equal(frame, every[k * 3])


def test_abandoning_the_frame_iterator_does_not_leave_ffmpeg_running(tmp_path):
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=30, w=64, h=48)
    it = iter_frames(path)
    next(it)
    it.close()  # generator finally-block must kill the decoder
    # Nothing to assert beyond "this returns" — a leaked process would keep the
    # pipe open and hang the close().


# --------------------------------------------------------------------------
# sharpness grading
# --------------------------------------------------------------------------

def test_sharpness_ranks_a_crisp_frame_above_a_soft_one():
    sharp = lunar_frame(96, 72, cx=48, cy=36, radius=25, sharpness=1.0, seed=1, noise=0.0)
    soft = lunar_frame(96, 72, cx=48, cy=36, radius=25, sharpness=0.1, seed=1, noise=0.0)
    assert frame_sharpness(frame_luma(sharp)) > 3 * frame_sharpness(frame_luma(soft))


def test_sharpness_is_not_fooled_by_a_brighter_exposure():
    """A thin cloud / auto-exposure step changes the level, not the detail.

    Without the mean-brightness normalisation the Laplacian energy scales with
    the square of the level, so the *brightest* frames would be ranked sharpest
    and lucky imaging would pick exactly the wrong ones.
    """
    sharp = lunar_frame(96, 72, cx=48, cy=36, radius=25, sharpness=1.0, seed=2, noise=0.0)
    soft = lunar_frame(96, 72, cx=48, cy=36, radius=25, sharpness=0.15, seed=2, noise=0.0)
    brighter_soft = np.clip(soft.astype(np.float32) * 1.6, 0, 255).astype(np.uint8)
    assert frame_sharpness(frame_luma(sharp)) > frame_sharpness(frame_luma(brighter_soft))


def test_sampling_stride_bounds_the_graded_frame_count():
    assert _sampling_stride(500, 1500) == 1
    assert _sampling_stride(3000, 1500) == 2
    assert _sampling_stride(4001, 1000) == 5
    assert _sampling_stride(0, 1000) == 1


# --------------------------------------------------------------------------
# the stack
# --------------------------------------------------------------------------

def test_stack_keeps_the_sharpest_frames_and_drops_the_rest(tmp_path):
    path = lunar_video(
        tmp_path / "Lunar_video.mp4", n_frames=12, sharp_indices=(1, 4, 7), w=96, h=72,
    )
    result = stack_video(path, LuckyOptions(keep_percent=25, align=False))
    assert result.n_graded == 12
    assert result.n_kept == 3
    assert result.n_stacked == 3
    # The three good-seeing frames are exactly the ones kept.
    assert result.kept_indices == (1, 4, 7)
    assert result.sharpness_kept_median > 2 * result.sharpness_all_median


def test_stack_averages_the_noise_down(tmp_path):
    """The whole point: N frames averaged are ~√N cleaner than any single one."""
    # A featureless disk (sharpness 0) so the scatter measured below is the
    # per-frame noise and nothing else.
    frames = [
        lunar_frame(96, 72, cx=48, cy=36, radius=25, sharpness=0.0, seed=i, noise=12.0)
        for i in range(12)
    ]
    path = write_video(tmp_path / "Lunar_video.mp4", frames)
    result = stack_video(path, LuckyOptions(keep_percent=100, align=False))
    assert result.n_stacked == 12

    # Measure the residual scatter over a flat patch of the disk interior, on
    # the stack vs on one raw frame.
    patch = (slice(30, 42), slice(42, 54))
    single = frames[0][patch][..., 0].astype(np.float32) / 255.0
    stacked = result.image[patch][..., 0]
    assert np.nanstd(stacked) < 0.6 * np.std(single)


def test_alignment_recovers_detail_a_drifting_disk_would_smear(tmp_path):
    path = lunar_video(
        tmp_path / "Lunar_video.mp4", n_frames=10, sharp_indices=range(10),
        w=128, h=96, drift_px=8.0,
    )
    aligned = stack_video(path, LuckyOptions(keep_percent=100, align=True))
    unaligned = stack_video(path, LuckyOptions(keep_percent=100, align=False))
    assert aligned.n_stacked == unaligned.n_stacked == 10
    # A drifting disk averaged without alignment is a blur; aligning it keeps
    # the surface detail, which shows up as a much higher sharpness score.
    sharp_aligned = frame_sharpness(frame_luma(np.nan_to_num(aligned.image) * 255.0))
    sharp_unaligned = frame_sharpness(frame_luma(np.nan_to_num(unaligned.image) * 255.0))
    assert sharp_aligned > 2 * sharp_unaligned


def test_alignment_leaves_vacated_edges_uncovered_not_black(tmp_path):
    """NaN = no coverage — a shift must never invent a dark band.

    Only the region no frame covered may be NaN, and nothing may be a
    suspiciously dark 'averaged with zero' edge.
    """
    path = lunar_video(
        tmp_path / "Lunar_video.mp4", n_frames=8, sharp_indices=range(8),
        w=128, h=96, drift_px=10.0,
    )
    result = stack_video(path, LuckyOptions(keep_percent=100, align=True))
    # The first kept frame is the reference and covers the whole canvas, so
    # nothing ends up uncovered here...
    assert not np.isnan(result.image).any()
    # ...and the sky corner stays sky-dark rather than being pulled toward zero
    # by an uncorrected fill.
    corner = result.image[0:6, 0:6]
    assert np.isfinite(corner).all()


def test_stack_refuses_a_video_with_too_few_frames(tmp_path):
    frames = [
        lunar_frame(64, 48, cx=32, cy=24, radius=16, sharpness=1.0, seed=i)
        for i in range(MIN_FRAMES - 1)
    ]
    path = write_video(tmp_path / "Lunar_video.mp4", frames)
    with pytest.raises(ValueError, match="at least"):
        stack_video(path)


def test_long_capture_is_evenly_sampled_with_an_honest_note(tmp_path):
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=20, w=64, h=48)
    result = stack_video(path, LuckyOptions(keep_percent=50, max_frames=5, align=False))
    assert result.stride == 4
    assert result.n_graded == 5
    assert any("every 4th frame" in w for w in result.warnings)


def test_progress_and_cancel_are_honoured(tmp_path):
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=10, w=64, h=48)
    seen: list[tuple[str, int, int]] = []
    result = stack_video(
        path, LuckyOptions(keep_percent=50, align=False),
        progress=lambda stage, done, total: seen.append((stage, done, total)),
    )
    assert result.n_stacked == 5
    assert [s for s, _, _ in seen].count("grade") == 10
    assert [s for s, _, _ in seen].count("stack") == 5

    calls = {"n": 0}

    def cancel_after_three() -> bool:
        calls["n"] += 1
        return calls["n"] > 3

    with pytest.raises(VideoStackCancelled):
        stack_video(path, should_cancel=cancel_after_three)


def test_bad_keep_percent_is_rejected_up_front():
    with pytest.raises(ValueError):
        LuckyOptions(keep_percent=0)
    with pytest.raises(ValueError):
        LuckyOptions(keep_percent=120)
    with pytest.raises(ValueError):
        LuckyOptions(max_frames=1)


# --------------------------------------------------------------------------
# display render
# --------------------------------------------------------------------------

def test_display_render_puts_the_sky_at_black_and_the_disk_near_white():
    disk = lunar_frame(96, 72, cx=48, cy=36, radius=25, sharpness=0.0, seed=0, noise=0.0)
    linear = disk.astype(np.float32) / 255.0
    out = normalize_for_display(linear)
    assert out[2, 2].max() < 0.05           # sky corner → black
    assert out[36, 48].max() > 0.8          # disk centre → bright
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_display_render_does_not_blow_the_disk_out_on_a_hot_pixel():
    disk = lunar_frame(96, 72, cx=48, cy=36, radius=25, sharpness=1.0, seed=0, noise=0.0)
    linear = disk.astype(np.float32) / 255.0
    baseline = normalize_for_display(linear)
    speckled = linear.copy()
    speckled[5, 5] = 40.0  # a single wild sample
    out = normalize_for_display(speckled)
    # The 99.9th-percentile anchor means one hot pixel can't crush the disk into
    # the bottom of the range.
    assert abs(float(out[36, 48].mean()) - float(baseline[36, 48].mean())) < 0.05


def test_display_render_maps_uncovered_pixels_to_black():
    linear = np.full((8, 8, 3), 0.5, dtype=np.float32)
    linear[0, 0] = np.nan
    out = normalize_for_display(linear)
    assert np.isfinite(out).all()
    assert out[0, 0].max() == 0.0


def test_display_render_survives_an_all_uncovered_image():
    out = normalize_for_display(np.full((4, 4, 3), np.nan, dtype=np.float32))
    assert np.isfinite(out).all() and out.max() == 0.0
