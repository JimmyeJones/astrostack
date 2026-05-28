"""
WCS serialization for the project DB.

We store an astropy WCS as a FITS-header text blob in the ``wcs_json`` column
(despite the name — it's not really JSON, it's FITS header text, which is plain
ASCII and easy to inspect). FITS header round-trips cleanly through astropy
without any data loss.

This module wraps that round-trip so the rest of the code doesn't have to care
about astropy import paths or header formatting details.
"""

from __future__ import annotations

from pathlib import Path


def wcs_to_text(wcs) -> str:
    """Serialize an astropy WCS to a FITS-header text string."""
    return str(wcs.to_header(relax=True))


def wcs_from_text(text: str | None):
    """Reconstruct a WCS from a stored text blob. Returns None on failure."""
    if not text:
        return None
    import warnings

    from astropy.io.fits import Header
    from astropy.wcs import FITSFixedWarning, WCS

    try:
        with warnings.catch_warnings():
            # astropy "fixes" DATE-OBS → MJD-OBS and warns every time; it's
            # harmless normalisation, just noise. Silence it.
            warnings.simplefilter("ignore", FITSFixedWarning)
            return WCS(Header.fromstring(text))
    except Exception:  # noqa: BLE001 — corrupt cache, treat as missing
        return None


def wcs_text_from_sidecar(wcs_path: str | Path) -> str | None:
    """Read an ASTAP ``.wcs`` sidecar file and return its FITS header as text."""
    wcs_path = Path(wcs_path)
    if not wcs_path.exists():
        return None
    from astropy.io.fits import Header

    try:
        # ASTAP writes a tiny FITS header file (no data block).
        with open(wcs_path, "rb") as f:
            raw = f.read().decode("ascii", errors="replace")
        # The header is padded to multiples of 2880 bytes by FITS convention,
        # but astropy's ``Header.fromstring`` handles that gracefully.
        return str(Header.fromstring(raw))
    except Exception:  # noqa: BLE001
        return None


def footprint_radec_deg(wcs, width_px: int, height_px: int) -> list[tuple[float, float]] | None:
    """
    Return the four corners of the frame in RA/Dec degrees, in image order
    (TL, TR, BR, BL). Useful for footprint plotting and mosaic detection.
    """
    if wcs is None:
        return None
    try:
        # pixel_to_world gives a SkyCoord; we want degrees as plain floats.
        corners_px = [(0, 0), (width_px - 1, 0), (width_px - 1, height_px - 1), (0, height_px - 1)]
        out: list[tuple[float, float]] = []
        for x, y in corners_px:
            sky = wcs.pixel_to_world(x, y)
            out.append((float(sky.ra.deg), float(sky.dec.deg)))
        return out
    except Exception:  # noqa: BLE001
        return None
