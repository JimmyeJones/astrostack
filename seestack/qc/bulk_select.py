"""Pick the "worst N%" of a target's subs by one QC metric.

The engine half of the Target page's bulk **"Reject worst … by …"** button. It
exists as a pure function (rather than a sort inline in the router) for one
reason: the ranking is only meaningful *within one patch of sky*.

``star_count``, ``transparency_score`` and ``sky_adu_median`` are properties of
**where the scope pointed** as much as of the night — the same line
:data:`~seestack.qc.grading.PER_POINTING_METRICS` draws for auto-grading. On a
mosaic, one global sort on any of them puts the whole of the panel that frames
the emptiest sky at the bottom of the list, so a user asking to "drop my haziest
10%" quietly loses a tenth of *one panel's coverage* instead — which, unlike a
tenth of a single field's subs, shows in the final picture as a thinner corner.

So for those metrics the worst are taken **per panel**: the same fraction out of
each, which is both what "worst" almost certainly means to the user and the only
choice that keeps a mosaic's coverage even. Everything else is unchanged:

  * FWHM and eccentricity are properties of the seeing, so they keep the one
    target-wide ranking they have always had.
  * A target whose pointings don't split soundly (a single field, an unsolved
    target, a mosaic too tightly packed to separate) keeps the one target-wide
    ranking too — the shared :func:`~seestack.stack.pointings.pointing_groups`
    gate decides, so "panel" means exactly what it means everywhere else.
  * Subs in no substantial panel (an unsolved sub, a thin panel) form their own
    bucket rather than being ranked against a yardstick from another patch of
    sky — they can only honestly be compared with each other.

Pure and read-only: it returns the frames to reject and never touches the DB.
"""

from __future__ import annotations

from seestack.io.project import FrameRow
from seestack.qc.grading import PER_POINTING_METRICS

# A panel needs this many *measured* subs before it can be ranked on its own —
# the same floor the photometric pass and the transparency trend use.
MIN_PANEL_FRAMES = 3

# Metrics where a *higher* value is better, so their "worst" are the lowest.
HIGHER_IS_BETTER: frozenset[str] = frozenset({"star_count", "transparency_score"})


def worst_frames_by_metric(
    frames: list[FrameRow],
    metric: str,
    fraction: float,
    *,
    min_panel_frames: int = MIN_PANEL_FRAMES,
) -> tuple[list[FrameRow], int]:
    """``(frames to reject, panels ranked separately)`` for one bulk cut.

    ``frames`` is the candidate population (the caller's accepted frames);
    rows with no value for ``metric`` are ignored, exactly as before. ``fraction``
    is clamped to ``[0, 1]`` and applied with the same ``int()`` truncation the
    router has always used, so a fraction too small to reach one frame rejects
    nothing.

    The second element is ``0`` whenever the ranking was target-wide (i.e. the
    old behaviour), and otherwise the number of panels ranked separately — the
    caller can say so in its result note.
    """
    measured = [f for f in frames if getattr(f, metric, None) is not None]
    if not measured:
        return [], 0
    fraction = max(0.0, min(1.0, float(fraction)))
    reverse = metric not in HIGHER_IS_BETTER  # higher is worse → worst first

    buckets, n_panels = _buckets(measured, metric, min_panel_frames)

    worst: list[FrameRow] = []
    for bucket in buckets:
        bucket.sort(key=lambda f: getattr(f, metric), reverse=reverse)
        worst.extend(bucket[:int(len(bucket) * fraction)])
    return worst, n_panels


def _buckets(
    measured: list[FrameRow], metric: str, min_panel_frames: int,
) -> tuple[list[list[FrameRow]], int]:
    """Split the measured frames into the populations that may be ranked against
    each other — one bucket (today's target-wide ranking) unless ``metric`` is
    position-dependent *and* the pointings split soundly."""
    if metric not in PER_POINTING_METRICS:
        return [list(measured)], 0

    from seestack.stack.pointings import pointing_groups

    labels = pointing_groups(
        [(f.ra_center_deg, f.dec_center_deg) for f in measured],
        min_members=min_panel_frames,
    )
    if labels is None:
        return [list(measured)], 0

    by_label: dict[int, list[FrameRow]] = {}
    for f, label in zip(measured, labels, strict=True):
        by_label.setdefault(label, []).append(f)
    # ``-1`` is "in no substantial panel" — a bucket of its own, never merged
    # into a panel and never counted as one.
    n_panels = sum(1 for label in by_label if label >= 0)
    return list(by_label.values()), n_panels
