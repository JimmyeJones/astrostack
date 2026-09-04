"""Synthetic Seestar-style video captures for the lucky-imaging tests.

Mirrors ``tests/synth.py`` (which writes synthetic FITS subs) for the video
path: builds frames in NumPy and encodes them with the same ``ffmpeg`` binary
the engine decodes with, so the tests exercise the real decoder rather than a
stand-in.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from seestack.video.ffmpeg import ffmpeg_path


def lunar_frame(
    w: int, h: int, *, cx: float, cy: float, radius: float, sharpness: float,
    seed: int = 0, noise: float = 3.0,
) -> np.ndarray:
    """One synthetic 'lunar disk' frame as (h, w, 3) uint8.

    ``sharpness`` in 0..1 scales the contrast of the surface detail (craters);
    a low value is what atmospheric seeing does to a bad frame. The disk itself
    stays the same size and brightness so the sharpness ranking can only be
    driven by the detail, not by the exposure.
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(xx - cx, yy - cy)
    # Soft-edged disk (a couple of px of limb softening, like the real thing).
    disk = np.clip((radius - r) / 2.0 + 0.5, 0.0, 1.0)
    base = 150.0 * disk

    # Fine "craters": a high-frequency pattern whose amplitude is what
    # ``sharpness`` varies, so a sharp frame has crisp detail and a soft one has
    # the same disk with the detail washed out. The pattern is measured from the
    # disk *centre*, so the surface moves with the disk exactly as the real
    # Moon's does — otherwise aligning on the disk would misalign the detail and
    # the alignment test would be measuring the synth, not the stacker.
    dx = xx - cx
    dy = yy - cy
    detail = (
        np.sin(dx * 1.1) * np.cos(dy * 0.9)
        + np.sin((dx + dy) * 0.7)
    ).astype(np.float32)
    img = base + 45.0 * sharpness * detail * disk

    rng = np.random.default_rng(seed)
    img = img + rng.normal(0.0, noise, size=img.shape).astype(np.float32)
    u8 = np.clip(img, 0, 255).astype(np.uint8)
    return np.repeat(u8[..., None], 3, axis=2)


def write_video(path: Path, frames: Iterable[np.ndarray], *, fps: int = 10) -> Path:
    """Encode ``frames`` ((h, w, 3) uint8) into a video file with ffmpeg.

    Uses a visually lossless H.264 setting so the decoded pixels are close
    enough to the source for the tests to reason about, while still going
    through a real container/codec round trip.
    """
    exe = ffmpeg_path()
    if exe is None:  # pragma: no cover — guarded by the tests' skip marker
        raise RuntimeError("ffmpeg not installed")
    frames = list(frames)
    if not frames:
        raise ValueError("no frames")
    h, w = frames[0].shape[:2]
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        exe, "-v", "error", "-y", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0",
        "-pix_fmt", "yuv444p",
        str(path),
    ]
    proc = subprocess.run(
        cmd, input=b"".join(f.astype(np.uint8).tobytes() for f in frames),
        capture_output=True, check=False,
    )
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(
            "ffmpeg encode failed: " + proc.stderr.decode("utf-8", "replace")[-400:]
        )
    return path


#: Relative transmission of the four RGGB photosites on a solar continuum —
#: the physical reason an undebayered mosaic reads as a fine bright/dark
#: checkerboard rather than as a flat disk. Exaggerated a little so a test can
#: measure the pattern without needing thousands of frames.
_CFA_TRANSMISSION = {"R": 1.00, "G": 0.80, "B": 0.55}


def solar_mosaic_frame(
    w: int, h: int, *, cx: float, cy: float, radius: float,
    sharpness: float = 1.0, seed: int = 0, noise: float = 2.0,
) -> np.ndarray:
    """One synthetic **raw sensor mosaic** frame as (h, w) uint8.

    A near-uniform solar disk sampled through an RGGB colour filter array: the
    scene itself is smooth, so *every* 2-px structure in the result comes from
    the filter. Single channel, exactly as a raw capture is recorded.
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(xx - cx, yy - cy)
    disk = np.clip((radius - r) / 2.0 + 0.5, 0.0, 1.0)
    dx, dy = xx - cx, yy - cy
    detail = (np.sin(dx * 0.35) * np.cos(dy * 0.31)).astype(np.float32)
    scene = 200.0 * disk + 25.0 * sharpness * detail * disk + 8.0

    gain = np.empty((h, w), dtype=np.float32)
    gain[0::2, 0::2] = _CFA_TRANSMISSION["R"]
    gain[0::2, 1::2] = _CFA_TRANSMISSION["G"]
    gain[1::2, 0::2] = _CFA_TRANSMISSION["G"]
    gain[1::2, 1::2] = _CFA_TRANSMISSION["B"]

    rng = np.random.default_rng(seed)
    img = scene * gain + rng.normal(0.0, noise, size=scene.shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def write_pal8_video(path: Path, planes: Iterable[np.ndarray], *, fps: int = 10) -> Path:
    """Encode single-channel ``planes`` as a **pal8 rawvideo AVI**.

    This is the shape the Seestar actually writes (measured on the owner's
    ``…-Solar-RAW.avi``: ``rawvideo`` / ``pal8`` / one byte per pixel), with the
    identity grey-ramp palette that makes each byte the raw sensor value.
    ffmpeg's rawvideo pal8 layout is ``w*h`` index bytes followed by a 1024-byte
    palette per frame, so the palette is written explicitly rather than left to
    a quantiser — a quantised palette would not be the file under test.
    """
    exe = ffmpeg_path()
    if exe is None:  # pragma: no cover — guarded by the tests' skip marker
        raise RuntimeError("ffmpeg not installed")
    planes = list(planes)
    if not planes:
        raise ValueError("no frames")
    h, w = planes[0].shape[:2]
    ramp = np.arange(256, dtype=np.uint8)
    palette = np.stack([ramp, ramp, ramp, np.full(256, 255, np.uint8)], axis=1)
    payload = b"".join(
        np.ascontiguousarray(p, dtype=np.uint8).tobytes() + palette.tobytes()
        for p in planes
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        exe, "-v", "error", "-y", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "pal8",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-c:v", "rawvideo", "-pix_fmt", "pal8",
        str(path),
    ]
    proc = subprocess.run(cmd, input=payload, capture_output=True, check=False)
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(
            "ffmpeg encode failed: " + proc.stderr.decode("utf-8", "replace")[-400:]
        )
    return path


def solar_raw_video(
    path: Path, *, n_frames: int = 12, w: int = 96, h: int = 72,
    sharp_indices: Iterable[int] = (), fps: int = 10,
) -> Path:
    """A short **undebayered** solar capture, in the owner's real file shape.

    The disk does not move — a solar/planetary capture is a static target, which
    is exactly why a sensor-fixed pattern accumulates through the stack instead
    of averaging away.
    """
    sharp = set(sharp_indices)
    planes = [
        solar_mosaic_frame(
            w, h, cx=w / 2, cy=h / 2, radius=min(w, h) * 0.35,
            sharpness=1.0 if i in sharp else 0.2, seed=i,
        )
        for i in range(n_frames)
    ]
    return write_pal8_video(path, planes, fps=fps)


def lunar_video(
    path: Path, *, n_frames: int = 12, w: int = 96, h: int = 72,
    sharp_indices: Iterable[int] = (), drift_px: float = 0.0, fps: int = 10,
) -> Path:
    """A short capture where ``sharp_indices`` are the good-seeing frames.

    ``drift_px`` moves the disk linearly across the capture, so alignment has
    something real to correct.
    """
    sharp = set(sharp_indices)
    frames = []
    for i in range(n_frames):
        t = i / max(1, n_frames - 1)
        frames.append(lunar_frame(
            w, h,
            cx=w / 2 + drift_px * t, cy=h / 2 + drift_px * t * 0.5,
            radius=min(w, h) * 0.35,
            sharpness=1.0 if i in sharp else 0.15,
            seed=i,
        ))
    return write_video(path, frames, fps=fps)
