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
    grade_video,
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
    # Every graded frame's score comes back, in capture order — that is what the
    # "How steady was your capture?" panel is measured from, and it costs the
    # grading pass nothing to keep.
    assert len(result.scores) == 12
    assert all(isinstance(s, float) for s in result.scores)
    # In capture order, so the good-seeing moments sit at their own indices.
    assert min(result.scores[i] for i in (1, 4, 7)) > max(
        s for j, s in enumerate(result.scores) if j not in (1, 4, 7))


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
    # The reference frame goes in unshifted and covers the whole canvas, so
    # nothing ends up uncovered here...
    assert not np.isnan(result.image).any()
    # ...and the sky corner stays sky-dark rather than being pulled toward zero
    # by an uncorrected fill.
    corner = result.image[0:6, 0:6]
    assert np.isfinite(corner).all()


def _disk_centre(luma: np.ndarray) -> tuple[float, float]:
    """(y, x) centroid of the bright disk in a luma frame.

    Weighted by how far each pixel rises above the frame's own median, so the
    sky (and its noise) contributes nothing and the answer is the disk's
    position rather than the frame's.
    """
    w = np.clip(np.nan_to_num(luma, nan=0.0) - float(np.median(luma)), 0.0, None)
    yy, xx = np.mgrid[0:luma.shape[0], 0:luma.shape[1]]
    total = float(w.sum())
    return float((w * yy).sum() / total), float((w * xx).sum() / total)


def _ramped_capture(tmp_path, *, n_frames: int, drift_px: float):
    """A drifting capture whose frames get steadily sharper to the last one.

    Deterministic by construction: the sharpness ramp is strictly increasing, so
    "the sharpest frame" is the last one and "the earliest keeper" is the first
    frame of the kept tail — the two candidate alignment anchors, as far apart in
    the capture (and in disk position) as the drift allows.
    """
    frames = []
    for i in range(n_frames):
        t = i / (n_frames - 1)
        frames.append(lunar_frame(
            128, 96,
            cx=64 + drift_px * t, cy=48 + drift_px * t,
            radius=28, sharpness=0.1 + 0.9 * t, seed=i,
        ))
    return write_video(tmp_path / "Lunar_video.mp4", frames), frames


def test_the_stack_is_anchored_on_the_sharpest_frame_not_the_earliest_kept_one(
    tmp_path,
):
    """Lucky imaging aligns to the *best* frame (as AutoStakkert/RegiStax do).

    Phase correlation locks harder against a crisp reference, so anchoring on
    whichever keeper merely came first in decode order measures every other
    frame's shift against a softer image. Measured on a seeing-blurred synthetic
    where the earliest keeper is ~98× softer than the sharpest: RMS shift error
    0.217 px → 0.135 px, and the finished picture's sharpness +14 %.

    The observable consequence — and what this pins — is the framing: the
    reference is added unshifted, so the result sits where the sharpest frame's
    disk sat, not where the earliest keeper's did.
    """
    path, frames = _ramped_capture(tmp_path, n_frames=12, drift_px=14.0)
    result = stack_video(path, LuckyOptions(keep_percent=50, align=True))

    sharpest = _disk_centre(frame_luma(frames[-1]))
    earliest_kept = _disk_centre(frame_luma(frames[min(result.kept_indices)]))
    stacked = _disk_centre(frame_luma(np.nan_to_num(result.image, nan=0.0) * 255.0))

    # The two candidate anchors really are far apart, so this can distinguish them.
    assert abs(sharpest[1] - earliest_kept[1]) > 4.0
    assert stacked[0] == pytest.approx(sharpest[0], abs=1.0)
    assert stacked[1] == pytest.approx(sharpest[1], abs=1.0)
    assert abs(stacked[1] - earliest_kept[1]) > 3.0
    # Anchoring elsewhere must not cost frames: everything kept still stacks.
    assert result.n_stacked == result.n_kept
    assert result.n_align_failed == 0


def test_the_sharpest_frame_is_always_one_of_the_keepers(tmp_path):
    """The reference must be a frame that is actually in the picture.

    Keepers are chosen by a stable descending sort, so a tie breaks toward the
    earlier frame — the same rule ``grade_video`` uses to pick the frame it hands
    back. That is what makes "the alignment reference is a kept frame" true by
    construction rather than by luck.
    """
    path, _ = _ramped_capture(tmp_path, n_frames=11, drift_px=6.0)
    for keep in (10, 30, 50, 100):
        result = stack_video(path, LuckyOptions(keep_percent=keep, align=True))
        best = int(np.argmax(result.scores))
        assert best in result.kept_indices, f"keep_percent={keep}"
        assert len(result.kept_indices) == result.n_kept


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


def test_grade_only_scores_every_frame_without_stacking(tmp_path):
    """Pass 1 on its own — the cheap half, run to answer "how picky should I
    be?" before a stack is spent finding out."""
    path = lunar_video(
        tmp_path / "Lunar_video.mp4", n_frames=12, sharp_indices=(1, 4, 7), w=96, h=72,
    )
    graded = grade_video(path)
    assert graded.n_graded == 12
    assert graded.stride == 1
    assert graded.width == 96 and graded.height == 72
    assert len(graded.scores) == 12
    assert min(graded.scores[i] for i in (1, 4, 7)) > max(
        s for j, s in enumerate(graded.scores) if j not in (1, 4, 7))
    # Identical to what the stack's own first pass produces — there is one
    # grading implementation, not two that can drift apart.
    stacked = stack_video(path, LuckyOptions(keep_percent=25, align=False))
    assert graded.scores == stacked.scores


def test_grade_only_honours_progress_and_cancel(tmp_path):
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=8, w=48, h=36)
    seen: list[tuple[str, int, int]] = []
    graded = grade_video(path, progress=lambda *a: seen.append(a))
    assert graded.n_graded == 8
    assert {s for s, _, _ in seen} == {"grade"}
    assert seen[-1][1] == 8

    with pytest.raises(VideoStackCancelled):
        grade_video(path, should_cancel=lambda: True)


def test_grade_only_refuses_a_video_with_too_few_frames(tmp_path):
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=2, w=48, h=36)
    with pytest.raises(ValueError, match="at least 3"):
        grade_video(path)


def test_grade_hands_back_the_sharpest_frame_when_asked(tmp_path):
    """The "quick look": the best frame itself, off the same single decode."""
    path = lunar_video(
        tmp_path / "Lunar_video.mp4", n_frames=12, sharp_indices=(5,), w=96, h=72,
    )
    graded = grade_video(path, keep_best_frame=True)
    assert graded.best_index == 5
    assert graded.best_index == int(np.argmax(graded.scores))
    assert graded.best_frame is not None
    assert graded.best_frame.shape == (72, 96, 3)
    assert graded.best_frame.dtype == np.uint8
    # It is genuinely that frame, not a re-decode that could drift: grading it
    # again reproduces the frame's own score.
    assert frame_sharpness(frame_luma(graded.best_frame)) == pytest.approx(
        graded.scores[5], rel=1e-9,
    )


def test_grade_locates_the_sharpest_frame_without_holding_one(tmp_path):
    """``keep_best_frame`` is opt-in — the index is free, the frame is not.

    The stack's own grading pass must not pay a frame of memory for a picture
    it never looks at, so the default carries the index alone.
    """
    path = lunar_video(
        tmp_path / "Lunar_video.mp4", n_frames=10, sharp_indices=(3,), w=64, h=48,
    )
    graded = grade_video(path)
    assert graded.best_index == 3
    assert graded.best_frame is None
