"""How hard is this target for a Seestar? — a plain-language expectation-setter.

A very common beginner disappointment is pointing a Seestar at a faint, spread-out
object (M33, the North America Nebula, the California Nebula), getting a dim, noisy
result after one short session, and concluding the app is broken — when in truth
that object is simply *hard* from a backyard and needs a dark sky and several hours,
while a bright galaxy or a star cluster looks great in twenty minutes. Nothing else
tells the beginner this *before* they're let down: the framing hint answers "will it
fit?", the readiness card answers "have I shot enough?", but neither says "is this
one easy or hard to begin with?".

This module answers that from the bundled catalog alone: pure, offline, no
dependency. It returns one of three friendly buckets — **easy / moderate /
challenging** — plus one honest, encouraging sentence, or ``None`` when the object
isn't one we've vetted (we never guess: absent a vetted verdict, no badge).

Why a curated table rather than a formula: the catalog stores ``type`` and
``size_arcmin`` but **no magnitude or surface brightness**, and those are exactly
what decides difficulty — a bright compact galaxy (M31) and a large faint one (M33)
share a type and dwarf each other in size, yet sit at opposite ends of "hard for a
Seestar". So we hand-curate the well-known galaxies, nebulae, planetary nebulae and
supernova remnants (the objects where difficulty genuinely varies) and lean on one
reliable *type* rule for the rest: **star clusters and star fields are uniformly
easy** — they're bright point sources that need no integration to look good — so any
open/globular cluster, star cloud, asterism or double star reads "easy" without
per-object curation. Everything not covered by either self-hides.

The verdicts follow well-established Seestar-community consensus for an OSC (no
filters) imager and deliberately bias *conservative*: when a call is borderline we
pick the harder bucket, because a beginner pleasantly surprised is far better than
one who was promised "easy" and got noise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Object types that are reliably *easy* for a Seestar whatever the individual object:
# bright, high-surface-brightness point sources (or fields of them) that resolve into
# a pleasing picture in well under an hour with no dark sky needed. Matched
# case-insensitively against the catalog ``type`` string.
_EASY_TYPES: frozenset[str] = frozenset(
    {"globular cluster", "open cluster", "star cloud", "asterism", "double star"}
)

# Hand-curated difficulty for the objects where it genuinely varies (galaxies,
# emission/reflection nebulae, planetary nebulae, supernova remnants). Keyed by the
# object's catalog id in a normalised form (uppercase, no spaces/underscores, e.g.
# "NGC 7000" -> "NGC7000"). Levels: "easy" | "moderate" | "challenging". Objects not
# listed here (and not covered by the easy-type rule) get no badge, so the table can
# grow over time without ever forcing a guess. Verdicts are for an OSC Seestar with
# no filters, biased conservative on borderline diffuse nebulae.
_CURATED: dict[str, str] = {
    # --- Galaxies -----------------------------------------------------------
    "M31": "easy",          # Andromeda — bright core, the classic first galaxy
    "M32": "moderate",      # small elliptical companion to M31
    "M33": "challenging",   # Triangulum — the classic low-surface-brightness trap
    "M49": "moderate",
    "M51": "moderate",      # Whirlpool
    "M58": "moderate",
    "M59": "moderate",
    "M60": "moderate",
    "M61": "moderate",
    "M63": "moderate",      # Sunflower
    "M64": "moderate",      # Black Eye
    "M65": "moderate",      # Leo Triplet
    "M66": "moderate",
    "M74": "challenging",   # Phantom — famously faint
    "M77": "moderate",
    "M81": "easy",          # Bode's — bright
    "M82": "easy",          # Cigar — high surface brightness
    "M83": "moderate",      # Southern Pinwheel
    "M84": "moderate",
    "M85": "moderate",
    "M86": "moderate",
    "M87": "moderate",      # Virgo A
    "M88": "moderate",
    "M89": "moderate",
    "M90": "moderate",
    "M91": "challenging",   # faint barred spiral
    "M94": "moderate",
    "M95": "moderate",
    "M96": "moderate",
    "M98": "challenging",   # faint edge-on
    "M99": "moderate",
    "M100": "moderate",
    "M101": "challenging",  # Pinwheel — large, low surface brightness
    "M102": "moderate",     # Spindle
    "M104": "easy",         # Sombrero — bright, high surface brightness
    "M105": "moderate",
    "M106": "moderate",
    "M108": "challenging",  # faint edge-on
    "M109": "challenging",  # faint barred spiral
    "M110": "moderate",     # M31 companion
    "NGC253": "easy",       # Sculptor — bright
    "NGC5128": "moderate",  # Centaurus A — bright but low for most observers
    "NGC4565": "moderate",  # Needle — edge-on
    "NGC891": "challenging",  # Silver Sliver — faint edge-on with dust lane
    "NGC7331": "moderate",  # Deer Lick
    "NGC4631": "moderate",  # Whale
    "NGC2903": "moderate",
    "NGC2403": "moderate",
    "NGC3628": "moderate",  # Hamburger
    "NGC4449": "moderate",
    "NGC4038": "challenging",  # Antennae — small, faint interacting pair
    # --- Emission / reflection nebulae & supernova remnants -----------------
    "M1": "moderate",       # Crab (SNR)
    "M8": "easy",           # Lagoon — bright
    "M16": "moderate",      # Eagle
    "M17": "easy",          # Omega — one of the brightest
    "M20": "moderate",      # Trifid
    "M42": "easy",          # Orion — the best beginner nebula
    "M43": "easy",          # De Mairan's, part of the Orion complex
    "M78": "moderate",      # reflection nebula
    "NGC7000": "challenging",   # North America — large, low surface brightness
    "IC5070": "challenging",    # Pelican
    "IC1805": "challenging",    # Heart — Ha-dominated, hard in OSC
    "IC1848": "challenging",    # Soul
    "NGC2244": "challenging",   # Rosette — faint nebulosity in OSC
    "NGC7380": "challenging",   # Wizard
    "NGC281": "challenging",    # Pacman
    "NGC1499": "challenging",   # California — famously low surface brightness
    "NGC6888": "challenging",   # Crescent
    "NGC7635": "challenging",   # Bubble
    "NGC2359": "challenging",   # Thor's Helmet
    "IC1396": "challenging",    # Elephant's Trunk
    "IC405": "challenging",     # Flaming Star
    "IC434": "challenging",     # Horsehead — very hard in OSC
    "NGC2024": "moderate",      # Flame — brighter, next to Alnitak
    "NGC2174": "challenging",   # Monkey Head
    "IC443": "challenging",     # Jellyfish (SNR)
    "IC2177": "challenging",    # Seagull
    "NGC6960": "challenging",   # Veil (Witch's Broom) — faint without OIII
    "NGC6992": "challenging",   # Eastern Veil
    "NGC7023": "moderate",      # Iris
    "IC5146": "challenging",    # Cocoon
    "NGC2264": "moderate",      # Christmas Tree cluster & Cone
    "NGC3372": "easy",          # Carina — very bright where it's up
    # --- Planetary nebulae --------------------------------------------------
    "M27": "easy",          # Dumbbell — bright, large
    "M57": "easy",          # Ring — bright, iconic
    "M76": "moderate",      # Little Dumbbell — fainter
    "M97": "moderate",      # Owl — fainter
    "NGC7293": "challenging",   # Helix — large, low surface brightness
    "NGC7662": "easy",      # Blue Snowball — small, bright
    "NGC6543": "easy",      # Cat's Eye — small, bright
    "NGC40": "moderate",    # Bow-Tie
    "NGC246": "challenging",    # Skull — faint
    "NGC3242": "easy",      # Ghost of Jupiter — small, bright
}

# The plain, honest, encouraging sentence per bucket. Deliberately name no object
# (the caller has the name); each is one self-contained beginner sentence.
_SENTENCES: dict[str, str] = {
    "easy": (
        "Bright and rewarding — a great target to start with. It usually looks "
        "good in well under an hour."
    ),
    "moderate": (
        "A middle-of-the-road target — give it a couple of hours of subs for a "
        "clean, detailed result."
    ),
    "challenging": (
        "Faint and low-contrast — it rewards a darker sky and several hours. From "
        "a bright suburb it stays dim and noisy, so don't be discouraged if an "
        "early result looks weak."
    ),
}

# Human-friendly one-word label per bucket, for a badge.
_LABELS: dict[str, str] = {
    "easy": "Easy",
    "moderate": "Moderate",
    "challenging": "Challenging",
}


@dataclass(frozen=True)
class DifficultyHint:
    """A plain-language "how hard is this for a Seestar?" verdict for a target.

    ``level`` is a stable machine token the UI can style on ("easy" | "moderate" |
    "challenging"); ``label`` is the one-word badge text ("Easy"…); ``text`` is the
    ready-to-render beginner sentence (self-contained — it names no object).
    """

    level: str
    label: str
    text: str


def _norm_id(object_id: str) -> str:
    """Normalise a catalog id for lookup: uppercase, alphanumerics only.

    ``"NGC 7000"`` -> ``"NGC7000"``, ``"M_31"`` -> ``"M31"``. Mirrors how the rest
    of the catalog code loosens designations so a space/underscore never misses.
    """
    return re.sub(r"[^A-Z0-9]", "", object_id.upper())


def target_difficulty(
    object_id: str,
    object_type: str | None,
) -> DifficultyHint | None:
    """Verdict on how hard ``object_id`` is to image well with a Seestar.

    Resolution order: (1) the hand-curated table for the objects where difficulty
    genuinely varies (galaxies, nebulae, planetary nebulae, SNRs); (2) the reliable
    "star clusters and star fields are easy" type rule; (3) ``None`` — no badge,
    so an un-vetted object never gets a guessed verdict.
    """
    level = _CURATED.get(_norm_id(object_id))
    if level is None:
        t = (object_type or "").strip().lower()
        if t in _EASY_TYPES:
            level = "easy"
    if level is None:
        return None
    return DifficultyHint(level=level, label=_LABELS[level], text=_SENTENCES[level])
