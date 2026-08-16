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
    rng_noise = np.random.default_rng(noise_seed)
    rng_stars = np.random.default_rng(seed)
    img = rng_noise.normal(loc=1000.0, scale=50.0, size=(_HEIGHT, _WIDTH)).astype(np.float32)

    fwhm_px = 4.0
    sigma = fwhm_px / 2.3548
    box = max(7, int(np.ceil(sigma * 6)))
    half = box // 2
    sx, sy = star_shift
    yy, xx = np.indices((box, box))
    for _ in range(_N_STARS):
        cx = int(rng_stars.integers(half + 4, _WIDTH - half - 4))
        cy = int(rng_stars.integers(half + 4, _HEIGHT - half - 4))
        peak = float(rng_stars.uniform(2000, 30000))
        kernel = peak * np.exp(
            -((xx - half - sx) ** 2 + (yy - half - sy) ** 2) / (2 * sigma * sigma)
        )
        img[cy - half : cy - half + box, cx - half : cx - half + box] += kernel

    return np.clip(img, 0, 65535).astype(np.uint16)


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


def _wcs_header_text(star_shift: tuple[float, float]) -> str:
    """The true WCS for a frame dithered by ``star_shift`` on the sensor.

    The stars moved by ``(dx, dy)`` on the sensor but stayed put on the sky, so
    the reference pixel moves with them — exactly the pairing the stacker needs
    to reproject the dithered subs back onto a common grid.
    """
    from astropy.wcs import WCS

    dx, dy = star_shift
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [_RA_CENTER_DEG, _DEC_CENTER_DEG]
    w.wcs.crpix = [_WIDTH / 2 + 0.5 + dx, _HEIGHT / 2 + 0.5 + dy]
    w.wcs.cdelt = [-_PIXSCALE_ARCSEC / 3600.0, _PIXSCALE_ARCSEC / 3600.0]
    return str(w.to_header(relax=True))


def _dither_offsets(n: int) -> list[tuple[float, float]]:
    """A small spiral-ish dither pattern, first frame un-shifted (the reference)."""
    pattern = [
        (0.0, 0.0), (2.0, 1.0), (-1.5, 2.0), (-2.0, -1.5),
        (1.0, -2.0), (2.5, 2.5), (-2.5, 1.5), (0.5, -2.5),
    ]
    return [pattern[i % len(pattern)] for i in range(n)]


def get_sample_status(lib: Library) -> SampleStatus:
    """Report whether the demo target exists (by its reserved display name)."""
    entry = lib.find_target(SAMPLE_TARGET_NAME)
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


def load_sample(lib: Library) -> SampleStatus:
    """Create the demo target from generated subs, run QC, inject WCS.

    Idempotent: if the sample already exists it is returned unchanged rather than
    duplicated, so a double-tap is harmless.
    """
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


def remove_sample(lib: Library) -> bool:
    """Delete the demo target and its generated files. Returns False if absent."""
    entry = lib.find_target(SAMPLE_TARGET_NAME)
    if entry is None:
        return False
    return lib.delete_target(entry.safe_name, remove_files=True)
