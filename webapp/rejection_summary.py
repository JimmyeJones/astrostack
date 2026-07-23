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
    ("unsolved", "Not located in the sky yet",
     "These frames were kept but haven't been matched to the star field yet, "
     "so they can't be added to the stack. Run Plate Solve to include them."),
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


# When a lot of frames drop and ONE actionable cause clearly dominates them, name
# it (and what to do next) instead of the generic "cloud or wind" — the specific
# cause is exactly the thing a beginner can act on before their next session.
# Keyed by bucket; only buckets with a clear, still-reassuring next step get a
# line. "trailed" is already reassuring (the stacker doing its job) and "removed"
# is the user's own choice, while "error"/"other" have no useful advice — those
# fall through to the generic copy.
_DOMINANT_VERDICTS: dict[str, str] = {
    "soft": "A lot of frames were left out — mostly soft or elongated stars this "
            "time. It's worth checking focus (and dew on the lens) before your "
            "next session. The stack still used all the sharp ones.",
    "clouds": "A lot of frames were left out — mostly cloud, haze or moonlight "
              "this time. A clearer, darker night will keep more of them. The "
              "stack still used all the clear ones.",
    "solve_failed": "A lot of frames were left out — mostly ones that couldn't be "
                    "located in the sky. The good ones still stacked; if it keeps "
                    "happening, check your subs aren't trailed or fogged.",
    "unsolved": "A lot of frames were left out — mostly subs that haven't been "
                "located in the sky yet. Run Plate Solve so the rest can be added.",
}


def _verdict(dropped: int, used: int, unsolved: int = 0,
             grouped: dict[str, int] | None = None) -> dict[str, str]:
    """A single reassuring headline from the dropped fraction.

    ``unsolved`` (accepted-but-not-plate-solved frames) is the beginner's one
    *actionable* case — the frames aren't bad, they just haven't been located in
    the sky yet — so when they outnumber what actually stacked, lead with a
    plate-solve nudge rather than the generic "cloud or wind" copy.

    ``grouped`` is the by-bucket dropped tally. On a high-drop night, when one
    actionable bucket clearly dominates (strictly more than half the dropped
    frames), the headline names *that* cause and its fix instead of the vague
    generic — the specific cause is the thing the beginner can act on. A genuinely
    mixed night (no single dominant bucket) keeps the generic reassurance."""
    if unsolved > 0 and unsolved > used:
        return {"tone": "warn",
                "text": "Most of your subs haven't been located in the sky yet, "
                        "so only a few made the stack — it will look noisy. Run "
                        "Plate Solve so the rest can be added."}
    total = dropped + used
    frac = dropped / total if total > 0 else 0.0
    if frac < 0.10:
        return {"tone": "good",
                "text": "This is normal — a healthy night."}
    if frac < 0.30:
        return {"tone": "ok",
                "text": "A few frames didn't make the cut — still a solid stack."}
    # High-drop: if one actionable cause is strictly the majority of the dropped
    # frames, name it. `top * 2 > dropped` guarantees a single dominant bucket (a
    # 50/50 split isn't "dominant" and keeps the generic copy).
    if grouped and dropped > 0:
        top_key, top_n = max(grouped.items(), key=lambda kv: kv[1])
        if top_key in _DOMINANT_VERDICTS and top_n * 2 > dropped:
            return {"tone": "warn", "text": _DOMINANT_VERDICTS[top_key]}
    return {"tone": "warn",
            "text": "A lot of frames were left out — usually cloud or wind. "
                    "The stack still used all the good ones."}


def summarize_rejections(
    counts: dict[str, int], n_accepted: int, n_unsolved: int = 0
) -> dict:
    """Group a ``reject_reason`` tally into friendly buckets + a verdict.

    ``counts`` is the raw namespaced tally (``{"auto:streak": 12, "user": 3,
    …}``, all from *rejected* frames); ``n_accepted`` is how many frames are
    accepted. ``n_unsolved`` is how many of those accepted frames have **not
    plate-solved yet** — they are kept but never reach the stacker (which
    combines only accepted+solved frames), so they must be counted as *left out*,
    not *used*, or a beginner is told a thin/gibberish stack was a "healthy
    night". Returns a JSON-safe dict::

        {
          "used": 412, "dropped": 88, "dropped_fraction": 0.176,
          "verdict": {"tone": "ok", "text": "…"},
          "buckets": [{"key","label","count","note"}, …],  # non-zero, ordered
        }

    Here ``used`` is accepted **and** solved (what actually stacks), and
    ``dropped`` includes both rejected frames and unsolved-accepted ones.
    Buckets with a zero count are omitted; the rest are returned in the canonical
    presentation order. Negative/garbled counts are floored at 0 so a bad row can
    never make the totals lie.
    """
    grouped: dict[str, int] = {}
    for reason, n in counts.items():
        if n <= 0:
            continue
        grouped[_bucket_for(reason)] = grouped.get(_bucket_for(reason), 0) + int(n)

    # Accepted-but-unsolved subs never reach the stack — surface them as their
    # own bucket and remove them from "used" so the accounting is honest.
    n_unsolved = max(0, int(n_unsolved))
    if n_unsolved > 0:
        grouped["unsolved"] = grouped.get("unsolved", 0) + n_unsolved

    dropped = sum(grouped.values())
    used = max(0, int(n_accepted) - n_unsolved)
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
        "verdict": _verdict(dropped, used, n_unsolved, grouped),
        "buckets": buckets,
    }
