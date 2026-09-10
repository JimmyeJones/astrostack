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
    each other, and the disk reads warm through the colour filter, not grey."""
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


# --- ...and in the phase the sensor actually used -------------------------
#
# The v0.347.0 fix above was right that the mosaic needed debayering and wrong
# about which pattern: it took ``RGGB`` from the deep-sky path, where it is read
# out of the FITS ``BAYERPAT`` header, and hard-coded it for video, which has no
# header to read. The owner's Sun came back **green** and still meshed.


#: The mean of each 2×2 sub-lattice inside the disk of the owner's own
#: ``incoming/Solar_video/2026-06-19-175558-Solar-RAW.avi``, measured on the
#: file. The two *matched* values are the two green photosites and they sit on
#: the **main** diagonal, which is ``GBRG``; ``RGGB`` would put green on the two
#: sites that are 13:1 apart.
_OWNERS_MEASURED_SITES = {(0, 0): 40.7, (0, 1): 10.2, (1, 0): 131.7, (1, 1): 40.7}


def _mosaic_from_sites(sites, size=64):
    """A synthetic mosaic laid down from four measured sub-lattice means."""
    m = np.zeros((size, size), dtype=np.float32)
    for (i, j), v in sites.items():
        m[i::2, j::2] = v
    return m


def test_the_owners_measured_sites_say_green_is_on_the_main_diagonal():
    """**The bug, at the arithmetic that settles it.** Four numbers off the
    owner's real file are enough to identify the green pair objectively — the
    two green photosites see the same filter, so their means match — and they
    are the main diagonal, i.e. ``GBRG`` and not the shipped ``RGGB``."""
    from seestack.video.ffmpeg import detect_cfa_pattern

    assert detect_cfa_pattern(_mosaic_from_sites(_OWNERS_MEASURED_SITES)) == "GBRG"


def test_debayering_the_owners_frame_as_rggb_is_what_made_the_sun_green():
    """Both symptoms from one cause, reproduced from those four numbers alone.

    ``RGGB`` averages the darkest and brightest sites together to make "green",
    which is the green cast *and* a huge alternating residual — the mesh that
    survived v0.347.0. ``GBRG`` leaves none of either and a red/orange disk,
    which is what a white-light solar filter physically gives you.

    Fails before: ``CFA_PATTERN`` was ``"RGGB"``."""
    from seestack.io.fits_loader import bilinear_debayer
    from seestack.video.ffmpeg import CFA_PATTERN, detect_cfa_pattern

    mosaic = _mosaic_from_sites(_OWNERS_MEASURED_SITES)
    chosen = detect_cfa_pattern(mosaic)

    def measure(pattern):
        rgb = bilinear_debayer(mosaic, pattern=pattern)[8:-8, 8:-8]
        luma = rgb.mean(axis=2)
        phases = [luma[i::2, j::2].mean() for i in (0, 1) for j in (0, 1)]
        return [float(rgb[..., c].mean()) for c in range(3)], float(
            max(phases) - min(phases))

    (r, g, b), residual = measure(chosen)
    assert r > g > b, f"the Sun is not red/orange under {chosen}: {r}:{g}:{b}"
    assert residual < 0.01, f"{chosen} left a mesh behind ({residual})"

    # ...and the shipped answer really was the bad one, not a wash.
    (r_bad, g_bad, b_bad), residual_bad = measure("RGGB")
    assert g_bad > r_bad and g_bad > b_bad, "RGGB was supposed to read green"
    assert residual_bad > 10.0, f"RGGB was supposed to mesh ({residual_bad})"

    # The default for a frame with nothing to read is the measured phase too.
    assert CFA_PATTERN == "GBRG"


@pytest.mark.parametrize("pattern", ["GBRG", "RGGB"])
def test_a_raw_capture_is_debayered_in_its_own_phase(tmp_path, pattern):
    """**The regression, end to end through the decoder.** A capture recorded in
    either phase comes back red-dominant and mesh-free, because the phase is
    read off the frame instead of asserted.

    Fails before on ``GBRG`` — the owner's real phase — with a green disk and
    the mesh intact; the ``RGGB`` case is the pre-existing behaviour, pinned so
    that reading the phase cannot regress the captures that already worked."""
    path = solar_raw_video(
        tmp_path / "Solar_video.avi", n_frames=4, w=64, h=48, pattern=pattern)
    frame = next(iter(iter_frames(path)))

    r, g, b = (float(frame[..., c].mean()) for c in range(3))
    assert r > g > b, f"{pattern} decoded to the wrong colour: {r}:{g}:{b}"
    assert _mesh_strength(frame[..., 1]) < 0.05


def test_the_two_patterns_are_one_row_flip_apart():
    """The coupled invariant the module comment warns about, pinned.

    ``RGGB`` row-flipped **is** ``GBRG`` — which is almost certainly why the
    video and FITS paths disagree at all (AVI is stored bottom-up). So if a
    future change ever flips a video frame vertically to fix its orientation,
    the pattern has to flip with it or the green Sun comes back. This test fails
    if either constant is changed on its own."""
    from seestack.io.fits_loader import bilinear_debayer
    from seestack.video.ffmpeg import (
        CFA_PATTERN_GREEN_ANTIDIAGONAL,
        CFA_PATTERN_GREEN_DIAGONAL,
        detect_cfa_pattern,
    )

    rng = np.random.default_rng(7)
    mosaic = rng.uniform(10, 200, size=(32, 32)).astype(np.float32)

    upright = bilinear_debayer(mosaic, pattern=CFA_PATTERN_GREEN_ANTIDIAGONAL)
    flipped = bilinear_debayer(mosaic[::-1], pattern=CFA_PATTERN_GREEN_DIAGONAL)
    assert np.allclose(upright, flipped[::-1])

    # And the detector agrees about which name goes with which diagonal.
    sites = _OWNERS_MEASURED_SITES
    assert detect_cfa_pattern(_mosaic_from_sites(sites)) == CFA_PATTERN_GREEN_DIAGONAL
    antidiagonal = {(0, 0): 10.2, (0, 1): 40.7, (1, 0): 40.7, (1, 1): 131.7}
    assert (detect_cfa_pattern(_mosaic_from_sites(antidiagonal))
            == CFA_PATTERN_GREEN_ANTIDIAGONAL)


def test_a_frame_with_nothing_to_read_falls_back_instead_of_guessing():
    """A dark, a blank sky or a blown disk has no colour information in it, and
    a coin toss between two phases would change a capture's colours from one run
    to the next. Those degrade to the measured default."""
    from seestack.video.ffmpeg import CFA_PATTERN, detect_cfa_pattern

    rng = np.random.default_rng(3)
    flat = np.full((64, 64), 32.0, np.float32) + rng.normal(0, 2.0, (64, 64))
    assert detect_cfa_pattern(flat.astype(np.float32)) == CFA_PATTERN
    assert detect_cfa_pattern(np.zeros((64, 64), np.float32)) == CFA_PATTERN
    # Both diagonals mismatched by the same amount is not a call either.
    ambiguous = {(0, 0): 10.0, (0, 1): 20.0, (1, 0): 60.0, (1, 1): 60.0}
    assert detect_cfa_pattern(_mosaic_from_sites(ambiguous)) == CFA_PATTERN
    # A frame too small to hold a whole 2×2 has nothing to average.
    assert detect_cfa_pattern(np.zeros((1, 8), np.float32)) == CFA_PATTERN
    with pytest.raises(ValueError):
        detect_cfa_pattern(np.zeros((8, 8, 3), np.float32))


def test_the_phase_is_read_once_and_reused_for_the_whole_capture(tmp_path, monkeypatch):
    """The sensor's phase cannot change mid-capture, so it is latched on the
    first frame off the wire like the "is this really a mosaic" decision beside
    it. Re-reading it per frame would let one frame too flat to call flip the
    colours halfway through a stack."""
    from seestack.video import ffmpeg as ffmpeg_mod

    path = solar_raw_video(
        tmp_path / "Solar_video.avi", n_frames=6, w=64, h=48, pattern="GBRG")
    calls = 0
    real = ffmpeg_mod.detect_cfa_pattern

    def counted(plane):
        nonlocal calls
        calls += 1
        return real(plane)

    monkeypatch.setattr(ffmpeg_mod, "detect_cfa_pattern", counted)
    frames = list(iter_frames(path))

    assert len(frames) == 6
    assert calls == 1, f"the phase was re-read {calls} times"


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


# --- and without paying for it twice ---------------------------------------

def test_pass_two_does_not_debayer_the_frames_it_is_about_to_discard(tmp_path, monkeypatch):
    """The wait, not the picture. Demosaicing is the expensive part of decoding a
    raw capture — ~350 ms a frame on the owner's 1080×1920 solar file — and pass 2
    used to pay it for *every* frame before dropping all but ``keep_percent`` of
    them one line later. Pass 1 still grades them all (it measures sharpness on
    the colour frame's luma); pass 2 now prepares only the keepers."""
    from seestack.video import ffmpeg as ffmpeg_mod

    path = solar_raw_video(
        tmp_path / "Solar_video.avi", n_frames=12, w=64, h=48, sharp_indices=(2, 5, 8))
    calls = 0
    real = ffmpeg_mod._demosaic_frame

    def counted(frame, *a, **kw):
        nonlocal calls
        calls += 1
        return real(frame, *a, **kw)

    monkeypatch.setattr(ffmpeg_mod, "_demosaic_frame", counted)
    result = stack_video(path, LuckyOptions(keep_percent=50, align=False))

    assert result.n_stacked == 6
    # 12 graded + 6 kept. Before this, both passes debayered all 12 → 24.
    assert calls == 18


def test_the_stacked_picture_is_identical_with_and_without_the_skip(tmp_path, monkeypatch):
    """This is a skip, not a change: the frames that reach the accumulator are
    the same frames, prepared the same way. Pinned against the pre-fix behaviour
    itself — pass 2 with ``wanted`` dropped, i.e. every frame debayered."""
    from seestack.video import lucky as lucky_mod

    path = solar_raw_video(
        tmp_path / "Solar_video.avi", n_frames=12, w=64, h=48, sharp_indices=(1, 4, 7))
    opts = LuckyOptions(keep_percent=50, align=True)
    fast = stack_video(path, opts)

    real_iter = lucky_mod.iter_frames

    def eager(*a, wanted=None, **kw):
        """Pass 2 as it was: debayer every frame, then throw the unwanted ones
        away afterwards."""
        for i, frame in enumerate(real_iter(*a, **kw)):
            yield frame if (wanted is None or i in wanted) else None

    monkeypatch.setattr(lucky_mod, "iter_frames", eager)
    eager_result = stack_video(path, opts)

    assert fast.n_stacked == eager_result.n_stacked
    assert np.array_equal(fast.image, eager_result.image)


def test_a_kept_frame_is_debayered_even_when_the_first_frame_is_discarded(tmp_path):
    """The "is this really a mosaic" test latches on the first frame off the
    wire, which under ``wanted`` may be one nobody asked for. Decide it there
    anyway, or a capture whose first frame is discarded would stack raw mosaics."""
    path = solar_raw_video(tmp_path / "Solar_video.avi", n_frames=6, w=64, h=48)
    every = list(iter_frames(path))
    picked = list(iter_frames(path, wanted={3}))

    assert picked[0] is None
    assert np.array_equal(picked[3], every[3])
    assert _mesh_strength(picked[3][..., 1]) < 0.05
