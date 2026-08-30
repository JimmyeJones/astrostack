"""A short looping "zoom clip" of one finished picture — a slow glide from the
whole frame into the object and back out.

The app already exports a finished stack well as a *still* (share JPEG, wallpaper,
keepsake, recap poster), but the places a Seestar beginner actually posts —
Instagram, WhatsApp status, a group chat — reward motion: a slow push-in on a
galaxy reads as "look what I made" in a way a static frame does not, and it is the
one format a non-expert has no tool to produce. This is that clip, with no craft
required: fixed timing, fixed zoom, no music, no text.

**Spatial, not temporal.** Two animations already exist and both show a stack
*accumulating over time* — :mod:`seestack.render.deepening` (night after night)
and the in-stack progress reel. This is a camera move over **one** finished frame,
answering a different question ("show people my picture"), so it lives beside them
rather than inside either.

**Everything here is pure and deterministic.** The keyframe schedule is derived
from the frame index alone — no clock, no RNG — so a given picture always produces
the same clip and the whole module is unit-testable. The way out is the way in
*reversed*, which makes the loop seamless by construction and means only the
push-in half is ever rendered or held in memory.

**Where the pixels come from.** Callers pass the finished **preview PNG** — the
bytes every other share surface uses, and the only rendering of a run that is
right for every kind of run (a plain autostretch, an editor export, or a
"Process target" Auto edit, whose preview is the only place its recipe is baked).
That preview is capped at 1024 px wide, so the output size is chosen to keep the
most zoomed-in frame close to native resolution rather than blown up; see
:func:`zoom_clip_size`.
"""

from __future__ import annotations

import logging
import math
from io import BytesIO
from pathlib import Path

log = logging.getLogger(__name__)

#: Long edge of the finished clip, in pixels. Small enough that the deepest
#: zoom is barely upscaled from a 1024-wide preview (see :func:`zoom_clip_size`),
#: large enough to look sharp in a phone feed.
CLIP_LONG_EDGE = 640
#: How far in the camera travels. 1.8× is a definite move without cropping so
#: hard that a wide nebula loses its shape.
CLIP_ZOOM = 1.8
#: Frames per second, and the shape of the ~6 s move: in, hold, out, hold.
CLIP_FPS = 12
CLIP_IN_SECONDS = 2.0
CLIP_HOLD_SECONDS = 0.7
#: The pause on the full frame at each end of the loop, so it reads as a loop
#: rather than a jitter.
CLIP_WIDE_HOLD_MS = 900


def zoom_clip_size(width: int, height: int, *, zoom: float = CLIP_ZOOM,
                   long_edge: int = CLIP_LONG_EDGE) -> tuple[int, int]:
    """Output size for a clip made from a ``width × height`` picture.

    Capped at ``long_edge``, and capped again at what the *most zoomed-in* frame
    actually contains (``source / zoom``) so the end of the move is never
    upscaled by more than rounding. A big picture therefore gives a 640 px clip
    and a small one gives a smaller, still-sharp clip — the same
    "never upsample" rule the wallpaper export follows.
    """
    if width <= 0 or height <= 0:
        return (0, 0)
    zoom = max(1.0, float(zoom))
    scale = min(1.0, long_edge / max(width, height), 1.0 / zoom)
    return (max(1, round(width * scale)), max(1, round(height * scale)))


def ease_in_out(t: float) -> float:
    """Smooth 0→1 easing (a raised cosine), so the camera starts and stops gently
    instead of snapping into motion. ``t`` outside 0..1 is clamped."""
    t = min(1.0, max(0.0, float(t)))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def crop_box_for_scale(width: int, height: int, focus_xy: tuple[float, float] | None,
                       scale: float) -> tuple[int, int, int, int]:
    """The ``(left, top, right, bottom)`` box showing ``1/scale`` of the picture,
    centred on ``focus_xy`` (the image centre when it is ``None``) and slid back
    inside the frame rather than clamped to a different shape — so a target near
    an edge still fills the zoomed frame with picture instead of blank border.
    """
    scale = max(1.0, float(scale))
    box_w = max(1, min(width, round(width / scale)))
    box_h = max(1, min(height, round(height / scale)))
    if focus_xy is None:
        cx, cy = width / 2.0, height / 2.0
    else:
        cx, cy = float(focus_xy[0]), float(focus_xy[1])
        if not (cx == cx and cy == cy):  # NaN → centre
            cx, cy = width / 2.0, height / 2.0
    left = int(round(cx - box_w / 2.0))
    top = int(round(cy - box_h / 2.0))
    left = max(0, min(left, width - box_w))
    top = max(0, min(top, height - box_h))
    return (left, top, left + box_w, top + box_h)


def brightness_centroid(img, *, percentile: float = 99.0) -> tuple[float, float] | None:
    """Where the *bright stuff* sits in ``img`` — the intensity-weighted centre of
    its brightest pixels — or ``None`` when the picture is flat or unreadable.

    This is the fallback focus for a run with no plate solve (or no catalogued
    position), so the camera still moves toward the object rather than blindly to
    the middle of the frame. Only the top ``percentile`` of pixels vote, so a
    bright galaxy off to one side wins over the sky it is sitting in; a picture
    with no such concentration returns ``None`` and the caller centres.
    """
    import numpy as np

    try:
        lum = np.asarray(img.convert("L"), dtype=np.float32)
    except Exception:  # noqa: BLE001 — an unreadable frame just has no centroid
        return None
    if lum.size == 0 or not np.isfinite(lum).any():
        return None
    cut = float(np.percentile(lum, percentile))
    weights = np.where(lum >= cut, lum - cut, 0.0)
    total = float(weights.sum())
    if not (total > 0.0):
        return None
    ys, xs = np.indices(lum.shape)
    cx = float((weights * xs).sum() / total)
    cy = float((weights * ys).sum() / total)
    if not (math.isfinite(cx) and math.isfinite(cy)):
        return None
    return (cx, cy)


def build_zoom_frames(img, focus_xy: tuple[float, float] | None = None, *,
                      zoom: float = CLIP_ZOOM, fps: int = CLIP_FPS,
                      in_seconds: float = CLIP_IN_SECONDS,
                      hold_seconds: float = CLIP_HOLD_SECONDS,
                      long_edge: int = CLIP_LONG_EDGE) -> tuple[list, list[int]]:
    """``(frames, durations_ms)`` for the whole loop of a push-in on ``img``.

    ``img`` is a PIL RGB image of the finished picture; ``focus_xy`` is where the
    object sits in *its* pixel grid (``None`` centres the move). Frames are PIL
    images all of the same size, and ``durations_ms`` is parallel to them, ready
    for ``save_all``.

    The way out reuses the way in's frame objects in reverse, so the loop closes
    exactly and only ``in_seconds`` worth of frames are ever rendered. The hold at
    the far end is one frame given a long duration rather than many identical
    ones, which keeps both the file and the memory small.
    """
    from PIL import Image

    width, height = img.size
    if width <= 0 or height <= 0:
        return ([], [])
    out_size = zoom_clip_size(width, height, zoom=zoom, long_edge=long_edge)
    n_in = max(2, int(round(max(0.1, in_seconds) * max(1, fps))))
    step_ms = max(1, round(1000.0 / max(1, fps)))

    def _frame(scale: float):
        box = crop_box_for_scale(width, height, focus_xy, scale)
        return img.crop(box).resize(out_size, Image.LANCZOS)

    # index 0 is the full frame, index n_in - 1 the deepest zoom.
    push_in = [_frame(1.0 + (zoom - 1.0) * ease_in_out(i / (n_in - 1)))
               for i in range(n_in)]

    frames = list(push_in)
    durations = [step_ms] * n_in
    durations[0] = CLIP_WIDE_HOLD_MS
    durations[-1] = max(step_ms, round(max(0.0, hold_seconds) * 1000.0))
    # …and back out the way we came, minus the two endpoints (the deepest frame
    # is already holding, and the full frame is the next loop's first frame).
    frames.extend(reversed(push_in[1:-1]))
    durations.extend([step_ms] * max(0, n_in - 2))
    return (frames, durations)


def write_zoom_clip(frames: list, durations: list[int], out_dir: Path,
                    out_basename: str) -> Path | None:
    """Write ``frames`` as one looping animation —
    ``{out_basename}_zoom.webp``, or ``.png`` (APNG) where this Pillow has no
    WEBP — beside the target's outputs. Returns the path, or ``None`` when there
    is nothing to write. Same encoder the deepening reel uses."""
    from PIL import features

    if len(frames) < 2:
        return None
    out_dir = Path(out_dir)
    if features.check("webp"):
        path = out_dir / f"{out_basename}_zoom.webp"
        frames[0].save(path, format="WEBP", save_all=True,
                       append_images=frames[1:], duration=durations, loop=0,
                       minimize_size=True)
    else:
        path = out_dir / f"{out_basename}_zoom.png"
        frames[0].save(path, format="PNG", save_all=True,
                       append_images=frames[1:], duration=durations, loop=0)
    log.info("Zoom clip saved (%d frames) → %s", len(frames), path.name)
    return path


def build_zoom_clip(preview_png: bytes, out_dir: Path, out_basename: str, *,
                    focus_xy: tuple[float, float] | None = None,
                    zoom: float = CLIP_ZOOM) -> Path | None:
    """Render the looping zoom clip for a finished picture and write it beside the
    outputs. Convenience wrapper over :func:`build_zoom_frames` +
    :func:`write_zoom_clip`; returns the written path, or ``None`` when the
    preview can't be read.

    ``preview_png`` is the run's stored preview PNG, flattened onto black exactly
    as the wallpaper export flattens it, so an uncovered corner reads the same in
    both. ``focus_xy`` is where the object sits in that grid; ``None`` falls back
    to the picture's own brightest concentration, and then to its centre.
    """
    from PIL import Image

    try:
        with Image.open(BytesIO(preview_png)) as src:
            if src.mode in ("RGBA", "LA", "P"):
                rgba = src.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (0, 0, 0))
                flat.paste(rgba, mask=rgba.split()[-1])
                img = flat
            else:
                img = src.convert("RGB")
            if focus_xy is None:
                focus_xy = brightness_centroid(img)
            frames, durations = build_zoom_frames(img, focus_xy, zoom=zoom)
    except Exception as exc:  # noqa: BLE001 — an unreadable preview is "no clip"
        log.warning("zoom clip: could not read the preview: %s", exc)
        return None
    return write_zoom_clip(frames, durations, out_dir, out_basename)
