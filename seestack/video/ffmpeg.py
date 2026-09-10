"""Thin, memory-bounded wrapper around the bundled ``ffmpeg``/``ffprobe`` binaries.

Video decoding is the one thing we can't do with the existing Python stack, and
a Seestar lunar capture is a normal H.264 ``.mp4``. Rather than pull in a heavy
Python codec dependency we shell out to ``ffmpeg`` (bundled in the Docker image),
piping **raw RGB frames** back over stdout and yielding them one at a time — a
1-minute 1080p capture is ~1800 frames / ~11 GB of pixels, so nothing here may
ever hold more than a frame at a time (the engine's standing memory discipline).

Both binaries are looked up on ``PATH`` unless ``SEESTACK_FFMPEG_PATH`` /
``SEESTACK_FFPROBE_PATH`` point elsewhere, so a user who mounts their own build
(or runs outside the container) can still use the feature.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

#: Longest we'll wait for a *probe* (metadata only — it never decodes the file).
PROBE_TIMEOUT_S = 60


class VideoToolsMissing(RuntimeError):
    """``ffmpeg``/``ffprobe`` isn't installed, so video captures can't be read."""


def ffmpeg_path() -> str | None:
    """Absolute path to ``ffmpeg``, or ``None`` if it isn't installed."""
    override = os.environ.get("SEESTACK_FFMPEG_PATH")
    if override:
        return override if Path(override).exists() else None
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    """Absolute path to ``ffprobe``, or ``None`` if it isn't installed."""
    override = os.environ.get("SEESTACK_FFPROBE_PATH")
    if override:
        return override if Path(override).exists() else None
    return shutil.which("ffprobe")


def ffmpeg_available() -> bool:
    """True when both binaries are present, i.e. video stacking can run.

    Every user-facing surface checks this first so a container without ffmpeg
    explains itself instead of failing halfway through a job.
    """
    return ffmpeg_path() is not None and ffprobe_path() is not None


@dataclass(frozen=True)
class VideoInfo:
    """What ``ffprobe`` can tell us about a capture without decoding it."""

    width: int
    height: int
    #: Best-effort frame count. Containers often omit ``nb_frames``, in which
    #: case this is ``duration × fps`` — good enough to plan sampling, which is
    #: why :attr:`n_frames_exact` says whether to trust it precisely.
    n_frames: int
    n_frames_exact: bool
    fps: float
    duration_s: float
    #: The stream's own pixel format as ffprobe reports it (``""`` when it
    #: doesn't say). Load-bearing: a **single-channel** stream is carrying the
    #: sensor's raw colour-filter mosaic, which has to be debayered rather than
    #: stacked as luminance — see :func:`source_is_cfa_mosaic`.
    pix_fmt: str = ""

    @property
    def megapixels(self) -> float:
        return (self.width * self.height) / 1e6


def _parse_fraction(text: str | None) -> float:
    """Parse ffprobe's ``"30000/1001"``-style rate fields; 0.0 when unusable."""
    if not text:
        return 0.0
    try:
        if "/" in text:
            num, _, den = text.partition("/")
            d = float(den)
            return float(num) / d if d else 0.0
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def probe_video(path: str | Path) -> VideoInfo:
    """Read a capture's dimensions / frame count / duration via ``ffprobe``.

    Raises :class:`VideoToolsMissing` when ffprobe isn't installed and
    ``ValueError`` when the file has no decodable video stream (a stray
    non-video file in a ``_video/`` folder, or a truncated copy).
    """
    exe = ffprobe_path()
    if exe is None:
        raise VideoToolsMissing("ffprobe is not installed")
    cmd = [
        exe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,nb_frames,avg_frame_rate,duration,pix_fmt",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, timeout=PROBE_TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover — pathological file
        raise ValueError(f"ffprobe timed out reading {Path(path).name}") from exc
    if out.returncode != 0:
        detail = out.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ValueError(
            f"ffprobe could not read {Path(path).name}"
            + (f": {detail[-1]}" if detail else "")
        )
    try:
        data = json.loads(out.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"ffprobe returned no usable metadata for {Path(path).name}") from exc

    streams = data.get("streams") or []
    if not streams:
        raise ValueError(f"{Path(path).name} has no video stream")
    st = streams[0]
    width = int(st.get("width") or 0)
    height = int(st.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError(f"{Path(path).name} has no usable video dimensions")

    fps = _parse_fraction(st.get("avg_frame_rate"))
    duration = _parse_fraction(st.get("duration")) or _parse_fraction(
        (data.get("format") or {}).get("duration")
    )

    n_frames = 0
    exact = False
    raw_nb = st.get("nb_frames")
    if raw_nb not in (None, "", "N/A"):
        try:
            n_frames = int(raw_nb)
            exact = n_frames > 0
        except (TypeError, ValueError):
            n_frames = 0
    if n_frames <= 0 and fps > 0 and duration > 0:
        # No frame count in the container (common for .avi and some phone
        # recordings) — estimate it so sampling can still be planned.
        n_frames = int(round(duration * fps))
    return VideoInfo(
        width=width,
        height=height,
        n_frames=max(0, n_frames),
        n_frames_exact=exact,
        fps=fps,
        duration_s=duration,
        pix_fmt=str(st.get("pix_fmt") or ""),
    )


#: Pixel formats that mean "one byte (or word) per pixel, straight off the
#: sensor" — i.e. the frame is the **raw colour-filter mosaic**, not a picture.
#:
#: ``pal8`` is the one the Seestar actually writes (measured on the owner's
#: ``…-Solar-RAW.avi``: ``rawvideo``, ``pal8``, and 1.00026 bytes per pixel over
#: the whole file). The byte at each pixel is a palette *index* that is the raw
#: sensor value, and the palette is the identity grey ramp — which is exactly how
#: the mosaic used to reach the stack as a luminance checkerboard.
#:
#: ``bayer_*`` formats are deliberately **absent**: ffmpeg debayers those itself
#: on the way to ``rgb24``, so treating one as a mosaic would debayer it twice.
_MOSAIC_PIX_FMT_PREFIXES = ("gray", "mono")
_MOSAIC_PIX_FMTS = frozenset({"pal8"})


def source_is_cfa_mosaic(pix_fmt: str | None) -> bool:
    """Is a stream in this pixel format carrying an undebayered sensor mosaic?

    True for the single-channel families (``pal8``, ``gray*``, ``mono*``), which
    is how solar/planetary capture is normally recorded — precisely so lucky
    imaging gets unprocessed frames. False for every colour format, and
    **deliberately false for ffmpeg's own ``bayer_*`` formats**, which the
    decoder already demosaics on the way to ``rgb24``.
    """
    fmt = (pix_fmt or "").strip().lower()
    if not fmt or fmt.startswith("bayer"):
        return False
    return fmt in _MOSAIC_PIX_FMTS or fmt.startswith(_MOSAIC_PIX_FMT_PREFIXES)


#: The two colour-filter phases one Seestar sensor can reach a demosaic in, and
#: why a single constant was the wrong shape for this. The deep-sky path reads
#: ``BAYERPAT`` out of the FITS header and only *falls back* to ``RGGB``
#: (``seestack/io/fits_loader.py``); video carries no header, so taking the same
#: name as a constant here was an assumption, not a device fact.
#:
#: **Measured on the owner's own** ``2026-06-19-175558-Solar-RAW.avi``, as the
#: mean of each 2×2 sub-lattice inside the disk: ``(0,0)`` 40.7, ``(0,1)`` 10.2,
#: ``(1,0)`` 131.7, ``(1,1)`` 40.7. The two *matched* values are the two green
#: photosites, and they sit on the **main** diagonal — where ``RGGB`` puts red
#: and blue, which here are 13:1 apart. Debayering it as ``RGGB`` therefore
#: averaged the darkest and brightest sites together to make "green": that is
#: both the **green Sun** the owner reported after v0.347.0 and the alternating
#: residual (mesh, 40.50) that the same fix was supposed to remove. ``GBRG``
#: leaves 0.00 residual and a red/orange disk — physically right for a
#: white-light solar filter.
#:
#: ⚠️ **CFA phase and frame orientation are one coupled invariant.** ``RGGB``
#: row-flipped is *exactly* ``GBRG``, which is almost certainly why the two
#: paths disagree: AVI is conventionally stored bottom-up, so the rows reach
#: this demosaic in the opposite order from the FITS path. If a future change
#: ever flips a video frame vertically to fix its orientation, **the pattern
#: flips with it** and the green Sun comes straight back. Detection below makes
#: that self-correcting, and
#: ``test_video_cfa_mosaic.py::test_the_two_patterns_are_one_row_flip_apart``
#: pins the relationship so neither can be changed alone.
CFA_PATTERN_GREEN_ANTIDIAGONAL = "RGGB"
CFA_PATTERN_GREEN_DIAGONAL = "GBRG"

#: What to debayer as when a frame carries no colour information to read — the
#: measured phase of the owner's real capture, not the deep-sky path's name.
CFA_PATTERN = CFA_PATTERN_GREEN_DIAGONAL

#: The green pair must be at least this many times better matched than the other
#: diagonal before :func:`detect_cfa_pattern` believes itself. On the owner's
#: file the two diagonals are 0.0 and 121.5 DN apart, so the real margin is
#: enormous; this only has to exclude the ambiguous middle.
_CFA_DETECT_MATCH_RATIO = 0.5

#: …and the *un*matched diagonal must be separated by at least this many DN at
#: all, so shot noise on a genuinely flat frame (a dark, a blank sky, a blown
#: disk) cannot elect a diagonal out of nothing. Each sub-lattice mean averages
#: a quarter of the frame, so its noise is well under a tenth of a DN.
_CFA_DETECT_MIN_SPREAD_DN = 1.0


def detect_cfa_pattern(mosaic: np.ndarray) -> str:
    """Which colour-filter phase this raw sensor plane is in.

    Reads the answer off the frame instead of asserting it, because the one
    thing video has no way to state is its own ``BAYERPAT``. The two green
    photosites of a Bayer 2×2 see the *same* filter, so their sub-lattice means
    match to within noise while red's and blue's do not — which identifies the
    green **diagonal** objectively, from four means over one frame.

    Green on the anti-diagonal is ``RGGB``; green on the main diagonal is
    ``GBRG``. Red-vs-blue *within* the winning pair cannot be read from a mosaic
    at all (``GBRG`` and ``GRBG`` differ only by swapping them, and both leave
    zero residual), so that stays the device fact the owner's measurement
    establishes: on this sensor the brighter site through a white-light solar
    filter is red.

    Returns :data:`CFA_PATTERN` when the frame is too flat to call, so a dark or
    an unexposed capture degrades to the measured default rather than to a coin
    toss.
    """
    a = np.asarray(mosaic)
    if a.ndim != 2:
        raise ValueError("mosaic must be 2D")
    # Crop to even dimensions: an odd trailing row/column would put a different
    # count of pixels behind each phase and bias the means it decides on.
    h, w = a.shape[0] - a.shape[0] % 2, a.shape[1] - a.shape[1] % 2
    if h < 2 or w < 2:
        return CFA_PATTERN
    a = a[:h, :w].astype(np.float64)
    means = {(i, j): float(a[i::2, j::2].mean()) for i in (0, 1) for j in (0, 1)}
    diagonal = abs(means[(0, 0)] - means[(1, 1)])
    antidiagonal = abs(means[(0, 1)] - means[(1, 0)])
    matched, unmatched = sorted((diagonal, antidiagonal))
    if unmatched < _CFA_DETECT_MIN_SPREAD_DN:
        return CFA_PATTERN  # nothing to read — a flat or unexposed frame
    if matched > unmatched * _CFA_DETECT_MATCH_RATIO:
        return CFA_PATTERN  # both diagonals equally mismatched: not a call
    if diagonal < antidiagonal:
        return CFA_PATTERN_GREEN_DIAGONAL
    return CFA_PATTERN_GREEN_ANTIDIAGONAL


def iter_frames(
    path: str | Path,
    *,
    stride: int = 1,
    width: int | None = None,
    height: int | None = None,
    pix_fmt: str | None = None,
    wanted: Collection[int] | None = None,
) -> Iterator[np.ndarray | None]:
    """Stream a capture's frames as ``(H, W, 3)`` uint8 RGB arrays.

    One frame is materialised at a time — the generator reads exactly
    ``H·W·3`` bytes off ffmpeg's stdout per iteration and never buffers the
    decoded video. Abandoning the generator (``break``, an exception, a
    cancelled job) kills the subprocess in the ``finally``, so a stopped stack
    doesn't leave an ffmpeg decoding the rest of the file.

    ``stride`` > 1 keeps every *n*-th frame, done inside ffmpeg's ``select``
    filter so the skipped frames are never piped at all. The kept frames are the
    same ones on every pass (``n mod stride == 0``), which is what lets the
    two-pass lucky stack grade in pass 1 and re-decode exactly those frames in
    pass 2.

    ``width``/``height``/``pix_fmt`` may be passed to skip a redundant probe;
    the dimensions must match the stream or the byte framing is wrong (so pass
    them only from a :func:`probe_video` result for the same file).

    ``wanted`` names the yielded indices the caller will actually *use* (the
    same index its own ``enumerate`` sees). A frame outside it is decoded — the
    byte framing demands that — but not demosaiced, and is yielded as **None**
    rather than skipped, so the caller's ``enumerate`` still lines up with an
    index set it computed on an earlier pass. ``None``, not the raw array: an
    un-demosaiced mosaic looks enough like a picture that a future caller would
    eventually stack one by mistake. This is what stops the lucky stack's second
    pass paying ~350 ms of demosaic per frame for the frames it is about to
    discard (a two-thirds saving on a 4,487-frame solar capture at the default
    keep percentage); the result is bit-identical either way.

    **A single-channel source is debayered here**, once, so every consumer
    downstream sees the same ``(H, W, 3)`` picture and nothing can demosaic
    twice. Solar and planetary video is normally recorded as the raw sensor
    mosaic (see :func:`source_is_cfa_mosaic`); left alone, that mosaic reaches
    the stack as a luminance checkerboard and — because the disk is static and
    the pattern is sensor-fixed — *adds coherently* across every kept frame
    instead of averaging down, which is the fine "mesh" the owner reported over
    a stacked Sun.

    **Why the decode still asks for ``rgb24``, which looks like the bug and is
    not.** Measured on a `pal8` fixture with the identity grey palette the
    Seestar writes: ``rgb24`` returns ``R == G == B ==`` the raw sensor byte,
    *exactly*, so one channel of it **is** the mosaic. The obvious-looking
    ``-pix_fmt gray`` is the one that loses data — ffmpeg routes it through an
    RGB→luma step and it came back off by up to 1 DN on the same fixture. So
    the honest raw plane is already on the wire; the bug was only that nobody
    demosaiced it. Keeping the decode command untouched also keeps the byte
    framing, the truncated-tail handling and the memory bound exactly as they
    were.

    The ``R == G == B`` equality is *verified on the first frame* rather than
    assumed, because a ``pal8`` stream whose palette is not a grey ramp would
    decode to real colour — in which case the frame is passed through
    untouched, since demosaicing it would be nonsense.
    """
    exe = ffmpeg_path()
    if exe is None:
        raise VideoToolsMissing("ffmpeg is not installed")
    if width is None or height is None or pix_fmt is None:
        info = probe_video(path)
        width, height = info.width, info.height
        if pix_fmt is None:
            pix_fmt = info.pix_fmt
    mosaic_source = source_is_cfa_mosaic(pix_fmt)
    demosaic: bool | None = None  # decided on the first frame, then latched
    pattern = CFA_PATTERN  # ditto — the sensor's phase cannot change mid-stream

    stride = max(1, int(stride))
    cmd = [exe, "-v", "error", "-nostdin", "-i", str(path)]
    if stride > 1:
        cmd += ["-vf", f"select=not(mod(n\\,{stride}))", "-vsync", "0"]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]

    frame_bytes = width * height * 3
    # stderr → DEVNULL rather than a pipe nobody drains: with a pipe, a chatty
    # decoder could fill the buffer and deadlock while we block reading stdout.
    proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        assert proc.stdout is not None
        index = -1
        while True:
            buf = proc.stdout.read(frame_bytes)
            if not buf:
                break
            if len(buf) < frame_bytes:
                # A truncated tail frame (partial write / cut-short recording):
                # stop cleanly rather than yielding a garbled array.
                log.debug("ignoring %d trailing bytes of %s", len(buf), Path(path).name)
                break
            # Copy off the pipe buffer: ``frombuffer`` views immutable bytes, so
            # the array would be read-only and blow up on any in-place caller.
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3).copy()
            index += 1
            keep = wanted is None or index in wanted
            if mosaic_source:
                # Latch the "is this really a mosaic" decision on the first frame
                # off the wire whatever ``wanted`` says: the evidence is the same
                # in every frame, and deferring it to the first *kept* frame would
                # make the answer depend on which frames a caller happened to
                # want. The test is cheap (two array compares); only the demosaic
                # itself is worth skipping.
                if demosaic is None:
                    demosaic = _channels_agree(frame)
                    if demosaic:
                        # Latched here for the same reason, and it matters more:
                        # the phase is a property of the sensor, so re-reading it
                        # per frame could only ever make the *colours change
                        # mid-capture* if one frame were too flat to call.
                        pattern = detect_cfa_pattern(frame[..., 0])
                        log.info(
                            "%s is a raw sensor mosaic — debayering it as %s",
                            Path(path).name, pattern,
                        )
                    else:
                        log.info(
                            "%s reports %s but decodes to real colour — leaving it "
                            "alone rather than demosaicing a picture",
                            Path(path).name, pix_fmt,
                        )
                if demosaic and keep:
                    frame = _demosaic_frame(frame, pattern=pattern)
            yield frame if keep else None
    finally:
        if proc.poll() is None:
            proc.kill()
        if proc.stdout is not None:
            proc.stdout.close()
        proc.wait()


def _channels_agree(frame: np.ndarray) -> bool:
    """Is every pixel of this decoded frame grey (``R == G == B``)?

    The evidence that the three channels carry one sensor plane replicated,
    rather than real colour — see :func:`iter_frames`.
    """
    return bool(
        np.array_equal(frame[..., 0], frame[..., 1])
        and np.array_equal(frame[..., 1], frame[..., 2])
    )


def _demosaic_frame(frame: np.ndarray, *, pattern: str = CFA_PATTERN) -> np.ndarray:
    """Turn a replicated-mosaic ``rgb24`` frame into a real colour frame.

    Reuses the engine's own :func:`~seestack.io.fits_loader.bilinear_debayer` —
    the same one the deep-sky path has always used — rather than growing a
    second demosaic here. It preserves dtype, so the ``uint8`` contract this
    generator promises is unchanged, and the frame is **not** transposed or
    flipped on the way in: CFA phase depends on true row/column parity, so a
    flip would silently swap colours while looking "fixed" — see
    :data:`CFA_PATTERN_GREEN_DIAGONAL` for what that cost the owner once.

    ``pattern`` comes from :func:`detect_cfa_pattern` on the stream's first
    frame; the default is only for a caller demosaicing one frame on its own.
    """
    from seestack.io.fits_loader import bilinear_debayer

    return bilinear_debayer(frame[..., 0], pattern=pattern)
