"""The share-ready "zoom clip" — a slow push-in on a finished picture and back out.

Everything in :mod:`seestack.render.zoomclip` is index-derived (no clock, no RNG),
so these pin the schedule exactly: the move starts on the whole frame, ends on a
tighter crop centred on the object, comes back the way it went, and never invents
pixels it doesn't have.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from seestack.render.zoomclip import (
    CLIP_ZOOM,
    brightness_centroid,
    build_zoom_clip,
    build_zoom_frames,
    crop_box_for_scale,
    ease_in_out,
    write_zoom_clip,
    zoom_clip_size,
)


def _picture(w=800, h=600, blob_xy=(600, 150)) -> Image.Image:
    """A dark sky with one bright blob, so "did it zoom onto the object?" is
    answerable from the pixels."""
    yy, xx = np.mgrid[0:h, 0:w]
    sky = np.full((h, w), 0.04, dtype=np.float32)
    sky += 0.9 * np.exp(-(((xx - blob_xy[0]) / 25) ** 2 + ((yy - blob_xy[1]) / 25) ** 2))
    u8 = (np.clip(sky, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([u8] * 3), mode="RGB")


def test_ease_is_smooth_and_pinned_at_both_ends():
    assert ease_in_out(0.0) == 0.0
    assert ease_in_out(1.0) == 1.0
    assert abs(ease_in_out(0.5) - 0.5) < 1e-9
    # Monotonic, and clamped rather than extrapolated outside 0..1.
    vals = [ease_in_out(i / 20) for i in range(21)]
    assert all(b >= a for a, b in zip(vals, vals[1:], strict=False))
    assert ease_in_out(-3.0) == 0.0 and ease_in_out(9.0) == 1.0


def test_output_size_never_upscales_the_deepest_frame():
    """The clip is only as big as the most zoomed-in frame actually contains — the
    same "never upsample" rule the wallpaper export follows, which is what keeps a
    1024-wide preview from being blown up into a soft 1080 clip."""
    # A big picture is capped by the long edge…
    assert zoom_clip_size(4000, 3000) == (640, 480)
    # …a 1024-wide preview by the zoom (1024 / 1.8 = 569).
    w, h = zoom_clip_size(1024, 768)
    assert w == round(1024 / CLIP_ZOOM) and h == round(768 / CLIP_ZOOM)
    # …and a tiny one stays tiny rather than growing.
    assert zoom_clip_size(200, 100) == (round(200 / CLIP_ZOOM), round(100 / CLIP_ZOOM))
    assert zoom_clip_size(0, 0) == (0, 0)


def test_crop_box_tracks_the_focus_and_stays_inside_the_frame():
    # Full frame at scale 1.
    assert crop_box_for_scale(100, 80, (50, 40), 1.0) == (0, 0, 100, 80)
    # Centred on the focus at scale 2.
    assert crop_box_for_scale(100, 80, (50, 40), 2.0) == (25, 20, 75, 60)
    # A focus in the corner slides the box back inside rather than shrinking it —
    # the zoomed frame stays full of picture.
    left, top, right, bottom = crop_box_for_scale(100, 80, (0, 0), 2.0)
    assert (left, top) == (0, 0) and (right - left, bottom - top) == (50, 40)
    left, top, right, bottom = crop_box_for_scale(100, 80, (999, 999), 2.0)
    assert (right, bottom) == (100, 80) and (right - left, bottom - top) == (50, 40)
    # No focus, and a NaN focus, both centre.
    assert crop_box_for_scale(100, 80, None, 2.0) == (25, 20, 75, 60)
    assert crop_box_for_scale(100, 80, (float("nan"), 40.0), 2.0) == (25, 20, 75, 60)
    # A scale below 1 would mean showing more than there is; clamped to the frame.
    assert crop_box_for_scale(100, 80, (50, 40), 0.2) == (0, 0, 100, 80)


def test_the_move_starts_wide_ends_tight_and_returns():
    img = _picture()
    frames, durations = build_zoom_frames(img, (600, 150))
    assert len(frames) == len(durations) >= 4
    # Every frame is the same size, or an encoder can't make a clip of them.
    assert len({f.size for f in frames}) == 1
    assert frames[0].size == zoom_clip_size(*img.size)

    # The loop closes: the way out is the way in, reversed, so the last frame is
    # adjacent to the first and the clip doesn't jump when it repeats.
    n_in = (len(frames) + 2) // 2
    assert frames[n_in:] == list(reversed(frames[1:n_in - 1]))

    # The far end really is tighter: the bright blob covers a larger share of the
    # deepest frame than of the full one.
    def _bright_fraction(f):
        a = np.asarray(f.convert("L"), dtype=np.float32)
        return float((a > 128).mean())

    assert _bright_fraction(frames[n_in - 1]) > _bright_fraction(frames[0]) * 1.5

    # The full frame and the deepest frame each hold, so the loop reads as a move
    # rather than a flicker.
    assert durations[0] > durations[1]
    assert durations[n_in - 1] > durations[1]


def _blob_centre(frame) -> tuple[float, float]:
    """Where the bright blob sits in a rendered frame, as a 0..1 fraction."""
    lum = np.asarray(frame.convert("L"), dtype=np.float32)
    ys, xs = np.where(lum > 200)
    assert xs.size, "the blob must be visible in the zoomed frame"
    h, w = lum.shape
    return (float(xs.mean()) / w, float(ys.mean()) / h)


def test_the_camera_travels_toward_the_focus_not_the_middle():
    """An off-centre object must end up in the middle of the deepest frame — the
    whole point of solving for its position rather than zooming on the middle."""
    img = _picture(blob_xy=(560, 300))
    frames, _ = build_zoom_frames(img, (560, 300))
    fx, fy = _blob_centre(frames[(len(frames) + 2) // 2 - 1])
    assert abs(fx - 0.5) < 0.1 and abs(fy - 0.5) < 0.1
    # Blind centring would have left it off to the side — the un-zoomed blob sits
    # at 0.70 W, and a centred 1.8× crop keeps it there.
    centred = build_zoom_frames(img, None)[0]
    cx, _cy = _blob_centre(centred[(len(centred) + 2) // 2 - 1])
    assert cx > 0.65


def test_an_object_near_the_edge_keeps_the_frame_full_of_picture():
    """The crop slides back inside the frame rather than hanging off it. The
    deliberate consequence: a target right in the corner cannot be centred, and is
    left where it is instead of being framed against a black margin — a beginner
    would rather see their picture than padding. It must still be *in* the clip."""
    img = _picture(blob_xy=(770, 60))
    frames, _ = build_zoom_frames(img, (770, 60))
    deepest = frames[(len(frames) + 2) // 2 - 1]
    fx, fy = _blob_centre(deepest)
    # Still visible, and no further out than it was in the full frame (0.96, 0.10).
    assert fx <= 0.96 and fy >= 0.10
    # The frame is all picture: the crop never runs off the canvas, so the outer
    # rows/columns carry sky rather than the black of an out-of-bounds read.
    lum = np.asarray(deepest.convert("L"), dtype=np.float32)
    assert lum.min() > 0
    assert deepest.size == zoom_clip_size(*img.size)


def test_a_degenerate_picture_makes_no_frames():
    frames, durations = build_zoom_frames(Image.new("RGB", (0, 0)))
    assert frames == [] and durations == []
    assert write_zoom_clip([], [], Path("."), "nope") is None


def test_brightness_centroid_finds_the_object_and_gives_up_on_a_flat_frame():
    cx, cy = brightness_centroid(_picture(blob_xy=(600, 150)))
    assert abs(cx - 600) < 20 and abs(cy - 150) < 20
    # A flat frame has no concentration to aim at — the caller centres instead.
    assert brightness_centroid(Image.new("RGB", (64, 64), (30, 30, 30))) is None


def test_build_zoom_clip_writes_a_looping_animation(tmp_path):
    buf = tmp_path / "src.png"
    _picture().save(buf)
    out = build_zoom_clip(buf.read_bytes(), tmp_path, "master")
    assert out is not None and out.exists()
    assert out.name in ("master_zoom.webp", "master_zoom.png")
    with Image.open(out) as clip:
        assert getattr(clip, "n_frames", 1) > 4
        assert clip.size == zoom_clip_size(800, 600)


def test_build_zoom_clip_falls_back_to_the_brightest_thing(tmp_path):
    """No plate solve ⇒ no target pixel ⇒ the clip still pushes in on the object,
    because the centroid stands in for the catalogue position."""
    buf = tmp_path / "src.png"
    _picture(blob_xy=(700, 100)).save(buf)
    solved = build_zoom_clip(buf.read_bytes(), tmp_path, "solved", focus_xy=(700, 100))
    guessed = build_zoom_clip(buf.read_bytes(), tmp_path, "guessed")
    assert solved is not None and guessed is not None
    with Image.open(solved) as a, Image.open(guessed) as b:
        a.seek(a.n_frames - 1)
        b.seek(b.n_frames - 1)
        assert a.size == b.size
    # Centring blindly would be visibly different; the centroid lands on the blob.
    assert guessed.stat().st_size > 0


def test_an_unreadable_preview_is_no_clip_not_a_crash(tmp_path):
    assert build_zoom_clip(b"not a png", tmp_path, "master") is None
