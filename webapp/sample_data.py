"""Bundled "try it with a sample image" onboarding dataset.

A brand-new owner who installs AstroStack before their first clear night lands
on an empty app with nothing to do — every screen stays blank until real Seestar
frames arrive. This module builds a small, *generated* (nothing ships in the
image) demo target so a newcomer can walk the real journey — QC → stack → edit →
export — on real-looking data, then remove it in one click.

Design choices that keep it safe and self-contained:

* The subs are generated on demand from a tiny star-field writer (a slim,
  production copy of the test synthesiser), so the repo/image carry no binary
  fixtures.
* They are written *inside the target's own directory* (``sample_subs/``), so
  deleting the target with ``remove_files=True`` cleans up everything — source
  subs, Stage-1 cache and project DB — leaving no orphaned files.
* Each frame's WCS is injected directly (the true, known solution for the
  synthetic sky) instead of relying on ASTAP, so the demo is stackable on any
  install regardless of whether plate-solving is set up yet.
* The whole thing is additive and opt-in: it exists only after the user taps
  "Try it", uses the normal ingest/QC path, and touches no config/DB-schema/
  on-disk/default/API contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from seestack.core.cache import CacheManager
from seestack.io.ingest import ingest_files
from seestack.io.library import Library
from seestack.io.project import Project
from seestack.io.scanner import run_qc_and_solve

# The reserved display name for the demo target. Detection (is-the-sample-loaded,
# which-target-to-remove) keys on this exact name, so keep it stable — an older
# install that already loaded a sample must stay recognisable after an upgrade.
SAMPLE_TARGET_NAME = "Sample: Orion Nebula (M42)"

# The second, opt-in demo: the same sky shot as a 2×2 **mosaic**, which is how
# the owner actually shoots (AGENTS.md §1). It is a separate target with its own
# reserved name — the one above stays byte-for-byte what the Dashboard's "Try it"
# button loads — and both are swept away by the same remove.
#
# Why it exists: every surface gated on *no coverage* (the union canvas, coverage
# levelling, per-panel photometric normalisation, the uncovered-fraction note,
# the depth map, Auto's border trim) is structurally invisible on the single
# field above, whose canvas has no uncovered pixel and one coverage plateau. A
# real mosaic bug therefore survives any number of clean passes over the field
# sample — which is exactly what happened to D1 (Auto cropping a mosaic to its
# overlap band) through twenty sweeps and three audits.
SAMPLE_MOSAIC_TARGET_NAME = "Sample: M42 mosaic (2×2)"

#: Which demo to load / ask about. ``"field"`` is the default everywhere, so an
#: existing caller (and the Dashboard button) is unchanged.
SampleShape = Literal["field", "mosaic"]

# Subfolder (inside the target dir) that holds the generated source subs, so a
# ``remove_files=True`` delete of the target sweeps them away too.
_SAMPLE_SUBDIR = "sample_subs"

# A modest, showpiece-plausible configuration: a handful of dithered subs of one
# bright target. Small + few so generation + QC finish in a second or two.
_N_SUBS = 6
_WIDTH = 480
_HEIGHT = 320
_N_STARS = 55
_PIXSCALE_ARCSEC = 5.0
# M42 centre (deg) — the demo pretends to be the Orion Nebula.
_RA_CENTER_DEG = 83.82
_DEC_CENTER_DEG = -5.39


@dataclass(frozen=True)
class SampleStatus:
    """Whether the demo target exists, and a couple of facts for the UI."""

    loaded: bool
    safe: str | None = None
    n_frames: int = 0


_FWHM_PX = 4.0
_STAR_SIGMA = _FWHM_PX / 2.3548
_STAR_BOX = max(7, int(np.ceil(_STAR_SIGMA * 6)))


def _star_catalog(
    *, seed: int, width: int, height: int, n_stars: int,
) -> list[tuple[int, int, float]]:
    """``(x, y, peak)`` for one patch of synthetic sky, in *sky-pixel* coordinates.

    Split out of :func:`_make_star_field` so a mosaic's panels can render **the
    same sky** — each panel is a window onto this one catalog, so the stars in an
    overlap really are the same stars. Without that, an overlap holds two
    unrelated star fields and nothing that measures a mosaic's seams (the union
    canvas, per-panel photometry, the overlap itself) is being exercised at all.

    The draw order is the original's exactly — position, position, peak, per star
    — so the single-field sample generated through this comes out bit-identical
    to the one every prior baseline was measured on.
    """
    rng_stars = np.random.default_rng(seed)
    half = _STAR_BOX // 2
    stars: list[tuple[int, int, float]] = []
    for _ in range(n_stars):
        cx = int(rng_stars.integers(half + 4, width - half - 4))
        cy = int(rng_stars.integers(half + 4, height - half - 4))
        peak = float(rng_stars.uniform(2000, 30000))
        stars.append((cx, cy, peak))
    return stars


def _render_star_field(
    stars: list[tuple[int, int, float]],
    *,
    noise_seed: int,
    star_shift: tuple[float, float],
    origin: tuple[int, int] = (0, 0),
    signal_scale: float = 1.0,
    sky_scale: float = 1.0,
) -> np.ndarray:
    """Render one sub: the window of ``stars`` this frame points at, uint16.

    ``origin`` is the frame's top-left corner in the catalog's sky-pixel grid (a
    mosaic panel's pointing); ``star_shift`` is the sub-pixel dither on top of
    it. ``signal_scale`` / ``sky_scale`` dim the stars and lift the sky the way a
    hazy night does — multiplicative on the signal, additive on the sky, which is
    the one thing per-frame photometric normalisation cannot fix from inside a
    single panel.
    """
    rng_noise = np.random.default_rng(noise_seed)
    img = rng_noise.normal(
        loc=1000.0 * sky_scale, scale=50.0, size=(_HEIGHT, _WIDTH)
    ).astype(np.float32)

    box, half = _STAR_BOX, _STAR_BOX // 2
    sigma = _STAR_SIGMA
    sx, sy = star_shift
    ox, oy = origin
    yy, xx = np.indices((box, box))
    for cx, cy, peak in stars:
        kernel = (peak * signal_scale) * np.exp(
            -((xx - half - sx) ** 2 + (yy - half - sy) ** 2) / (2 * sigma * sigma)
        )
        x0, y0 = cx - half - ox, cy - half - oy
        # A panel's edge cuts stars in half — clip the paste rather than dropping
        # them, or every panel border would be a suspiciously star-free strip.
        xa, ya = max(0, x0), max(0, y0)
        xb, yb = min(_WIDTH, x0 + box), min(_HEIGHT, y0 + box)
        if xb <= xa or yb <= ya:
            continue
        img[ya:yb, xa:xb] += kernel[ya - y0 : yb - y0, xa - x0 : xb - x0]

    return np.clip(img, 0, 65535).astype(np.uint16)


def _make_star_field(
    *,
    seed: int,
    noise_seed: int,
    star_shift: tuple[float, float],
) -> np.ndarray:
    """A Bayer (RGGB) mosaic of Gaussian stars on a noisy sky, uint16.

    A slim production copy of ``tests/synth.make_star_field``: shared star
    positions (``seed``) with an independent noise draw (``noise_seed``) and a
    sub-pixel ``star_shift`` so a set of frames reads as a genuinely *dithered*
    session — stacking them then visibly averages the noise down (~√N).
    """
    stars = _star_catalog(seed=seed, width=_WIDTH, height=_HEIGHT, n_stars=_N_STARS)
    return _render_star_field(stars, noise_seed=noise_seed, star_shift=star_shift)


def _write_sample_fits(path: Path, *, index: int, star_shift: tuple[float, float]) -> None:
    """Write one Seestar-like sub with headers (no WCS — injected in the DB)."""
    from astropy.io import fits

    data = _make_star_field(seed=42, noise_seed=100 + index, star_shift=star_shift)
    hdu = fits.PrimaryHDU(data=data)
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.header["EXPTIME"] = 10.0
    hdu.header["GAIN"] = 80.0
    hdu.header["CCD-TEMP"] = -10.0
    # Space the subs a few minutes apart so night/session views read naturally.
    hdu.header["DATE-OBS"] = f"2024-11-15T22:{10 + index:02d}:00.000"
    hdu.header["INSTRUME"] = "Seestar S50"
    hdu.header["OBJECT"] = "M42 (sample)"
    hdu.writeto(path, overwrite=True)


def _frame_wcs(
    star_shift: tuple[float, float],
    *,
    origin: tuple[int, int] = (0, 0),
    window: tuple[int, int] | None = None,
):
    """The true WCS for a frame dithered by ``star_shift`` on the sensor.

    The stars moved by ``(dx, dy)`` on the sensor but stayed put on the sky, so
    the reference pixel moves with them — exactly the pairing the stacker needs
    to reproject the dithered subs back onto a common grid.

    ``origin`` / ``window`` extend the same idea to a mosaic: the sky centre
    (``crval``) is the centre of the whole ``window``, and a panel whose top-left
    corner sits at ``origin`` in that window sees it that many pixels off to one
    side. A single field is ``origin=(0, 0)`` with the window equal to the frame,
    which reproduces the original expression exactly.
    """
    from astropy.wcs import WCS

    dx, dy = star_shift
    ox, oy = origin
    win_w, win_h = window if window is not None else (_WIDTH, _HEIGHT)
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [_RA_CENTER_DEG, _DEC_CENTER_DEG]
    w.wcs.crpix = [win_w / 2 + 0.5 - ox + dx, win_h / 2 + 0.5 - oy + dy]
    w.wcs.cdelt = [-_PIXSCALE_ARCSEC / 3600.0, _PIXSCALE_ARCSEC / 3600.0]
    return w


def _wcs_header_text(
    star_shift: tuple[float, float],
    *,
    origin: tuple[int, int] = (0, 0),
    window: tuple[int, int] | None = None,
) -> str:
    """:func:`_frame_wcs` as the header text the project DB stores."""
    return str(_frame_wcs(star_shift, origin=origin, window=window).to_header(relax=True))


def _frame_center_deg(
    star_shift: tuple[float, float],
    *,
    origin: tuple[int, int] = (0, 0),
    window: tuple[int, int] | None = None,
) -> tuple[float, float]:
    """Where *this frame's* centre points, in RA/Dec degrees.

    A mosaic's panels are different patches of sky, and every per-panel decision
    in the engine (QC grading, photometric normalisation, the panel labels
    themselves) clusters the frames by exactly this pair — so a mosaic sample
    whose subs all recorded the mosaic's centre would cluster as one pointing and
    exercise none of it.
    """
    w = _frame_wcs(star_shift, origin=origin, window=window)
    ra, dec = w.wcs_pix2world([[(_WIDTH - 1) / 2, (_HEIGHT - 1) / 2]], 0)[0]
    return float(ra), float(dec)


# --- the 2×2 mosaic sample -------------------------------------------------
#
# Panels step 82 % of a frame, so neighbours share ~18 % — a Seestar mosaic's own
# shape. On top of that each panel carries a small pointing error, which is what
# makes the union canvas **ragged**: the bounding box of four jittered rectangles
# has uncovered corners, so the sample finally has NaN "no coverage" pixels to
# reason about. Deliberately integers, not a random draw: the sample must be the
# same picture on every install and in every test run.
_MOSAIC_STEP_FRAC = 0.82
_MOSAIC_JITTER_PX: tuple[tuple[int, int], ...] = ((0, 0), (12, -14), (-14, 10), (8, 14))
# Panel order is (col, row): top-left, top-right, bottom-left, bottom-right.
_MOSAIC_GRID: tuple[tuple[int, int], ...] = ((0, 0), (1, 0), (0, 1), (1, 1))
# **Uneven depth, deliberately** (AGENTS.md §1): one panel got clouded out after
# three subs. A mosaic whose panels are all equally deep reads as "nothing to
# level" and every per-panel surface stays quiet.
_MOSAIC_PANEL_SUBS: tuple[int, ...] = (6, 6, 6, 3)
# …and one panel was shot through haze: its stars are dimmer *and* its sky is
# brighter. Multiplicative on the signal, so it is the one thing per-frame
# photometric normalisation cannot fix from inside the panel (it gain-matches
# each sub against its own panel's median, and a wholly hazy panel is its own
# median) — the open "match each panel's gain from the overlaps" item.
_MOSAIC_HAZY_PANEL = 1
_MOSAIC_HAZE_SIGNAL = 0.85
_MOSAIC_HAZE_SKY = 1.08
# The thin panel was shot on the following night, so the sample also has a
# genuine two-night history the session/night surfaces can render.
_MOSAIC_NIGHTS = ("2024-11-15", "2024-11-15", "2024-11-15", "2024-11-16")
# Stars per sky window rather than per frame: the window is ~3.6× a frame's area,
# so this keeps the on-sky star density the single-field sample already has.
_MOSAIC_N_STARS = 200
_MOSAIC_SUBDIR = "sample_mosaic_subs"


@dataclass(frozen=True)
class _MosaicPanel:
    """One panel of the mosaic sample: where it points and how it was shot."""

    index: int
    origin: tuple[int, int]
    n_subs: int
    signal_scale: float
    sky_scale: float
    night: str


def _mosaic_layout() -> tuple[list[_MosaicPanel], tuple[int, int]]:
    """The panels and the sky window they tile, in catalog pixel coordinates."""
    step_x = int(round(_WIDTH * _MOSAIC_STEP_FRAC))
    step_y = int(round(_HEIGHT * _MOSAIC_STEP_FRAC))
    raw = [
        (col * step_x + jx, row * step_y + jy)
        for (col, row), (jx, jy) in zip(_MOSAIC_GRID, _MOSAIC_JITTER_PX)
    ]
    min_x = min(x for x, _ in raw)
    min_y = min(y for _, y in raw)
    origins = [(x - min_x, y - min_y) for x, y in raw]
    window = (
        max(x for x, _ in origins) + _WIDTH,
        max(y for _, y in origins) + _HEIGHT,
    )
    panels = [
        _MosaicPanel(
            index=i,
            origin=origins[i],
            n_subs=_MOSAIC_PANEL_SUBS[i],
            signal_scale=_MOSAIC_HAZE_SIGNAL if i == _MOSAIC_HAZY_PANEL else 1.0,
            sky_scale=_MOSAIC_HAZE_SKY if i == _MOSAIC_HAZY_PANEL else 1.0,
            night=_MOSAIC_NIGHTS[i],
        )
        for i in range(len(origins))
    ]
    return panels, window


def _write_mosaic_fits(
    path: Path,
    *,
    stars: list[tuple[int, int, float]],
    panel: _MosaicPanel,
    sub: int,
    noise_seed: int,
    star_shift: tuple[float, float],
) -> None:
    """Write one sub of one mosaic panel (no WCS — injected in the DB)."""
    from astropy.io import fits

    data = _render_star_field(
        stars,
        noise_seed=noise_seed,
        star_shift=star_shift,
        origin=panel.origin,
        signal_scale=panel.signal_scale,
        sky_scale=panel.sky_scale,
    )
    hdu = fits.PrimaryHDU(data=data)
    hdu.header["BAYERPAT"] = "RGGB"
    hdu.header["EXPTIME"] = 10.0
    hdu.header["GAIN"] = 80.0
    hdu.header["CCD-TEMP"] = -10.0
    hdu.header["DATE-OBS"] = f"{panel.night}T22:{10 + panel.index * 12 + sub:02d}:00.000"
    # The owner's scope (AGENTS.md §1 — an S30, not the S50 the older sample
    # names), with the focal length that says so to anything deriving the model
    # from the frame rather than trusting the string.
    hdu.header["INSTRUME"] = "Seestar S30"
    hdu.header["FOCALLEN"] = 150.0
    hdu.header["OBJECT"] = "M42 mosaic (sample)"
    hdu.writeto(path, overwrite=True)


def _dither_offsets(n: int) -> list[tuple[float, float]]:
    """A small spiral-ish dither pattern, first frame un-shifted (the reference)."""
    pattern = [
        (0.0, 0.0), (2.0, 1.0), (-1.5, 2.0), (-2.0, -1.5),
        (1.0, -2.0), (2.5, 2.5), (-2.5, 1.5), (0.5, -2.5),
    ]
    return [pattern[i % len(pattern)] for i in range(n)]


def sample_target_name(shape: SampleShape = "field") -> str:
    """The reserved display name for one demo shape."""
    return SAMPLE_MOSAIC_TARGET_NAME if shape == "mosaic" else SAMPLE_TARGET_NAME


def get_sample_status(lib: Library, shape: SampleShape = "field") -> SampleStatus:
    """Report whether the demo target exists (by its reserved display name)."""
    entry = lib.find_target(sample_target_name(shape))
    if entry is None:
        return SampleStatus(loaded=False)
    try:
        proj = Project.open(lib.target_dir(entry))
    except Exception:  # noqa: BLE001 — a half-removed target reads as "not loaded"
        return SampleStatus(loaded=False)
    try:
        n_frames = sum(1 for _ in proj.iter_frames())
    finally:
        proj.close()
    return SampleStatus(loaded=True, safe=entry.safe_name, n_frames=n_frames)


def load_sample(lib: Library, shape: SampleShape = "field") -> SampleStatus:
    """Create the demo target from generated subs, run QC, inject WCS.

    Idempotent: if the sample already exists it is returned unchanged rather than
    duplicated, so a double-tap is harmless. ``shape="mosaic"`` builds the second,
    opt-in demo (a separate target) instead; the default is the single field the
    Dashboard's "Try it" button has always loaded.
    """
    if shape == "mosaic":
        return _load_mosaic_sample(lib)
    existing = get_sample_status(lib)
    if existing.loaded:
        return existing

    entry, proj = lib.create_target(
        SAMPLE_TARGET_NAME, ra_deg=_RA_CENTER_DEG, dec_deg=_DEC_CENTER_DEG,
        notes="A generated demo target — remove it any time from the Dashboard.",
    )
    try:
        sample_dir = lib.target_dir(entry) / _SAMPLE_SUBDIR
        sample_dir.mkdir(parents=True, exist_ok=True)
        offsets = _dither_offsets(_N_SUBS)
        for i, shift in enumerate(offsets):
            _write_sample_fits(sample_dir / f"sample_{i:03d}.fit", index=i, star_shift=shift)

        cache = CacheManager(lib.target_dir(entry))
        sources = sorted(sample_dir.glob("*.fit"))
        for _ in ingest_files(proj, cache, sources, copy_to_cache=True):
            pass

        # QC only — the frames' true WCS is injected below, so ASTAP is not needed
        # (and won't solve synthetic star fields on most installs anyway).
        run_qc_and_solve(proj, run_qc=True, run_solve=False, serial=True)

        # Pair each frame with the true solution for its dither so it stacks.
        frames = sorted(proj.iter_frames(), key=lambda f: f.source_path)
        for frame, shift in zip(frames, offsets):
            if frame.id is None:
                continue
            proj.update_frame(
                frame.id,
                wcs_json=_wcs_header_text(shift),
                ra_center_deg=_RA_CENTER_DEG,
                dec_center_deg=_DEC_CENTER_DEG,
                pixscale_arcsec=_PIXSCALE_ARCSEC,
                width_px=_WIDTH,
                height_px=_HEIGHT,
                bayer_pattern="RGGB",
            )
        n_frames = sum(1 for _ in proj.iter_frames())
    finally:
        proj.close()

    # Publish the frames to the *library* row, exactly as a scan does
    # (``scanner.py`` ends with the same call). Without it the sample's subs
    # exist only inside its project DB: the Library card reads "0/0 frames" with
    # no integration, the Dashboard's frame/integration tiles stay at zero, and
    # the Tonight planner ranks the demo as "you haven't captured any of it yet"
    # — the newcomer's first screen contradicting the sample it just made for
    # them. Cheap (one project re-open, once, on an explicit user action) and
    # idempotent, so the early-return above needs nothing.
    lib.refresh_target_stats(entry.safe_name)

    return SampleStatus(loaded=True, safe=entry.safe_name, n_frames=n_frames)


def _load_mosaic_sample(lib: Library) -> SampleStatus:
    """Build the 2×2 mosaic demo: four overlapping panels of one shared sky.

    Same machinery as the single field — generate → ingest → QC → inject the true
    WCS — with three differences that are the whole point of it: the panels are
    windows onto **one** star catalog (so an overlap really holds the same
    stars), their depth is uneven, and one of them was shot through haze.
    """
    existing = get_sample_status(lib, shape="mosaic")
    if existing.loaded:
        return existing

    panels, window = _mosaic_layout()
    stars = _star_catalog(
        seed=42, width=window[0], height=window[1], n_stars=_MOSAIC_N_STARS,
    )

    entry, proj = lib.create_target(
        SAMPLE_MOSAIC_TARGET_NAME, ra_deg=_RA_CENTER_DEG, dec_deg=_DEC_CENTER_DEG,
        notes="A generated demo mosaic — remove it any time from the Dashboard.",
    )
    try:
        sample_dir = lib.target_dir(entry) / _MOSAIC_SUBDIR
        sample_dir.mkdir(parents=True, exist_ok=True)
        # Filenames sort panel-major, so the ingested frames pair back up with
        # this list by sorted source path — the same pairing the field sample uses.
        plan: list[tuple[_MosaicPanel, tuple[float, float]]] = []
        for panel in panels:
            for sub, shift in enumerate(_dither_offsets(panel.n_subs)):
                path = sample_dir / f"sample_p{panel.index}_{sub:03d}.fit"
                _write_mosaic_fits(
                    path, stars=stars, panel=panel, sub=sub,
                    noise_seed=500 + panel.index * 20 + sub, star_shift=shift,
                )
                plan.append((panel, shift))

        cache = CacheManager(lib.target_dir(entry))
        sources = sorted(sample_dir.glob("*.fit"))
        for _ in ingest_files(proj, cache, sources, copy_to_cache=True):
            pass

        run_qc_and_solve(proj, run_qc=True, run_solve=False, serial=True)

        frames = sorted(proj.iter_frames(), key=lambda f: f.source_path)
        for frame, (panel, shift) in zip(frames, plan):
            if frame.id is None:
                continue
            ra, dec = _frame_center_deg(shift, origin=panel.origin, window=window)
            proj.update_frame(
                frame.id,
                wcs_json=_wcs_header_text(shift, origin=panel.origin, window=window),
                ra_center_deg=ra,
                dec_center_deg=dec,
                pixscale_arcsec=_PIXSCALE_ARCSEC,
                width_px=_WIDTH,
                height_px=_HEIGHT,
                bayer_pattern="RGGB",
            )
        n_frames = sum(1 for _ in proj.iter_frames())
    finally:
        proj.close()

    lib.refresh_target_stats(entry.safe_name)
    return SampleStatus(loaded=True, safe=entry.safe_name, n_frames=n_frames)


def remove_sample(lib: Library) -> bool:
    """Delete the demo targets and their generated files.

    Removes **both** shapes — one "remove the sample" action, whichever demos the
    user asked for — and returns False only when neither existed.
    """
    removed = False
    for shape in ("field", "mosaic"):
        entry = lib.find_target(sample_target_name(shape))  # type: ignore[arg-type]
        if entry is None:
            continue
        removed = lib.delete_target(entry.safe_name, remove_files=True) or removed
    return removed
