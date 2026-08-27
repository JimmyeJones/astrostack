"""One definition of "how did this picture actually catch its target?".

Two surfaces ask the same question of a finished stack, and they must answer it
in one voice:

- the **History / Target card** of a finished picture, which reads the verdict
  the morning after ("M 31 is running off the left edge — next time, nudge your
  Seestar about 1.0° south…"), via
  ``GET /api/targets/{safe}/stack-runs/{id}/framing``;
- the **night planner**, which repeats the *nudge* half of that on the row for a
  target the user already owns — because the one moment the advice is worth
  anything is while they are standing outside pointing the scope, and by then the
  card they read yesterday is long forgotten.

The verdict itself is pure geometry in :mod:`seestack.framing`; what lives here
is the read that feeds it — the run's own solved output WCS, the catalog object's
position and size — so neither surface grows its own idea of "which way".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def framing_payload(fits_path: str | None, info) -> dict[str, Any] | None:  # noqa: ANN001
    """The full "did I frame it well?" answer for one finished stack, or ``None``.

    ``info`` is the catalog match for the target (an
    :func:`seestack.objectinfo.identify_object` result); the caller has already
    established it is not ``None`` and carries a vetted ``size_arcmin``.

    ``None`` — never a guess — when the run has no FITS, no usable celestial WCS,
    no measurable plate scale, or the object's position can't be projected onto
    the canvas. Reads a FITS header, so callers on the request path run it in a
    threadpool.
    """
    if not fits_path or info is None or info.size_arcmin is None:
        return None
    from seestack.framing import (
        framing_result_verdict,
        recentre_nudge,
        recentre_outcome,
    )
    from seestack.io.wcs_io import arcsec_per_px, celestial_wcs_from_fits

    wcs, width, height = celestial_wcs_from_fits(fits_path)
    if wcs is None:
        return None
    try:
        xs, ys = wcs.world_to_pixel_values(info.ra_deg, info.dec_deg)
        x_px, y_px = float(xs), float(ys)
    except Exception:  # noqa: BLE001 — a degenerate WCS just means "no verdict"
        return None
    # Where this picture's middle actually pointed, so "re-centre it" can name
    # a direction. Read from the same WCS, in sky coordinates — which is why
    # it survives a rotated canvas without any orientation guesswork.
    try:
        cra, cdec = wcs.all_pix2world((width - 1) / 2.0, (height - 1) / 2.0, 0)
        centre_ra, centre_dec = float(cra), float(cdec)
    except Exception:  # noqa: BLE001 — no centre means no nudge, not no verdict
        centre_ra = centre_dec = float("nan")
    scale = arcsec_per_px(wcs)
    if scale is None:
        return None
    v = framing_result_verdict(
        x_px=x_px, y_px=y_px, width_px=width, height_px=height,
        arcsec_per_px=scale, size_arcmin=info.size_arcmin,
    )
    if v is None:
        return None
    # "Re-centre this picture": the crop that would bring an off-centre object
    # back to the middle, offered only when the verdict is exactly that — a
    # clipped or oversized object can't be helped by cropping, and a centred
    # one has nothing to gain. The engine refuses on its own terms too
    # (too destructive, or too cramped around the object), so this is `null`
    # far more often than it isn't. An offer, never an automatic change.
    outcome = recentre_outcome(
        x_px=x_px, y_px=y_px, width_px=width, height_px=height,
        arcsec_per_px=scale, size_arcmin=info.size_arcmin,
    ) if v.level == "off_centre" else None
    rc = outcome.crop if outcome else None
    # "Re-centre it next session" is advice a beginner can't act on without
    # knowing *which way*. Offered only for the two verdicts whose fix really
    # is a better pointing — a well-centred picture needs nothing, and an
    # object bigger than the frame needs mosaic mode, not a nudge.
    nudge = recentre_nudge(
        centre_ra_deg=centre_ra, centre_dec_deg=centre_dec,
        object_ra_deg=info.ra_deg, object_dec_deg=info.dec_deg,
    ) if v.level in ("off_centre", "clipped") else None
    return {
        "level": v.level,
        "text": v.text,
        "coverage": v.coverage,
        "off_centre": v.off_centre,
        # Which way, and how far, to move the mount so it lands in the middle
        # next time. `null` when the correction is too small to act on, or the
        # verdict isn't one a re-point fixes.
        "nudge": None if nudge is None else {
            "direction": nudge.direction,
            "degrees": nudge.degrees,
            "text": nudge.text,
            # The same move as a chip-sized phrase, for a surface with no room
            # for the sentence (the night planner's target row).
            "short": nudge.short,
        },
        # Fractional (0..1) crop bounds in the editor's own `geometry.crop`
        # convention, plus the fraction of the frame it keeps.
        "recentre": None if rc is None else {
            "x0": rc.x0, "y0": rc.y0, "x1": rc.x1, "y1": rc.y1, "kept": rc.kept,
        },
        # Why there is no offer, when the verdict said "off to one side" but
        # cropping can't help. Present so the *worst*-framed pictures don't
        # get less help than the mildly off-centre ones: the caller can say
        # "cropping back to the middle would leave only about a fifth of the
        # picture" instead of going quiet. `kept` is what that crop would have
        # kept (0–1), and is only meaningful for `too_destructive`.
        "recentre_refused": None if (outcome is None or rc is not None) else {
            "reason": outcome.reason, "kept": outcome.kept,
        },
        # The name the sentence is prefixed with, so one voice covers this
        # card and the pre-shoot "will it fit?" hint.
        "object_name": info.name or info.id,
        "size_arcmin": info.size_arcmin,
    }


def newest_picture_nudge(proj, info):  # noqa: ANN001, ANN201
    """The "nudge it this way before you start" advice from a target's **newest**
    finished picture, as a :class:`~seestack.framing.RecentreNudge`, or ``None``.

    Deliberately the newest run only: a verdict from three sessions ago could
    contradict a re-pointed one, and the planner must never tell someone to move
    a scope they have already moved. ``None`` — and so a silent row — whenever
    the target has no stacked picture with a readable master, the object isn't
    confidently identified, or its framing needs no correction.

    Reads a FITS header, so a caller on the request path should keep it behind a
    cache or a threadpool.
    """
    if info is None or info.size_arcmin is None:
        return None
    from seestack.framing import RecentreNudge

    try:
        runs = list(proj.iter_stack_runs())
    except Exception:  # noqa: BLE001 — a broken project simply gets no advice
        return None
    # `iter_stack_runs` is newest-first; take the first run that still has a
    # master on disk, so a purged/moved newest run falls back rather than
    # silencing the target entirely.
    for run in runs:
        if not run.fits_path or not Path(run.fits_path).exists():
            continue
        try:
            payload = framing_payload(run.fits_path, info)
        except Exception:  # noqa: BLE001 — an unreadable master is "no advice"
            return None
        if payload is None:
            return None
        n = payload.get("nudge")
        if n is None:
            return None
        return RecentreNudge(n["direction"], n["degrees"], n["text"],
                             n.get("short", ""))
    return None
