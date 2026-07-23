"""
Auto-identify the imaged target.

Given a project's median plate-solved RA/Dec, look it up against SIMBAD to
identify what's actually in the field (M42? NGC 7000? PGC 12345?). Use the
resulting object type to recommend bg-flatten and stretch settings:

  - **Galaxy / cluster / planetary nebula**: small extent → per-channel bg
    flatten, default box size.
  - **Diffuse emission nebula** (HII regions, etc.): large extent → linear
    output is fine, bg flatten OFF or luminance, large box.

SIMBAD lookup goes through ``astroquery.simbad``. If astroquery isn't
installed or the query fails (offline, server timeout), we fall back to
"unknown target — keep defaults" silently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# SIMBAD's main object types we care about — mapped to bg-flatten suggestion.
# https://simbad.cds.unistra.fr/guide/otypes.htx
_TYPE_HINTS: dict[str, str] = {
    # Galaxies (small extent, sky-dominated frame): per-channel works well.
    "G": "per_channel",
    "GiC": "per_channel",
    "GiG": "per_channel",
    "GiP": "per_channel",
    "Sy": "per_channel",
    "AGN": "per_channel",
    # Star clusters: small + many stars + lots of sky.
    "OpC": "per_channel",
    "GlC": "per_channel",
    "Cl*": "per_channel",
    # Planetary nebula (typically small): per_channel.
    "PN": "per_channel",
    # Emission / reflection nebulas — often large extent.
    "HII": "off",
    "RNe": "luminance",
    "ISM": "luminance",
    "MoC": "luminance",
    "DNe": "luminance",
    "EmO": "luminance",
}

# Plain-language names for SIMBAD's short OTYPE codes, so any surface that shows
# the object type reads "Galaxy" rather than a bare "G". Covers the codes we map
# for a bg-flatten hint plus the common OSC-Seestar targets. Unknown codes fall
# back to the raw code (see ``friendly_object_type``), so this never hides data.
# https://simbad.cds.unistra.fr/guide/otypes.htx
_OTYPE_NAMES: dict[str, str] = {
    # Galaxies
    "G": "Galaxy",
    "GiC": "Galaxy in cluster",
    "GiG": "Galaxy in group",
    "GiP": "Galaxy in pair",
    "IG": "Interacting galaxies",
    "Sy": "Seyfert galaxy",
    "AGN": "Active galaxy nucleus",
    "QSO": "Quasar",
    # Star clusters
    "OpC": "Open cluster",
    "GlC": "Globular cluster",
    "Cl*": "Star cluster",
    "As*": "Stellar association",
    # Nebulae
    "PN": "Planetary nebula",
    "HII": "HII region",
    "RNe": "Reflection nebula",
    "DNe": "Dark nebula",
    "EmO": "Emission object",
    "SNR": "Supernova remnant",
    "MoC": "Molecular cloud",
    "ISM": "Interstellar medium",
    "GNe": "Galactic nebula",
    "Cld": "Cloud",
    # Stars (a plate-solve can land on a bright star, not a deep-sky object)
    "*": "Star",
    "**": "Double star",
    "V*": "Variable star",
    "Em*": "Emission-line star",
}


def friendly_object_type(code: str | None) -> str | None:
    """Map a SIMBAD short OTYPE code to a plain-language name.

    Falls back to the raw code for anything not in the table (so an
    unrecognised type still shows *something* rather than nothing), and
    returns ``None`` for a missing code.
    """
    if not code:
        return None
    return _OTYPE_NAMES.get(code, code)


# Friendly descriptions of the recommendation, for the GUI tooltip.
_REASONS: dict[str, str] = {
    "per_channel": "small target / star-dominated field",
    "luminance": "extended structure — luminance-linked bg flatten keeps colour clean",
    "off": "target fills most of the frame — bg flatten can't help here; "
           "use linear output and do gradient removal in PixInsight/Siril",
}


@dataclass
class TargetIdResult:
    """Outcome of one SIMBAD lookup."""

    identifier: str | None      # e.g. "M 42", "NGC 7000"
    object_type: str | None     # SIMBAD short type code
    object_type_name: str | None
    bg_mode_hint: str | None    # 'per_channel' | 'luminance' | 'off'
    hint_reason: str | None
    error: str | None = None


def identify_target(ra_deg: float, dec_deg: float, *,
                    search_radius_arcmin: float = 30.0) -> TargetIdResult:
    """
    Query SIMBAD for the catalog object nearest (RA, Dec).

    Returns a ``TargetIdResult``. If astroquery isn't available or the query
    fails, the result has ``error`` set and other fields are None — callers
    should just keep defaults in that case.
    """
    try:
        from astroquery.simbad import Simbad
    except ImportError:
        return TargetIdResult(None, None, None, None, None,
                              error="astroquery not installed")

    try:
        from astropy.coordinates import SkyCoord
        import astropy.units as u
    except ImportError as exc:
        return TargetIdResult(None, None, None, None, None,
                              error=f"astropy missing: {exc}")

    try:
        custom = Simbad()
        # otype gives the short type code we use for the hint mapping.
        try:
            custom.add_votable_fields("otype")
        except Exception:  # noqa: BLE001 — already added or rejected by server
            pass
        coord = SkyCoord(ra_deg * u.deg, dec_deg * u.deg)
        table = custom.query_region(coord, radius=search_radius_arcmin * u.arcmin)
    except Exception as exc:  # noqa: BLE001
        return TargetIdResult(None, None, None, None, None,
                              error=f"SIMBAD query failed: {exc}")

    if table is None or len(table) == 0:
        return TargetIdResult(None, None, None, None, None,
                              error="no SIMBAD match within search radius")

    # query_region returns rows in SIMBAD's catalog order, NOT sorted by angular
    # separation, so table[0] can be any object in the cone (e.g. a Trapezium
    # star instead of M 42). Pick the row actually nearest the frame centre.
    row = _pick_nearest_row(table, ra_deg, dec_deg)
    name = _get_string(row, "MAIN_ID", "main_id")
    otype = _get_string(row, "OTYPE", "otype")
    hint = _TYPE_HINTS.get(otype) if otype else None
    reason = _REASONS.get(hint) if hint else None
    return TargetIdResult(
        identifier=name, object_type=otype,
        object_type_name=friendly_object_type(otype),
        bg_mode_hint=hint, hint_reason=reason,
    )


def _row_coord(row):
    """Build a ``SkyCoord`` from a SIMBAD result row's RA/Dec columns.

    Returns ``None`` if the row carries no readable coordinates. Handles both
    astroquery column conventions: modern releases give numeric ``ra``/``dec``
    in decimal degrees; older ones give sexagesimal ``RA`` (hours) / ``DEC``
    (degrees) strings.
    """
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    ra = _get_string(row, "ra", "RA_d", "RA")
    dec = _get_string(row, "dec", "DEC_d", "DEC")
    if ra is None or dec is None:
        return None
    # Numeric decimal degrees (the common, unambiguous modern case).
    try:
        return SkyCoord(float(ra) * u.deg, float(dec) * u.deg)
    except (ValueError, TypeError):
        pass
    # Sexagesimal strings: RA in hours, Dec in degrees.
    try:
        return SkyCoord(ra, dec, unit=(u.hourangle, u.deg))
    except Exception:  # noqa: BLE001 — malformed/unparseable coordinate string
        return None


def _pick_nearest_row(table, ra_deg: float, dec_deg: float):
    """Return the result row angularly closest to the query centre.

    ``Simbad.query_region`` returns rows in SIMBAD's internal catalog order, not
    sorted by separation, so ``table[0]`` can be any object in the search cone
    (e.g. a Trapezium star instead of M 42). Pick the true nearest so the
    friendly name and bg-flatten hint describe the framed target. Falls back to
    row 0 if no row has readable coordinates (preserving prior behaviour).
    """
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    center = SkyCoord(ra_deg * u.deg, dec_deg * u.deg)
    best_i: int | None = None
    best_sep: float | None = None
    for i in range(len(table)):
        coord = _row_coord(table[i])
        if coord is None:
            continue
        sep = float(center.separation(coord).deg)
        if best_sep is None or sep < best_sep:
            best_i, best_sep = i, sep
    return table[best_i] if best_i is not None else table[0]


def _get_string(row, *keys: str) -> str | None:
    """Try several column name conventions (astroquery has changed casing over time)."""
    for k in keys:
        try:
            v = row[k]
            if hasattr(v, "decode"):
                v = v.decode("ascii", errors="replace")
            v = str(v).strip()
            if v and v.lower() not in {"--", "none"}:
                return v
        except (KeyError, IndexError, TypeError):
            continue
    return None
