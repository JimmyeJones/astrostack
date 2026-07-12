"""Identify a captured target against the bundled deep-sky catalog.

A pure, **offline** lookup that turns a bare folder name (``M_31``) or a
plate-solved field centre into friendly context a beginner enjoys: the object's
common name, a plain-language type ("barred spiral galaxy" — but our catalog
already stores plain types), the constellation it sits in, and its catalog id.

No network, no heavy dependency — it reads the same static catalog the Tonight
planner uses (:func:`seestack.nightplan.load_catalog`) and returns ``None`` when
nothing matches, so the UI can render a card only when there's something real to
say. Matching is deliberately conservative (an exact designation/name match, or
a tight cone around a *solved* centre) so it never guesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from seestack.nightplan import CatalogObject, _angular_sep_deg, load_catalog

# IAU 3-letter constellation abbreviation → full name. Static and offline; the
# bundled catalog uses these abbreviations in its ``con`` field. The full 88 are
# listed so the map keeps working if the catalog grows.
CONSTELLATION_NAMES: dict[str, str] = {
    "And": "Andromeda", "Ant": "Antlia", "Aps": "Apus", "Aqr": "Aquarius",
    "Aql": "Aquila", "Ara": "Ara", "Ari": "Aries", "Aur": "Auriga",
    "Boo": "Boötes", "Cae": "Caelum", "Cam": "Camelopardalis", "Cnc": "Cancer",
    "CVn": "Canes Venatici", "CMa": "Canis Major", "CMi": "Canis Minor",
    "Cap": "Capricornus", "Car": "Carina", "Cas": "Cassiopeia", "Cen": "Centaurus",
    "Cep": "Cepheus", "Cet": "Cetus", "Cha": "Chamaeleon", "Cir": "Circinus",
    "Col": "Columba", "Com": "Coma Berenices", "CrA": "Corona Australis",
    "CrB": "Corona Borealis", "Crv": "Corvus", "Crt": "Crater", "Cru": "Crux",
    "Cyg": "Cygnus", "Del": "Delphinus", "Dor": "Dorado", "Dra": "Draco",
    "Equ": "Equuleus", "Eri": "Eridanus", "For": "Fornax", "Gem": "Gemini",
    "Gru": "Grus", "Her": "Hercules", "Hor": "Horologium", "Hya": "Hydra",
    "Hyi": "Hydrus", "Ind": "Indus", "Lac": "Lacerta", "Leo": "Leo",
    "LMi": "Leo Minor", "Lep": "Lepus", "Lib": "Libra", "Lup": "Lupus",
    "Lyn": "Lynx", "Lyr": "Lyra", "Men": "Mensa", "Mic": "Microscopium",
    "Mon": "Monoceros", "Mus": "Musca", "Nor": "Norma", "Oct": "Octans",
    "Oph": "Ophiuchus", "Ori": "Orion", "Pav": "Pavo", "Peg": "Pegasus",
    "Per": "Perseus", "Phe": "Phoenix", "Pic": "Pictor", "Psc": "Pisces",
    "PsA": "Piscis Austrinus", "Pup": "Puppis", "Pyx": "Pyxis",
    "Ret": "Reticulum", "Sge": "Sagitta", "Sgr": "Sagittarius", "Sco": "Scorpius",
    "Scl": "Sculptor", "Sct": "Scutum", "Ser": "Serpens", "Sex": "Sextans",
    "Tau": "Taurus", "Tel": "Telescopium", "Tri": "Triangulum",
    "TrA": "Triangulum Australe", "Tuc": "Tucana", "UMa": "Ursa Major",
    "UMi": "Ursa Minor", "Vel": "Vela", "Vir": "Virgo", "Vol": "Volans",
    "Vul": "Vulpecula",
}

# How close a *solved* field centre must sit to a catalog object to count as
# "that's what you shot". The Seestar OSC field is ~1.3°×0.7°, so a genuine
# framing lands well within this; a tight radius avoids claiming a neighbour.
_CONE_MATCH_DEG = 0.75

# A catalog-style designation token anywhere in a name: "M 31", "M_31", "NGC7000",
# "ic 1805", "C 14". Captures the prefix and the number so we can normalise both.
_DESIGNATION_RE = re.compile(r"\b(m|ngc|ic|c)\s*[_\-]?\s*0*(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ObjectInfo:
    """Friendly identity for a captured target, ready to render on a card."""

    id: str                 # catalog designation, e.g. "M31" / "NGC7000"
    name: str               # common name, "" if the catalog has none
    type: str               # plain-language type, e.g. "galaxy"
    constellation: str      # full constellation name, "" if the abbr is unknown
    constellation_abbr: str  # raw catalog abbreviation, e.g. "And"
    ra_deg: float
    dec_deg: float
    matched_by: str         # "name" or "coords" — how we identified it


def _norm_name(s: str) -> str:
    """Loose form for common-name equality: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _norm_designation(text: str) -> str | None:
    """Extract and normalise the first catalog designation in ``text``.

    ``"M_31 Andromeda"`` → ``"M31"``, ``"NGC 7000"`` → ``"NGC7000"``. Leading
    zeros are stripped so ``"NGC 0224"`` and ``"NGC224"`` match. ``None`` when the
    text carries no designation-like token.
    """
    m = _DESIGNATION_RE.search(text)
    if m is None:
        return None
    return f"{m.group(1).upper()}{int(m.group(2))}"


def identify_object(
    name: str | None,
    ra_deg: float | None = None,
    dec_deg: float | None = None,
    *,
    catalog: tuple[CatalogObject, ...] | None = None,
) -> ObjectInfo | None:
    """Best-effort identify a target from its ``name`` and/or solved centre.

    Tries, in order: (1) an exact catalog **designation** parsed from the name
    (M/NGC/IC/C + number), (2) an exact **common-name** match, then (3) a tight
    **cone match** against a solved ``ra_deg``/``dec_deg``. Returns ``None`` when
    nothing matches confidently, so the caller shows no card rather than a guess.
    """
    cat = catalog if catalog is not None else load_catalog()

    if name:
        want_desig = _norm_designation(name)
        if want_desig is not None:
            for obj in cat:
                if _norm_designation(obj.id) == want_desig:
                    return _to_info(obj, "name")
        want_name = _norm_name(name)
        if want_name:
            for obj in cat:
                if obj.name and _norm_name(obj.name) == want_name:
                    return _to_info(obj, "name")

    if ra_deg is not None and dec_deg is not None:
        best: CatalogObject | None = None
        best_sep = _CONE_MATCH_DEG
        for obj in cat:
            sep = _angular_sep_deg(ra_deg, dec_deg, obj.ra_deg, obj.dec_deg)
            if sep < best_sep:
                best, best_sep = obj, sep
        if best is not None:
            return _to_info(best, "coords")

    return None


def _to_info(obj: CatalogObject, matched_by: str) -> ObjectInfo:
    return ObjectInfo(
        id=obj.id,
        name=obj.name,
        type=obj.type,
        constellation=CONSTELLATION_NAMES.get(obj.con, ""),
        constellation_abbr=obj.con,
        ra_deg=obj.ra_deg,
        dec_deg=obj.dec_deg,
        matched_by=matched_by,
    )
