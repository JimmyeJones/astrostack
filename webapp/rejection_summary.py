"""Plain-language "why were some frames left out?" breakdown.

A beginner's stack quietly uses, say, 412 of 500 subs and today they see only
the two counts — never *why* 88 were dropped or whether that's normal. That
silence reads as "something went wrong with my night" when usually it's healthy
(a few satellite trails, some cloud, a couple of soft-focus frames).

This module turns the namespaced ``reject_reason`` tally
(:meth:`seestack.io.project.Project.reject_reason_counts`) into a handful of
friendly buckets, each with a one-line note, plus a single reassuring headline
verdict from the dropped fraction. It is a **pure** function of the counts +
accepted total (no I/O, JSON-safe), so it's trivially unit-tested and the same
mapping can be reused anywhere the counts are known.
"""

from __future__ import annotations

# Ordered bucket definitions. Each raw ``reject_reason`` is matched by the first
# rule (exact string or namespace prefix) that applies; the *order here* is also
# the order buckets are presented to the user (most reassuring / most common
# first). ``auto:grade:<metric>`` splits into "clouds" vs "soft" by which metric
# fired, so a beginner sees the physical cause, not the internal metric name.
# Metric names appear in two forms — the grading attr (``fwhm_px``,
# ``eccentricity_median``, ``sky_adu_median``) and the shorter label form a
# ``qc:``/``bulk:`` reason may carry (``fwhm``, ``eccentricity``) — so match by
# prefix rather than an exact set.
_SOFT_PREFIXES = ("fwhm", "eccentric")
_CLOUD_PREFIXES = ("sky", "star_count", "transparency")


def _metric_bucket(metric: str) -> str | None:
    """Bucket for a grading metric name (either the attr or its label form)."""
    if metric.startswith(_SOFT_PREFIXES):
        return "soft"
    if metric.startswith(_CLOUD_PREFIXES):
        return "clouds"
    return None

# Canonical bucket order + copy. Keep the notes plain-language and non-alarming:
# dropping bad frames is the stacker doing its job, not a failure of the night.
_BUCKETS: list[tuple[str, str, str]] = [
    ("trailed", "Trailed frames (satellites or planes)",
     "A plane or satellite crossed these — leaving them out keeps streaks out "
     "of your picture."),
    ("clouds", "Cloud, haze or moonlight",
     "Fewer stars or a brighter sky than usual — cloud, haze or moonlight got "
     "in the way."),
    ("soft", "Soft or elongated stars",
     "Soft focus, wind or tracking wobble left the stars fuzzy or streaked in "
     "these frames."),
    ("solve_failed", "Couldn't be located in the sky",
     "These frames couldn't be matched to the star field, so they can't be "
     "lined up with the others."),
    ("removed", "You removed these",
     "Frames you rejected by hand."),
    ("error", "Couldn't be read or measured",
     "A problem reading or measuring these frames left them out."),
    ("other", "Left out for other reasons",
     "A few frames were set aside for other reasons."),
]
_BUCKET_ORDER = {key: i for i, (key, _, _) in enumerate(_BUCKETS)}
_BUCKET_META = {key: (label, note) for key, label, note in _BUCKETS}


def _bucket_for(reason: str) -> str:
    """Map one namespaced ``reject_reason`` to a friendly bucket key."""
    if reason in ("auto:streak", "bulk:streaked", "bulk:trailed"):
        return "trailed"
    # qc_error must be checked before the generic "qc:" branch below.
    if reason.startswith("qc_error"):
        return "error"
    if reason.startswith("solve_failed"):
        return "solve_failed"
    if reason == "user":
        return "removed"
    # auto:grade:<metric>, bulk:<worst-metric>, qc:<metric> — split by the
    # physical cause the metric names (soft/seeing vs cloud/transparency).
    if reason.startswith(("auto:grade:", "bulk:", "qc:")):
        metric = reason.split(":")[-1]
        return _metric_bucket(metric) or "other"
    return "other"


def _verdict(dropped: int, used: int) -> dict[str, str]:
    """A single reassuring headline from the dropped fraction."""
    total = dropped + used
    frac = dropped / total if total > 0 else 0.0
    if frac < 0.10:
        return {"tone": "good",
                "text": "This is normal — a healthy night."}
    if frac < 0.30:
        return {"tone": "ok",
                "text": "A few frames didn't make the cut — still a solid stack."}
    return {"tone": "warn",
            "text": "A lot of frames were left out — usually cloud or wind. "
                    "The stack still used all the good ones."}


def summarize_rejections(counts: dict[str, int], n_accepted: int) -> dict:
    """Group a ``reject_reason`` tally into friendly buckets + a verdict.

    ``counts`` is the raw namespaced tally (``{"auto:streak": 12, "user": 3,
    …}``); ``n_accepted`` is how many frames *made* the stack. Returns a
    JSON-safe dict::

        {
          "used": 412, "dropped": 88, "dropped_fraction": 0.176,
          "verdict": {"tone": "ok", "text": "…"},
          "buckets": [{"key","label","count","note"}, …],  # non-zero, ordered
        }

    Buckets with a zero count are omitted; the rest are returned in the canonical
    presentation order. Negative/garbled counts are floored at 0 so a bad row can
    never make the totals lie.
    """
    grouped: dict[str, int] = {}
    for reason, n in counts.items():
        if n <= 0:
            continue
        grouped[_bucket_for(reason)] = grouped.get(_bucket_for(reason), 0) + int(n)

    dropped = sum(grouped.values())
    used = max(0, int(n_accepted))
    buckets = [
        {"key": key,
         "label": _BUCKET_META[key][0],
         "count": grouped[key],
         "note": _BUCKET_META[key][1]}
        for key in sorted(grouped, key=lambda k: _BUCKET_ORDER[k])
    ]
    total = dropped + used
    return {
        "used": used,
        "dropped": dropped,
        "dropped_fraction": round(dropped / total, 4) if total > 0 else 0.0,
        "verdict": _verdict(dropped, used),
        "buckets": buckets,
    }
