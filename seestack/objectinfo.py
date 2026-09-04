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

import math
import re
from dataclasses import dataclass

from seestack.angularsize import AngularSize, angular_size
from seestack.bg_advice import BackgroundModeHint, background_mode_hint
from seestack.framing import (
    FrameField,
    FramingHint,
    MosaicPlan,
    framing_hint,
    mosaic_plan,
)
from seestack.lighttravel import LightTravel, light_travel
from seestack.nightplan import CatalogObject, _angular_sep_deg, load_catalog
from seestack.target_difficulty import DifficultyHint, target_difficulty

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
    size_arcmin: float | None = None   # major-axis size, when the catalog has one
    framing: FramingHint | None = None  # "will it fit in one frame?" verdict
    # "How big a mosaic?" — the panel grid this object's span needs, for the ones
    # too big for a single frame. ``None`` when it fits (or has no vetted size),
    # so the card says nothing rather than planning a one-panel mosaic.
    mosaic: MosaicPlan | None = None
    blurb: str = ""         # plain-language "what am I looking at?" one-liner, "" if none
    difficulty: DifficultyHint | None = None  # "how hard for a Seestar?" verdict, if vetted
    # Which per-frame background-flatten mode suits this target, when its catalog
    # type/size say the default per-channel fit would bend into it; None
    # otherwise (the default is fine, so there is nothing to say).
    background_mode_hint: BackgroundModeHint | None = None
    # "How far did you see?" — the light-travel line built from the catalog
    # distance. None when the catalog has no vetted distance, so the card simply
    # says nothing rather than guessing.
    light_travel: LightTravel | None = None
    # "How big is it, really?" — the catalog's angular size expressed in full
    # Moons, the one yardstick a non-astronomer already owns. None when the
    # catalog has no vetted size, or the object is too small for the comparison
    # to say anything (see :mod:`seestack.angularsize`).
    angular_size: AngularSize | None = None


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
    field: FrameField | None = None,
) -> ObjectInfo | None:
    """Best-effort identify a target from its ``name`` and/or solved centre.

    Tries, in order: (1) an exact catalog **designation** parsed from the name
    (M/NGC/IC/C + number), (2) an exact **common-name** match, then (3) a tight
    **cone match** against a solved ``ra_deg``/``dec_deg``. Returns ``None`` when
    nothing matches confidently, so the caller shows no card rather than a guess.

    ``field`` is the owner's own single-frame field of view
    (:func:`seestack.framing.frame_field_from_solve`), which decides the "will it
    fit?" verdict and the mosaic panel count. Omitting it falls back to the S50
    field the module has always assumed — right for an install with no solved
    frame to ask, wrong for the owner's S30, which is why every caller that *can*
    answer should.
    """
    cat = catalog if catalog is not None else load_catalog()

    if name:
        want_desig = _norm_designation(name)
        if want_desig is not None:
            for obj in cat:
                if _norm_designation(obj.id) == want_desig:
                    return _to_info(obj, "name", field)
        want_name = _norm_name(name)
        if want_name:
            for obj in cat:
                if obj.name and _norm_name(obj.name) == want_name:
                    return _to_info(obj, "name", field)

    if ra_deg is not None and dec_deg is not None:
        best: CatalogObject | None = None
        best_sep = _CONE_MATCH_DEG
        for obj in cat:
            sep = _angular_sep_deg(ra_deg, dec_deg, obj.ra_deg, obj.dec_deg)
            if sep < best_sep:
                best, best_sep = obj, sep
        if best is not None:
            return _to_info(best, "coords", field)

    return None


#: How close a solved centre must sit to a catalog object before we are willing
#: to put that object's name on a picture the user is about to *share*. Three
#: times tighter than :data:`_CONE_MATCH_DEG`, and deliberately so: showing the
#: wrong "what am I looking at?" card is a bad guess the reader can dismiss;
#: printing the wrong object name into a shared image is a wrong fact that
#: outlives the session. At 0.25° a Seestar field is still centred on the object,
#: while a neighbouring showpiece (Stephan's Quintet beside NGC 7331, ~0.5°) is
#: safely out of reach.
_TITLE_MATCH_DEG = 0.25


def confident_object_title(
    name: str | None,
    ra_deg: float | None = None,
    dec_deg: float | None = None,
    *,
    catalog: tuple[CatalogObject, ...] | None = None,
) -> str | None:
    """A catalog title for a picture whose stored ``name`` says nothing useful.

    A beginner who drops loose FITS in gets a target called ``Unsorted`` or
    ``MyWorks_2026-08-14``, and that folder name is what ends up printed in serif
    under the picture they were about to post. When the plate solve puts the
    field squarely on a catalog object *and the stored name identifies nothing*,
    the catalog's own name is strictly more informative — so this returns it.

    Deliberately conservative, in both directions:

    * If ``name`` already resolves to a catalog object (by designation or common
      name), this returns ``None`` — the user's own words win, and we never
      "correct" ``M 31`` into ``Andromeda Galaxy`` or overrule a name that
      disagrees with the coordinates.
    * The cone is :data:`_TITLE_MATCH_DEG`, not the card's wider
      :data:`_CONE_MATCH_DEG`, because this name gets baked into shared pixels.

    Returns the object's common name, falling back to its designation, or
    ``None`` when there is nothing confident to say.
    """
    if ra_deg is None or dec_deg is None:
        return None
    try:
        ra = float(ra_deg)
        dec = float(dec_deg)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(ra) and math.isfinite(dec)):
        return None

    cat = catalog if catalog is not None else load_catalog()
    if name and identify_object(name, catalog=cat) is not None:
        return None

    best: CatalogObject | None = None
    best_sep = _TITLE_MATCH_DEG
    for obj in cat:
        sep = _angular_sep_deg(ra, dec, obj.ra_deg, obj.dec_deg)
        if sep < best_sep:
            best, best_sep = obj, sep
    if best is None:
        return None
    title = (best.name or "").strip() or (best.id or "").strip()
    return title or None


def _to_info(obj: CatalogObject, matched_by: str,
             field: FrameField | None = None) -> ObjectInfo:
    return ObjectInfo(
        id=obj.id,
        name=obj.name,
        type=obj.type,
        constellation=CONSTELLATION_NAMES.get(obj.con, ""),
        constellation_abbr=obj.con,
        ra_deg=obj.ra_deg,
        dec_deg=obj.dec_deg,
        matched_by=matched_by,
        size_arcmin=obj.size_arcmin,
        framing=framing_hint(obj.size_arcmin, field=field),
        mosaic=mosaic_plan(obj.size_arcmin, obj.size_minor_arcmin, field=field),
        blurb=obj.blurb,
        difficulty=target_difficulty(obj.id, obj.type),
        # The "it fills each sub" clause is the same field-of-view comparison
        # the framing verdict makes, so it reads the same telescope — an S30's
        # 128' frame is not filled by the 80' nebula an S50's 77' one is.
        background_mode_hint=background_mode_hint(
            obj.type, obj.size_arcmin,
            **({"fov_long_arcmin": field.long_arcmin} if field else {})),
        light_travel=light_travel(obj.distance_ly),
        angular_size=angular_size(obj.size_arcmin),
    )
