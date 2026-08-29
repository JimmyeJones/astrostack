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

#: FITS header keyword marking a written image as tone-mapped **display space**
#: (roughly ``[0, 1]``, non-linear) rather than the usual linear ADU stack. An
#: editor export is the recipe's already-stretched result, so it is *not* linear
#: — stamping this lets both our renderers and external tools (Siril/PixInsight)
#: know not to stretch it again. Absent = the historical assumption (linear).
DISPLAY_SPACE_CARD = "SSDISPLY"

_UNSAFE_BASENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def fits_is_display_space(fits_path: str | Path) -> bool:
    """True when a stack FITS is marked tone-mapped display-space (an editor
    export), so renderers skip the default stretch that would double-process it.

    Reads only the header (cheap) and treats any read error / missing card as
    "not display space" — so old files and non-editor stacks keep the historical
    linear behaviour. See :data:`DISPLAY_SPACE_CARD`."""
    try:
        from astropy.io import fits

        return bool(fits.getheader(fits_path).get(DISPLAY_SPACE_CARD, False))
    except Exception:  # noqa: BLE001 — a bad/missing header just means "not marked"
        return False


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
    already_display: bool = False,
    frame_coverage: np.ndarray | None = None,
    rejection_map: np.ndarray | None = None,
) -> dict[str, Path]:
    """
    Write the FITS + TIFF + preview PNG. Returns a dict of ``{kind: path}``.

    Parameters
    ----------
    frame_coverage
        The honest per-pixel **frame count**, when the stack path can supply it
        (the weighted-sum and drizzle accumulators both do). Written as a
        sibling ``{base}_framecov.fits`` so the editor's sky-leveling pass can
        bin panels by how many subs actually cover them rather than by a sum of
        weights — see :func:`_write_frame_coverage_fits`. Omitted (or ``None``)
        writes no sibling at all, which is exactly what every run recorded
        before this existed looks like, and every consumer falls back to the
        weighted ``coverage`` as it always has.
    rejection_map
        The per-pixel **count of samples outlier rejection dropped**, when the
        run was asked to record one (``StackOptions.record_rejection_map``, off
        by default). Written as a sibling ``{base}_rejected.fits`` so the app can
        show the user *where* the satellites and cosmic rays it cleaned out
        actually were, instead of only a percentage. ``None`` — which is every
        run that didn't ask, and every run recorded before this existed — writes
        no sibling at all, and every consumer reads that as "no overlay
        available".
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
    framecov_fits_path = out_dir / f"{out_basename}_framecov.fits"
    rejected_fits_path = out_dir / f"{out_basename}_rejected.fits"

    archived = _archive_existing_outputs(out_dir, out_basename)

    _write_fits(fits_path, rgb, wcs_text, header_meta, already_display=already_display)
    _write_coverage_fits(cov_fits_path, coverage)
    # Only worth a second canvas-sized file when it actually says something
    # different: on an unweighted stack the coverage map *is* the frame count,
    # and a consumer that finds no sibling correctly falls back to it. This
    # keeps the ordinary output set exactly the size it has always been.
    wrote_framecov = (
        frame_coverage is not None
        and not _same_map(coverage, frame_coverage))
    if wrote_framecov:
        _write_frame_coverage_fits(framecov_fits_path, frame_coverage)
    # Only written when the run was asked to record it *and* rejection actually
    # dropped something. An all-zero map is a real answer ("nothing was removed")
    # but it's a canvas-sized file saying nothing, and a consumer that finds no
    # sibling already renders exactly that answer — so the disk stays quiet.
    wrote_rejected = rejection_map is not None and bool(np.any(rejection_map))
    if wrote_rejected:
        _write_rejection_map_fits(rejected_fits_path, rejection_map)
    _write_tiff(tiff_path, rgb, mode=tiff_mode, already_display=already_display)
    # Preview PNG normally autostretches a linear stack. For an editor export the
    # data is already in display space (the recipe applied a stretch), so writing
    # it as-is makes the History/Gallery thumbnail match what the editor showed.
    _write_preview_png(preview_path, rgb, already_display=already_display)

    log.info("Stack outputs written to %s (TIFF mode: %s)", out_dir, tiff_mode)
    return {
        "fits": fits_path,
        "tiff": tiff_path,
        "preview": preview_path,
        "coverage": cov_fits_path,
        **({"frame_coverage": framecov_fits_path} if wrote_framecov else {}),
        **({"rejection_map": rejected_fits_path} if wrote_rejected else {}),
        # {original_path: archived_path} for outputs that already existed and were
        # moved aside. The caller uses this to repoint the *previous* run's history
        # row at its archived files, so a re-stack keeps ``master`` as the newest
        # image without silently making the old run's row serve the new pixels.
        "archived": archived,
    }


# ---- FITS ----------------------------------------------------------------

def _write_fits(
    path: Path,
    rgb: np.ndarray,
    wcs_text: str | None,
    header_meta: dict[str, Any] | None = None,
    *,
    already_display: bool = False,
) -> None:
    """Write a 3-channel float32 FITS cube with WCS header.

    ``already_display`` (editor exports): the cube is the recipe's already
    tone-mapped ``[0, 1]`` result, not a linear stack, so we stamp
    :data:`DISPLAY_SPACE_CARD` and an honest ``BUNIT`` instead of claiming
    ``ADU (linear)`` — otherwise re-opening the file (here or in Siril/
    PixInsight) would stretch an already-stretched picture again."""
    from astropy.io import fits

    # FITS convention: data shape is (NAXIS3, NAXIS2, NAXIS1) = (channels, H, W).
    cube = np.transpose(rgb, (2, 0, 1)).astype(np.float32, copy=False)
    hdu = fits.PrimaryHDU(data=cube)
    h = hdu.header
    h["CREATOR"] = ("Seestack", "see PLAN.md")
    h["DATE"] = (datetime.now(timezone.utc).isoformat(), "UTC")
    h["NAXIS3"] = (3, "R, G, B")
    if already_display:
        h["BUNIT"] = ("display", "tone-mapped display-space [0,1] (non-linear)")
        h[DISPLAY_SPACE_CARD] = (True, "tone-mapped display-space image, not linear")
    else:
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
    """Write the per-pixel coverage map (averaged across channels).

    The map is the accumulator's ``coverage`` — the **Σ of per-frame weights**,
    not a frame count. Those are the same number only for an unweighted stack
    whose frames are all-or-nothing per pixel; with quality weighting on (or on
    the drizzle path, where a frame contributes fractional footprint overlap at
    any ``pixfrac < 1`` / ``scale ≠ 1``) a pixel's value is a weight sum that
    happens to sit near the frame count. The header used to call it "frames"
    outright, which is a claim the numbers don't support — so it now says what
    they are, with the equivalence spelled out in the comment for anyone who
    opens the file. **Only the label changed**: the array is byte-for-byte what
    it always was, because the sky-leveling pass and the editor's
    ``EditContext.coverage`` both read these pixels and binning them differently
    would change every existing run's picture. The honest unweighted count is
    the stacker's separate ``frame_coverage``, which is what the
    ``coverage_min``/``coverage_max`` diagnostics already report.
    """
    from astropy.io import fits

    cov_2d = coverage.mean(axis=-1).astype(np.float32) if coverage.ndim == 3 else coverage
    hdu = fits.PrimaryHDU(data=cov_2d)
    hdu.header["CREATOR"] = "Seestack"
    # The comment has to fit the 80-column card beside the value, or astropy
    # truncates it mid-word — so it is kept short deliberately.
    hdu.header["BUNIT"] = ("weight", "sum of frame weights (=frames unweighted)")
    hdu.writeto(path, overwrite=True)


def _collapse_2d(cov: np.ndarray) -> np.ndarray:
    """A coverage-style map as 2-D float32 (channel-mean for a per-channel one)."""
    flat = cov.mean(axis=-1) if cov.ndim == 3 else cov
    return np.asarray(flat, dtype=np.float32)


def _same_map(coverage: np.ndarray, frame_coverage: np.ndarray) -> bool:
    """Do these two maps carry identical numbers once collapsed to 2-D?

    True on every unweighted stack, where Σ-of-weights *is* the frame count —
    the case where writing the frame-count sibling would only duplicate a
    canvas-sized file for nothing.
    """
    a, b = _collapse_2d(coverage), _collapse_2d(frame_coverage)
    return a.shape == b.shape and bool(np.array_equal(a, b))


def _write_rejection_map_fits(path: Path, rejection_map: np.ndarray) -> None:
    """Write the per-pixel **rejected-sample count** beside the picture.

    This is the spatial half of the ``REJFRAC`` trust line. The header already
    says *"sigma clipping dropped 0.3% of samples"*; this file says **where** —
    so the app can lay the satellite trains, plane trails and cosmic rays it
    quietly removed over the finished picture, and the user can see that leaving
    the frames in and trusting the stack was the right call.

    Purely observational: it records the same keep/drop decision the combine
    already applied, so a run that writes it produces pixel-identical output to
    one that doesn't. Stored as ``uint16`` — the count is bounded by the number
    of samples that landed on the pixel, and both recording paths saturate
    rather than wrap — which keeps the file a sixth the size of a float32
    canvas.
    """
    from astropy.io import fits

    hdu = fits.PrimaryHDU(data=np.asarray(rejection_map, dtype=np.uint16))
    hdu.header["CREATOR"] = "Seestack"
    # Kept short so astropy doesn't truncate the comment mid-word on the card.
    hdu.header["BUNIT"] = ("count", "samples dropped by outlier rejection")
    hdu.writeto(path, overwrite=True)


def _write_frame_coverage_fits(path: Path, frame_coverage: np.ndarray) -> None:
    """Write the honest per-pixel **frame count** beside the weighted map.

    The sky-leveling pass bins a mosaic's canvas by coverage level — one bin per
    panel / overlap region — and pushes each bin's sky to zero. Which bin a pixel
    lands in must therefore follow the *panel geometry*, and nothing else.

    Binning the weighted map instead does not: with quality weighting on (which
    the walk-away chain enables by itself on every unattended stack), a pixel's
    value is Σ of per-frame weights, so a four-sub panel reads anywhere from ~2.5
    to 4 depending on how good those four subs happened to be. Rounded to
    integers, one real region **splits into several bins along weight boundaries
    that have nothing to do with the sky** — measured on a synthetic two-region
    mosaic, a 4-sub panel and its 8-sub overlap binned as *four* levels
    (3, 4, 6, 7) — and each half then gets its own sky pushed to zero
    independently. That is a step-generating mechanism inside a panel, in the
    very pass whose job is to remove steps.

    ``level_by_coverage`` and ``measure_seam_residual`` have always accepted a
    ``frame_coverage`` argument for exactly this reason, and the in-stack call
    passes it; only the *editor*, which reloads the maps from disk, could not —
    because this file didn't exist. It does now.

    Deliberately a **new sibling** rather than a change to
    ``{base}_coverage.fits``: those pixels are what every already-recorded run's
    picture was leveled against, and rewriting their meaning would change
    existing images. A run without this file falls back to the weighted map
    exactly as before.
    """
    from astropy.io import fits

    cov = frame_coverage
    cov_2d = cov.mean(axis=-1).astype(np.float32) if cov.ndim == 3 else cov
    hdu = fits.PrimaryHDU(data=np.asarray(cov_2d, dtype=np.float32))
    hdu.header["CREATOR"] = "Seestack"
    hdu.header["BUNIT"] = ("frames", "subs covering this pixel (unweighted)")
    hdu.writeto(path, overwrite=True)


# ---- TIFF + preview ------------------------------------------------------

def _write_tiff(path: Path, rgb: np.ndarray, *, mode: str = "linear",
                already_display: bool = False) -> None:
    """16-bit RGB TIFF in either linear or autostretched form.

    ``already_display`` (editor exports): the data is already the display-space
    [0,1] image, so write it verbatim — neither a linear rescale nor another
    stretch applies (both would misrepresent what the editor showed)."""
    import tifffile

    if already_display:
        u16 = (np.clip(np.nan_to_num(rgb, nan=0.0), 0.0, 1.0) * 65535.0).astype(np.uint16)
    elif mode == "linear":
        u16 = _to_uint16_linear(rgb)
    elif mode == "autostretch":
        stretched = _autostretch_for_export(rgb)
        u16 = (np.clip(stretched, 0.0, 1.0) * 65535.0).astype(np.uint16)
    else:
        raise ValueError(f"unknown tiff mode: {mode!r}")
    tifffile.imwrite(path, u16, photometric="rgb", compression="zlib")


def _write_preview_png(path: Path, rgb: np.ndarray, *, max_width: int = 1024,
                       already_display: bool = False) -> None:
    """Downsized 8-bit PNG preview. Autostretched for a linear stack; written
    as-is when the data is already display-space (an editor export)."""
    from PIL import Image

    stretched = np.nan_to_num(rgb, nan=0.0) if already_display else _autostretch_for_export(rgb)
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


def write_share_jpeg(path: Path, rgb: np.ndarray, *, max_long_edge: int = 2048,
                     quality: int = 90, nameplate: "Any | None" = None) -> Path:
    """Write a social-ready JPEG of an already display-stretched image (values in
    0..1, NaN = uncovered → black), downscaled so its long edge is at most
    ``max_long_edge`` px. A native PNG of a 100+ MP mosaic is far too big to post;
    a ~2048 px JPEG is what image-sharing sites actually want. The image content
    is exactly the edited result as shown — only the size and container differ.

    When ``nameplate`` is a :class:`seestack.nameplate.NameplateFields`, a
    tasteful acquisition footer (target · integration · date · gear) is baked
    onto the *downscaled* image so the caption is crisp at the output resolution.
    Passing ``None`` (the default) leaves the pixels exactly as before."""
    from PIL import Image

    arr = np.nan_to_num(np.asarray(rgb, dtype=np.float32), nan=0.0)
    u8 = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
    if u8.ndim == 2:
        u8 = np.stack([u8, u8, u8], axis=-1)
    img = Image.fromarray(u8, mode="RGB")
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > max_long_edge:
        scale = max_long_edge / float(long_edge)
        # LANCZOS gives the cleanest downscale for a finished picture (BOX, used for
        # the tiny preview thumbnail, would soften star cores at this size).
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                         Image.LANCZOS)
    if nameplate is not None:
        from seestack.nameplate import draw_nameplate
        img = draw_nameplate(img, nameplate)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="JPEG", quality=quality, optimize=True)
    return Path(path)


def png_bytes_to_jpeg(png_data: bytes, *, quality: int = 90,
                      nameplate: Any | None = None,
                      keepsake: Any | None = None,
                      sky_marks: Any | None = None) -> bytes:
    """Transcode an already-rendered display PNG (e.g. the stored stack preview)
    to a smaller, more share-friendly JPEG at the **same** resolution.

    JPEG has no alpha channel, so any transparency is flattened onto black —
    which matches the preview's own convention (uncovered/NaN pixels are already
    black). Used to offer a JPEG download of the finished picture alongside the
    PNG without re-rendering from the linear FITS: a PNG of a large stack is
    heavy and PNG isn't ideal for messaging apps, while a quality-90 JPEG is
    smaller and universally share-friendly. Returns the encoded JPEG bytes.

    When ``nameplate`` is a :class:`seestack.nameplate.NameplateFields`, the same
    tasteful acquisition footer the editor share export bakes on (target ·
    integration · date · gear) is drawn onto this download too — so the direct
    "Download JPEG" path can be as post-ready as the editor's. Passing ``None``
    (the default) leaves the pixels exactly as before.

    ``keepsake`` takes the same fields and produces the *framed* variant instead:
    the picture matted on a dark card with its name and acquisition data set
    **beneath** it (:func:`seestack.keepsake.draw_keepsake`), for printing or
    posting. The two are alternatives, not layers — a keepsake already carries
    the caption, so it wins if both are passed rather than captioning twice.

    ``sky_marks`` is a :class:`seestack.skymarks.SkyMarks` and *does* layer: the
    scale bar and North/East rose are drawn onto the picture **first**, so a
    keepsake mats an already-marked picture and a nameplate's footer sits below
    marks that live along the top edge. A ``SkyMarks`` with nothing to draw is a
    clean no-op, so a run with no usable WCS is byte-for-byte the plain
    download."""
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(png_data)) as src:
        if src.mode in ("RGBA", "LA", "P"):
            rgba = src.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (0, 0, 0))
            flat.paste(rgba, mask=rgba.split()[-1])
            img = flat
        else:
            img = src.convert("RGB")
        if sky_marks is not None:
            from seestack.skymarks import draw_sky_marks
            img = draw_sky_marks(img, sky_marks)
        if keepsake is not None:
            from seestack.keepsake import draw_keepsake
            img = draw_keepsake(img, keepsake)
        elif nameplate is not None:
            from seestack.nameplate import draw_nameplate
            img = draw_nameplate(img, nameplate)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


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


#: The display-space sky-background grey the saved preview/export lands the stack's
#: sky median at (~6% grey). This is the look a beginner sees on the History and
#: Gallery thumbnails, so the History "Adjust" asinh suggestion anchors to the same
#: target (see ``webapp/routers/stack.py``) — keeping the two named as one constant
#: stops the suggestion drifting brighter/darker than the thumbnail it claims to match.
EXPORT_AUTOSTRETCH_TARGET_BG = 0.06


def _autostretch_for_export(rgb: np.ndarray) -> np.ndarray:
    """
    Conservative export stretch — much milder than the GUI preview thumbnail.

    The thumbnail uses ``target_bg=0.20`` because it has to be visible at a
    glance in a small panel. For a full-resolution saved file we want sky at
    ~6% grey (:data:`EXPORT_AUTOSTRETCH_TARGET_BG`), with deeper shadows clipped
    (sigma_factor=-2.8) so noise doesn't dominate the histogram.

    NaN (uncovered mosaic canvas) is passed straight through — ``autostretch``
    is nan-aware and computes its per-channel statistics over covered pixels
    only, so a mosaic's no-data gaps can't corrupt the black point or skew
    the colour balance.
    """
    from seestack.render.thumbnail import autostretch

    return autostretch(
        rgb.astype(np.float32, copy=False),
        target_bg=EXPORT_AUTOSTRETCH_TARGET_BG, sigma_factor=-2.8,
    )


# ---- file management -----------------------------------------------------

#: Every file a finished stack writes into ``output/``, as the suffix appended to
#: the run's *basename*. Only the first three are recorded as columns on the
#: ``stack_runs`` row; the coverage map and the "watch it appear" reel (webp, or
#: an APNG fallback) are resolved from the basename instead. Both operations that
#: act on a run's whole file set — archiving it aside on a re-stack, and deleting
#: it — need the same list, so it lives here once rather than being retyped.
RUN_ARTEFACT_SUFFIXES: dict[str, str] = {
    "fits": ".fits",
    "tiff": ".tif",
    "preview": "_preview.png",
    "coverage": "_coverage.fits",
    "frame_coverage": "_framecov.fits",
    "rejection_map": "_rejected.fits",
    "progress_webp": "_progress.webp",
    "progress_apng": "_progress.png",
}

# The artefacts that have a dedicated ``stack_runs`` column, i.e. the only ones a
# repoint can actually move. Stated as an allow-list rather than a list of
# exclusions so a *new* entry in ``RUN_ARTEFACT_SUFFIXES`` defaults to "not in the
# map": every artefact added since the exclusions were written (the frame-coverage
# sibling ``_framecov.fits``) resolves from the FITS basename like coverage does,
# and an exclusion list silently let it into the map instead.
_REPOINTABLE_ARTEFACTS = frozenset({"fits", "tiff", "preview"})


def _archive_existing_outputs(out_dir: Path, out_basename: str) -> dict[str, str]:
    """Move an existing output set aside under a single timestamped *basename*.

    Rather than overwriting (people get attached to their stacks), a previous
    ``{base}.fits`` / ``.tif`` / ``_preview.png`` / ``_coverage.fits`` set is
    renamed to ``{base}_{stamp}.*``. Critically, all four move to the **same**
    new basename so the coverage/preview siblings stay siblings of the archived
    FITS (``coverage_path_for`` derives ``{stem}_coverage.fits`` from the FITS
    path) — repointing a history row at the archived FITS then keeps its
    coverage map resolvable.

    Returns ``{original_path: archived_path}`` for the ``fits``/``tiff``/
    ``preview`` artefacts (the ones recorded in ``stack_runs``), so the caller
    can repoint the previous run's row. The coverage sibling and the "watch it
    appear" reel are archived too but aren't in the returned map (they have no
    dedicated history column — they're resolved from the FITS basename).

    The set moved is :data:`RUN_ARTEFACT_SUFFIXES`; the compound ``_preview`` /
    ``_coverage`` / ``_progress`` names rebuild cleanly from the new basename.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived_basename = f"{out_basename}_{stamp}"
    # Avoid clobbering an already-archived set from the same second (near-
    # impossible for real multi-minute stacks, but rename() overwrites silently).
    n = 2
    while any(
        (out_dir / f"{archived_basename}{suffix}").exists()
        for suffix in RUN_ARTEFACT_SUFFIXES.values()
    ):
        archived_basename = f"{out_basename}_{stamp}_{n}"
        n += 1

    mapping: dict[str, str] = {}
    for kind, suffix in RUN_ARTEFACT_SUFFIXES.items():
        orig = out_dir / f"{out_basename}{suffix}"
        if not orig.exists():
            continue
        dst = out_dir / f"{archived_basename}{suffix}"
        try:
            orig.rename(dst)
            log.info("archived previous %s → %s", orig.name, dst.name)
            # coverage, frame-coverage + progress reel resolve from the FITS
            # basename (no dedicated history column), so they aren't in the map.
            if kind in _REPOINTABLE_ARTEFACTS:
                mapping[str(orig)] = str(dst)
        except OSError as exc:
            log.warning("could not archive %s: %s", orig, exc)
    return mapping
