"""A raw solar/planetary capture is a Bayer mosaic, and the stack must debayer it.

The owner reported a stacked Sun "covered edge-to-edge in a fine mesh". The video
pipeline had no colour-filter handling at all: a single-channel source reaches
ffmpeg's ``rgb24`` output as R=G=B=the raw sensor byte, so the mosaic survived
verbatim as a luminance checkerboard — and because the disk is static and the
pattern is sensor-fixed, lucky imaging *adds* it coherently across every kept
frame instead of averaging it down.

These drive a real ffmpeg-encoded ``pal8`` rawvideo capture — the shape ffprobe
found on the owner's own ``…-Solar-RAW.avi`` — and measure the artefact directly:
the spread between the four 2×2 phase means, which *is* the mesh. That statistic
rather than an FFT bin because it averages over a quarter of the frame per phase,
so shot noise cancels out of it and what is left is the fixed pattern alone.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.video import LuckyOptions, ffmpeg_available, iter_frames, probe_video
from seestack.video.ffmpeg import source_is_cfa_mosaic
from seestack.video.lucky import stack_video
from tests.videosynth import lunar_video, solar_raw_video

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed (bundled in the Docker image; see AGENTS.md §7)",
)


def _mesh_strength(plane: np.ndarray) -> float:
    """How strong a fixed 2×2 pattern this plane carries, relative to its level.

    The four CFA phases are sampled a quarter-frame each, so noise averages out
    of their means and the spread between them is the mesh and nothing else. A
    replicated mosaic reads ~0.58 on the fixture (the R/G/B transmission spread);
    a demosaiced picture reads ~0.01, which is bilinear interpolation's own
    slight asymmetry at the limb.
    """
    a = np.asarray(plane, dtype=np.float64)
    h, w = a.shape[0] - a.shape[0] % 2, a.shape[1] - a.shape[1] % 2
    a = a[:h, :w]
    means = [a[i::2, j::2].mean() for i in (0, 1) for j in (0, 1)]
    return float((max(means) - min(means)) / (abs(a.mean()) + 1e-9))


def _raw_rgb24_frame(path, w, h):
    """What the decoder handed the pipeline *before* this fix: the replicated
    mosaic, straight off ``-pix_fmt rgb24`` with no demosaic."""
    import subprocess

    from seestack.video.ffmpeg import ffmpeg_path

    out = subprocess.run(
        [ffmpeg_path(), "-v", "error", "-nostdin", "-i", str(path),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(out[: h * w * 3], np.uint8).reshape(h, w, 3)


# --- what the source is ----------------------------------------------------

def test_the_probe_reports_the_pixel_format(tmp_path):
    """It could not before: ``pix_fmt`` was absent from ffprobe's entry list, so
    the pipeline was structurally incapable of noticing a raw source."""
    path = solar_raw_video(tmp_path / "Solar_video.avi", n_frames=6, w=64, h=48)
    assert probe_video(path).pix_fmt == "pal8"


@pytest.mark.parametrize(
    ("pix_fmt", "expected"),
    [
        ("pal8", True),        # the owner's real file
        ("gray", True),
        ("gray16le", True),
        ("monow", True),
        ("yuv420p", False),    # an ordinary colour capture
        ("rgb24", False),
        ("bayer_rggb8", False),  # ffmpeg demosaics this itself — see below
        ("", False),
        (None, False),
    ],
)
def test_which_formats_mean_raw_sensor_data(pix_fmt, expected):
    assert source_is_cfa_mosaic(pix_fmt) is expected


def test_an_ffmpeg_bayer_format_is_never_demosaiced_twice():
    """``bayer_*`` is the one single-channel-looking family that must be left
    alone: ffmpeg already demosaics it on the way to ``rgb24``, so treating it
    as raw would debayer a picture."""
    for fmt in ("bayer_rggb8", "bayer_bggr8", "bayer_gbrg16le"):
        assert source_is_cfa_mosaic(fmt) is False


# --- the fix ---------------------------------------------------------------

def test_decoding_a_raw_capture_removes_the_mesh(tmp_path):
    """**The bug.** Fails before: the frame the pipeline received was the
    replicated mosaic, whose Nyquist bin carries the checkerboard."""
    w, h = 64, 48
    path = solar_raw_video(tmp_path / "Solar_video.avi", n_frames=6, w=w, h=h)

    before = _mesh_strength(_raw_rgb24_frame(path, w, h)[..., 1])
    after = _mesh_strength(next(iter(iter_frames(path)))[..., 1])

    # The mesh is unmistakable before and gone after — asserted as a ratio so
    # the test says "the artefact was removed", not "some number changed".
    assert before > 0.2, f"the fixture does not carry the artefact ({before})"
    assert after < before / 20.0, f"mesh survived: {before} -> {after}"


def test_a_raw_capture_comes_back_as_real_colour(tmp_path):
    """The other half of demosaicing: the three channels stop being copies of
    each other, and the disk reads warm through an RGGB filter rather than grey."""
    path = solar_raw_video(tmp_path / "Solar_video.avi", n_frames=4, w=64, h=48)
    frame = next(iter(iter_frames(path)))
    assert frame.shape == (48, 64, 3) and frame.dtype == np.uint8
    frame[0, 0, 0] = 1  # downstream code does in-place maths on these
    r, g, b = (float(frame[..., c].mean()) for c in range(3))
    assert not np.array_equal(frame[..., 0], frame[..., 2])
    assert r > g > b


def test_an_ordinary_colour_capture_is_untouched(tmp_path):
    """Upgrade safety: every capture that already worked must decode to exactly
    the same pixels, so no existing Moon still changes."""
    path = lunar_video(tmp_path / "Lunar_video.mp4", n_frames=5, w=64, h=48)
    assert source_is_cfa_mosaic(probe_video(path).pix_fmt) is False
    frames = list(iter_frames(path))
    expected = _raw_rgb24_frame(path, 64, 48)
    assert len(frames) == 5
    assert np.array_equal(frames[0], expected)


def test_a_palettised_source_that_is_really_colour_is_left_alone(tmp_path):
    """The ``pal8`` trap, guarded by measurement rather than assumption: the
    format says "raw", but a non-grey palette decodes to a real picture. The
    ``R == G == B`` check on the first frame catches that and passes it
    through, because demosaicing a picture is nonsense."""
    import subprocess

    from seestack.video.ffmpeg import ffmpeg_path

    w, h = 64, 48
    src = tmp_path / "colour.raw"
    yy, xx = np.mgrid[0:h, 0:w]
    idx = ((yy // 8) * 8 + (xx // 8)).astype(np.uint8)
    ramp = np.arange(256, dtype=np.uint8)
    # A deliberately colourised palette — R, G and B all differ.
    palette = np.stack([ramp, (255 - ramp), (ramp // 2), np.full(256, 255, np.uint8)], axis=1)
    src.write_bytes(b"".join(idx.tobytes() + palette.tobytes() for _ in range(4)))
    path = tmp_path / "Scenery_video.avi"
    subprocess.run(
        [ffmpeg_path(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "pal8",
         "-s", f"{w}x{h}", "-r", "10", "-i", str(src),
         "-c:v", "rawvideo", "-pix_fmt", "pal8", str(path)],
        check=True, capture_output=True)

    assert source_is_cfa_mosaic(probe_video(path).pix_fmt) is True  # it claims raw
    frame = next(iter(iter_frames(path)))
    assert np.array_equal(frame, _raw_rgb24_frame(path, w, h))  # ...but is passed through


def test_the_two_decode_passes_still_see_the_same_frames(tmp_path):
    """The stride identity the two-pass lucky stack depends on has to survive
    demosaicing — pass 2 re-decodes exactly the frames pass 1 graded."""
    path = solar_raw_video(tmp_path / "Solar_video.avi", n_frames=12, w=64, h=48)
    every = list(iter_frames(path))
    strided = list(iter_frames(path, stride=3))
    assert len(strided) == 4
    for k, frame in enumerate(strided):
        assert np.array_equal(frame, every[k * 3])


# --- through the whole stack ----------------------------------------------

def test_a_stacked_raw_solar_capture_has_no_mesh(tmp_path):
    """End to end, and the reason this bug is worse than it sounds: the disk is
    static, so a sensor-fixed pattern adds coherently across the kept frames.
    The stacked result is where the owner saw it, so that is where it is pinned."""
    path = solar_raw_video(
        tmp_path / "Solar_video.avi", n_frames=12, w=64, h=48, sharp_indices=(2, 5, 8))
    result = stack_video(path, LuckyOptions(keep_percent=50, align=False))
    assert result.n_stacked >= 2
    stacked = _mesh_strength(result.image[..., 1])
    raw = _mesh_strength(_raw_rgb24_frame(path, 64, 48)[..., 1])
    assert raw > 0.2, f"the fixture does not carry the artefact ({raw})"
    assert stacked < raw / 20.0, f"mesh survived the stack: {raw} -> {stacked}"
