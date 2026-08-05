"""Which per-frame background-flatten mode suits *this* target?

``StackOptions.background_mode`` defaults to ``per_channel``, which fits a sky
model separately in R, G and B. That is the right answer for star fields and
small targets — light pollution is warm-coloured, so the three channels really
do carry different gradients. It is the *wrong* answer for a big emission
nebula: there the nebula's own morphology differs across channels, so each
channel's fit bends into the nebulosity by a different amount and the result
carries cyan cores, red halos and black "holes"
(:mod:`seestack.bg.per_frame` spells this out). ``luminance`` mode fits one
shared shape and subtracts it equally from all three, so colour survives.

The knob is documented, but a beginner has no way to know their target is one of
the ones that needs it. This module answers that from the **bundled offline
catalog** alone — the object's plain-language type and its major-axis size, both
of which :func:`seestack.objectinfo.identify_object` already resolves without a
network call or a classifier over pixel data.

Deliberately conservative: it advises only when the catalog says the target is
extended emission *and* records a size big enough to matter, and it never
advises anything but a suggestion (``per_channel`` stays the default; a wrong
guess costs one click). Unknown type, unknown size or a small object → ``None``,
and no nudge is shown at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from seestack.framing import SEESTAR_FOV_LONG_ARCMIN

# Catalog ``type`` values whose objects are *extended emission*: a diffuse glow
# spread across the frame whose shape differs between R, G and B. Emission and
# reflection nebulae both live under the bundled catalogs' bare "nebula", and a
# supernova remnant (Veil, Crab) is the same optically — filamentary Hα/OIII
# structure with wildly different per-channel morphology.
#
# Deliberately NOT included: "planetary nebula" (compact — a few arcmin at most,
# so it behaves like a point source against the sky fit), clusters, galaxies and
# star clouds. A galaxy is extended but its channels share one shape, which is
# exactly the case per-channel mode handles correctly.
EXTENDED_EMISSION_TYPES = frozenset({"nebula", "supernova remnant"})

# Below this major-axis size an extended-emission object is small enough,
# relative to the Seestar frame (77' × 44'), that the sky fit has plenty of
# genuine sky around it in every channel and per-channel mode is not at risk.
# 15' is about a fifth of the frame's long edge — comfortably inside a corner of
# it — and sits below every catalog nebula the advice is meant to catch.
MIN_EXTENDED_ARCMIN = 15.0


@dataclass(frozen=True)
class BackgroundModeHint:
    """A suggested per-frame background-flatten mode, with the reason to show.

    ``mode`` is the ``StackOptions.background_mode`` value being recommended, so
    a caller can wire a one-click fix to it without re-deriving anything.
    ``text`` is the ready-to-render beginner sentence; it never names the target
    (the caller already knows which one it is).
    """

    mode: str    # a StackOptions.background_mode value — "luminance" today
    text: str


def background_mode_hint(
    object_type: str | None,
    size_arcmin: float | None,
    *,
    fov_long_arcmin: float = SEESTAR_FOV_LONG_ARCMIN,
) -> BackgroundModeHint | None:
    """Advise a background-flatten mode for a target of this type and size.

    Returns ``None`` — meaning "the default is fine, say nothing" — unless the
    catalog type is extended emission (:data:`EXTENDED_EMISSION_TYPES`) *and* a
    size of at least :data:`MIN_EXTENDED_ARCMIN` is known. Never guesses from a
    missing size.

    An object bigger than a single Seestar frame fills every sub, so even the
    shared luminance model can absorb some of its faint outer glow — that case
    gets one extra honest sentence pointing at the box-size knob, rather than a
    different recommendation (turning the flatten off entirely costs the biggest
    noise win in the pipeline, so it is not something to nudge a beginner into).
    """
    if object_type is None or size_arcmin is None:
        return None
    if object_type.strip().lower() not in EXTENDED_EMISSION_TYPES:
        return None
    if size_arcmin < MIN_EXTENDED_ARCMIN:
        return None

    text = (
        "This target is a large patch of glowing gas, and it looks different in "
        "red, green and blue. Flattening each colour separately — the default — "
        "can bend each colour's sky model into the nebula by a different amount, "
        "which leaves cyan cores and red halos in the finished picture. "
        "Luminance mode fits one shared sky model and subtracts it equally from "
        "all three colours, so the nebula keeps its colour."
    )
    if size_arcmin > fov_long_arcmin:
        text += (
            " It's also bigger than a single Seestar frame, so it fills each sub "
            "— if its faint outer glow looks eaten away, raise the Background box "
            "size so the sky model stays gentler than the nebula."
        )
    return BackgroundModeHint("luminance", text)
