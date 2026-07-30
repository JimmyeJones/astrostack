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
from collections.abc import Iterator
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
        "-show_entries", "stream=width,height,nb_frames,avg_frame_rate,duration",
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
    )


def iter_frames(
    path: str | Path,
    *,
    stride: int = 1,
    width: int | None = None,
    height: int | None = None,
) -> Iterator[np.ndarray]:
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

    ``width``/``height`` may be passed to skip a redundant probe; they must
    match the stream or the byte framing is wrong (so pass them only from a
    :func:`probe_video` result for the same file).
    """
    exe = ffmpeg_path()
    if exe is None:
        raise VideoToolsMissing("ffmpeg is not installed")
    if width is None or height is None:
        info = probe_video(path)
        width, height = info.width, info.height

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
            yield np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3).copy()
    finally:
        if proc.poll() is None:
            proc.kill()
        if proc.stdout is not None:
            proc.stdout.close()
        proc.wait()
