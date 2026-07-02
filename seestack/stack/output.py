"""
Write final stack outputs.

Three artefacts go into ``<project>/output/``:

  * ``master.fits``    — 32-bit float, channel order R/G/B as a 3-axis cube
                         (NAXIS3=3), with the output WCS in the header.
                         **The scientific output.** Open in PixInsight, Siril,
                         APP, etc. for further processing.
  * ``master.tif``     — 16-bit TIFF. Either *linear* (untouched stack data,
                         like DSS / Siril output — looks dark on its own but
                         is what other astro tools expect) or *autostretched*
                         (mildly stretched for direct viewing).
  * ``master_preview.png`` — autostretched PNG, downsized for easy preview.

A second pair of files (``master_coverage.fits`` and ``..._coverage.png``)
records the per-pixel coverage map — useful to spot footprint mismatches in
mosaic stacks.

If a previous stack lives at the same paths, the writer renames it with a
timestamp suffix rather than overwriting; people get attached to their stacks
and accidental clobbers are bad.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

OUTPUT_DIRNAME = "output"

_UNSAFE_BASENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_basename(name: str) -> str:
    """Constrain an output basename to safe filename characters.

    ``out_basename`` can originate from a web API request (stack/editor
    "output name" fields), so it must never be able to place path separators
    or ``..`` into the joined path and write outside ``<project>/output/``.
    """
    cleaned = _UNSAFE_BASENAME_CHARS.sub("_", name.strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:128] or "master"


# Public alias — used by the webapp (pipeline) and its tests.
def safe_basename(name: str) -> str:
    """Sanitize a user-supplied output name to a single safe filename stem
    (see :func:`_sanitize_basename`)."""
    return _sanitize_basename(name)


def write_stack_outputs(
    project_dir: Path,
    rgb: np.ndarray,
    coverage: np.ndarray,
    *,
    wcs_text: str | None,
    out_basename: str = "master",
    tiff_mode: str = "linear",
    header_meta: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """
    Write the FITS + TIFF + preview PNG. Returns a dict of ``{kind: path}``.

    Parameters
    ----------
    header_meta
        Optional extra FITS header cards to record in ``master.fits`` — stack
        provenance such as target name, number of frames, integration time and
        stacking method. Keys are treated as FITS keyword names (see
        :func:`_merge_header_meta`); values may be ``(value, comment)`` tuples.
        Purely additive: downstream tools that don't read these keys are
        unaffected, and omitting the argument reproduces the old output exactly.
    tiff_mode
        ``"linear"`` (default) writes a 16-bit TIFF with no stretching, scaled
        to fill 16-bit range based on the data's robust min/max. This matches
        what DSS / Siril / PixInsight expect — the file looks dark but the
        full data is preserved without amplifying noise.

        ``"autostretch"`` applies a conservative STF stretch (sky → ~6% grey)
        for direct viewing.
    """
    out_basename = _sanitize_basename(out_basename)
    out_dir = Path(project_dir) / OUTPUT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)

    fits_path = out_dir / f"{out_basename}.fits"
    tiff_path = out_dir / f"{out_basename}.tif"
    preview_path = out_dir / f"{out_basename}_preview.png"
    cov_fits_path = out_dir / f"{out_basename}_coverage.fits"

    _archive_if_exists([fits_path, tiff_path, preview_path, cov_fits_path])

    _write_fits(fits_path, rgb, wcs_text, header_meta)
    _write_coverage_fits(cov_fits_path, coverage)
    _write_tiff(tiff_path, rgb, mode=tiff_mode)
    # Preview PNG always uses autostretch — it's there for the "did the stack
    # come out OK?" glance. Always-stretched answers that question.
    _write_preview_png(preview_path, rgb)

    log.info("Stack outputs written to %s (TIFF mode: %s)", out_dir, tiff_mode)
    return {
        "fits": fits_path,
        "tiff": tiff_path,
        "preview": preview_path,
        "coverage": cov_fits_path,
    }


# ---- FITS ----------------------------------------------------------------

def _write_fits(
    path: Path,
    rgb: np.ndarray,
    wcs_text: str | None,
    header_meta: dict[str, Any] | None = None,
) -> None:
    """Write a 3-channel float32 FITS cube with WCS header."""
    from astropy.io import fits

    # FITS convention: data shape is (NAXIS3, NAXIS2, NAXIS1) = (channels, H, W).
    cube = np.transpose(rgb, (2, 0, 1)).astype(np.float32, copy=False)
    hdu = fits.PrimaryHDU(data=cube)
    h = hdu.header
    h["CREATOR"] = ("Seestack", "see PLAN.md")
    h["DATE"] = (datetime.now(timezone.utc).isoformat(), "UTC")
    h["NAXIS3"] = (3, "R, G, B")
    h["BUNIT"] = ("ADU", "linear units (uncalibrated)")
    if header_meta:
        _merge_header_meta(h, header_meta)
    if wcs_text:
        # Merge the reference WCS in. We strip NAXIS keys so they don't clash
        # with the cube's own.
        try:
            ref = fits.Header.fromstring(wcs_text)
            for k in list(ref):
                if k.startswith("NAXIS") or k in {"SIMPLE", "BITPIX", "EXTEND", ""}:
                    continue
                h[k] = (ref[k], ref.comments[k])
        except Exception:  # noqa: BLE001
            log.warning("Could not merge WCS into output FITS")
    hdu.writeto(path, overwrite=True)


def _merge_header_meta(header, meta: dict[str, Any]) -> None:  # noqa: ANN001
    """Merge caller-supplied provenance cards into a FITS header, defensively.

    FITS keywords are 8-char uppercase (A–Z, 0–9, ``-``, ``_``); values must be
    str/int/float/bool. We skip ``None`` values and any key/value that can't be
    coerced into a valid card, so a stray field never aborts writing the stack.
    Values may be a bare scalar or a ``(value, comment)`` tuple.
    """
    for raw_key, raw_val in meta.items():
        key = re.sub(r"[^A-Z0-9_-]", "", str(raw_key).upper())[:8]
        if not key:
            continue
        # HISTORY is a FITS commentary card: it may repeat, so a list of lines is
        # appended one card each (the canonical way to record processing steps)
        # rather than assigned like a normal keyword.
        if key == "HISTORY":
            lines = raw_val if isinstance(raw_val, (list, tuple)) else [raw_val]
            for line in lines:
                if line is None:
                    continue
                header.add_history(str(line)[:72])
            continue
        comment = ""
        val = raw_val
        if isinstance(raw_val, tuple) and len(raw_val) == 2:
            val, comment = raw_val
        if val is None:
            continue
        if isinstance(val, bool):
            pass  # bool is a valid FITS logical
        elif isinstance(val, (int, float, str)):
            pass
        else:
            val = str(val)
        if isinstance(val, str):
            val = val[:68]  # keep the card within the 80-column limit
        try:
            header[key] = (val, comment) if comment else val
        except (ValueError, TypeError):  # unrepresentable value — drop the card
            log.debug("skipping non-FITS-safe header meta %r=%r", key, raw_val)


def _write_coverage_fits(path: Path, coverage: np.ndarray) -> None:
    """Write the per-pixel coverage map (averaged across channels)."""
    from astropy.io import fits

    cov_2d = coverage.mean(axis=-1).astype(np.float32) if coverage.ndim == 3 else coverage
    hdu = fits.PrimaryHDU(data=cov_2d)
    hdu.header["CREATOR"] = "Seestack"
    hdu.header["BUNIT"] = "frames"
    hdu.writeto(path, overwrite=True)


# ---- TIFF + preview ------------------------------------------------------

def _write_tiff(path: Path, rgb: np.ndarray, *, mode: str = "linear") -> None:
    """16-bit RGB TIFF in either linear or autostretched form."""
    import tifffile

    if mode == "linear":
        u16 = _to_uint16_linear(rgb)
    elif mode == "autostretch":
        stretched = _autostretch_for_export(rgb)
        u16 = (np.clip(stretched, 0.0, 1.0) * 65535.0).astype(np.uint16)
    else:
        raise ValueError(f"unknown tiff mode: {mode!r}")
    tifffile.imwrite(path, u16, photometric="rgb", compression="zlib")


def _write_preview_png(path: Path, rgb: np.ndarray, *, max_width: int = 1024) -> None:
    """Downsized 8-bit PNG preview — always autostretched (it's the 'preview')."""
    from PIL import Image

    stretched = _autostretch_for_export(rgb)
    h, w = stretched.shape[:2]
    u8 = (np.clip(stretched, 0.0, 1.0) * 255).astype(np.uint8)
    if w > max_width:
        new_w = max_width
        new_h = int(round(h * (new_w / w)))
        img = Image.fromarray(u8, mode="RGB").resize((new_w, new_h), Image.BOX)
    else:
        img = Image.fromarray(u8, mode="RGB")
    img.save(path, format="PNG")


def write_full_res_png(path: Path, rgb: np.ndarray) -> Path:
    """Write a native-resolution 8-bit RGB PNG of an already display-stretched
    image (values in 0..1). Unlike ``_write_preview_png`` this does NOT autostretch
    or downsize — it's for downloading the editor result exactly as shown. NaN
    (uncovered) pixels render black."""
    from PIL import Image

    arr = np.nan_to_num(np.asarray(rgb, dtype=np.float32), nan=0.0)
    u8 = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
    if u8.ndim == 2:
        u8 = np.stack([u8, u8, u8], axis=-1)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(u8, mode="RGB").save(path, format="PNG")
    return Path(path)


def _to_uint16_linear(rgb: np.ndarray) -> np.ndarray:
    """
    Pack float32 stack data into 16-bit unsigned without stretching.

    We map the data's robust 0.5%–99.9% percentile range to 0–65535. This
    preserves the linear shape of the histogram (no curve applied), like
    DSS / Siril 16-bit TIFFs.

    Percentiles are computed over the **covered** pixels only. For a mosaic,
    the union canvas has large NaN (no-data) regions; if those were counted
    as zeros they'd drag the low percentile down and crush the real data into
    a sliver of the 16-bit range. Uncovered pixels are written as 0 (black).
    """
    arr = rgb.astype(np.float32, copy=False)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros(arr.shape, dtype=np.uint16)
    covered = arr[finite]
    lo = float(np.percentile(covered, 0.5))
    hi = float(np.percentile(covered, 99.9))
    if hi <= lo:
        hi = lo + 1.0
    norm = (arr - lo) / (hi - lo)
    norm = np.where(finite, np.clip(norm, 0.0, 1.0), 0.0)
    return (norm * 65535.0).astype(np.uint16)


def _autostretch_for_export(rgb: np.ndarray) -> np.ndarray:
    """
    Conservative export stretch — much milder than the GUI preview thumbnail.

    The thumbnail uses ``target_bg=0.20`` because it has to be visible at a
    glance in a small panel. For a full-resolution saved file we want sky at
    ~6% grey, with deeper shadows clipped (sigma_factor=-2.8) so noise
    doesn't dominate the histogram.

    NaN (uncovered mosaic canvas) is passed straight through — ``autostretch``
    is nan-aware and computes its per-channel statistics over covered pixels
    only, so a mosaic's no-data gaps can't corrupt the black point or skew
    the colour balance.
    """
    from seestack.render.thumbnail import autostretch

    return autostretch(
        rgb.astype(np.float32, copy=False), target_bg=0.06, sigma_factor=-2.8,
    )


# ---- file management -----------------------------------------------------

def _archive_if_exists(paths: list[Path]) -> None:
    """Rename existing outputs with a timestamp suffix instead of overwriting."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for p in paths:
        if not p.exists():
            continue
        archived = p.with_name(f"{p.stem}_{stamp}{p.suffix}")
        try:
            p.rename(archived)
            log.info("archived previous %s → %s", p.name, archived.name)
        except OSError as exc:
            log.warning("could not archive %s: %s", p, exc)
