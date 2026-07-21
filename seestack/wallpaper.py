"""Crop + size a finished stack preview into a ready-to-set wallpaper.

One of the most delightful things a Seestar beginner does with a good result is
make it their phone lock-screen — but the native Seestar field of view is roughly
square, so it letterboxes badly on a tall phone or a wide desktop. Today the only
path is to open a separate photo editor and hand-crop, which usually leaves the
target off-centre.

This module turns the already-rendered stack preview into a wallpaper cropped to a
chosen aspect (phone / desktop / square), centred on the plate-solved target when
we know where it is, and sized for the device.

Everything here is pure and read-only: it only ever *crops and downscales* the
preview that was already produced, **never upsamples** (so it can't invent detail
that isn't in the stack) and never touches the stored pixels on disk.
"""

from __future__ import annotations

from pathlib import Path

# Aspect presets a beginner actually wants. ``aspect_w``/``aspect_h`` set the crop
# shape; ``max_w``/``max_h`` cap the output size (a sane device resolution). We
# never upsample past the crop's own pixels, so a small preview simply yields a
# smaller — but correctly-shaped — wallpaper.
WALLPAPER_PRESETS: dict[str, dict] = {
    "phone": {"aspect_w": 1170, "aspect_h": 2532, "max_w": 1170, "max_h": 2532,
              "label": "Phone"},
    "desktop": {"aspect_w": 1920, "aspect_h": 1080, "max_w": 1920, "max_h": 1080,
                "label": "Desktop"},
    "square": {"aspect_w": 1440, "aspect_h": 1440, "max_w": 1440, "max_h": 1440,
               "label": "Square"},
}


def wallpaper_crop_box(
    img_w: int, img_h: int, aspect_w: int, aspect_h: int,
    target_px: tuple[float, float] | None = None,
) -> tuple[int, int, int, int]:
    """The largest ``aspect_w:aspect_h`` rectangle that fits inside an
    ``img_w × img_h`` image, centred on ``target_px`` (the target's pixel) and
    clamped so it never runs past the image edge.

    Returns a half-open ``(x0, y0, x1, y1)`` box (PIL-crop convention). Falls back
    to the image centre when ``target_px`` is ``None`` or non-finite. Degenerate
    inputs (a zero-size image or aspect) yield the whole image so a caller never
    crashes on a broken preview.
    """
    if img_w <= 0 or img_h <= 0 or aspect_w <= 0 or aspect_h <= 0:
        return (0, 0, max(img_w, 0), max(img_h, 0))

    target_ratio = aspect_w / aspect_h            # width / height of the crop
    img_ratio = img_w / img_h
    if img_ratio > target_ratio:
        # Image is wider than the target shape → the crop is limited by height.
        crop_h = img_h
        crop_w = round(img_h * target_ratio)
    else:
        # Image is taller/narrower → limited by width.
        crop_w = img_w
        crop_h = round(img_w / target_ratio)
    crop_w = max(1, min(crop_w, img_w))
    crop_h = max(1, min(crop_h, img_h))

    cx: float
    cy: float
    if target_px is not None and _finite(target_px[0]) and _finite(target_px[1]):
        cx, cy = float(target_px[0]), float(target_px[1])
    else:
        cx, cy = img_w / 2.0, img_h / 2.0

    x0 = round(cx - crop_w / 2.0)
    y0 = round(cy - crop_h / 2.0)
    # Slide the box fully inside the image (keep its size; only move it).
    x0 = max(0, min(x0, img_w - crop_w))
    y0 = max(0, min(y0, img_h - crop_h))
    return (x0, y0, x0 + crop_w, y0 + crop_h)


def wallpaper_target_pixel(
    fits_path: str | Path, ra_deg: float | None, dec_deg: float | None,
    preview_w: int, preview_h: int,
) -> tuple[float, float] | None:
    """Where the target sits in the **preview PNG's** pixel grid, from the stack's
    stored celestial WCS and the target's RA/Dec.

    The master FITS carries the true canvas WCS; we map the target's sky position
    to a full-res pixel and rescale it to the downscaled preview (area-resampling
    convention, matching :func:`seestack.io.wcs_io.wcs_dict_rescaled_to_preview`).
    Returns ``None`` — so the caller centres on the image instead — when there's no
    WCS, no target position, or the mapping fails.
    """
    if ra_deg is None or dec_deg is None or preview_w <= 0 or preview_h <= 0:
        return None
    from seestack.io.wcs_io import celestial_wcs_from_fits

    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    if wcs is None or full_w <= 0 or full_h <= 0:
        return None
    try:
        px, py = wcs.world_to_pixel_values(float(ra_deg), float(dec_deg))
        px = float(px)
        py = float(py)
    except Exception:  # noqa: BLE001 — a malformed WCS just means "no target pixel"
        return None
    if not (_finite(px) and _finite(py)):
        return None
    # 0-based full-res pixel centre → 0-based preview pixel centre for a uniform
    # downscale: (p_full + 0.5)/s = p_prev + 0.5.
    s_x = full_w / preview_w
    s_y = full_h / preview_h
    tx = (px + 0.5) / s_x - 0.5
    ty = (py + 0.5) / s_y - 0.5
    return (tx, ty)


def png_size(png_bytes: bytes) -> tuple[int, int] | None:
    """``(width, height)`` of an encoded PNG (or any PIL-readable image), or
    ``None`` if it can't be read."""
    from io import BytesIO

    from PIL import Image

    try:
        with Image.open(BytesIO(png_bytes)) as img:
            return (int(img.width), int(img.height))
    except Exception:  # noqa: BLE001 — a corrupt preview just means "unknown size"
        return None


def render_wallpaper_jpeg(
    preview_png: bytes, preset: dict, target_px: tuple[float, float] | None = None,
    *, quality: int = 90,
) -> bytes:
    """Crop the finished preview PNG to ``preset``'s aspect (centred on
    ``target_px``), downscale it to fit ``preset``'s ``max_w × max_h`` without ever
    upsampling, and return share-friendly JPEG bytes.

    JPEG has no alpha, so any transparency flattens onto black — matching the
    preview's own "uncovered = black" convention (as :func:`png_bytes_to_jpeg`).
    """
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(preview_png)) as src:
        if src.mode in ("RGBA", "LA", "P"):
            rgba = src.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (0, 0, 0))
            flat.paste(rgba, mask=rgba.split()[-1])
            img = flat
        else:
            img = src.convert("RGB")

        w, h = img.size
        box = wallpaper_crop_box(w, h, int(preset["aspect_w"]),
                                 int(preset["aspect_h"]), target_px)
        cropped = img.crop(box)
        cw, ch = cropped.size

        # Downscale to the device size, preserving the crop's exact aspect and
        # never upsampling (a preview smaller than the device stays native-size).
        max_w = int(preset["max_w"])
        max_h = int(preset["max_h"])
        scale = min(1.0, max_w / cw, max_h / ch)
        if scale < 1.0:
            cropped = cropped.resize((max(1, round(cw * scale)),
                                      max(1, round(ch * scale))), Image.LANCZOS)

        buf = BytesIO()
        cropped.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _finite(v: float) -> bool:
    return v == v and v not in (float("inf"), float("-inf"))
