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

from seestack.io.project import REJECT_REASON_FILE_MISSING
from seestack.solve.astap import SOLVE_FAILED_TIMEOUT

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
    ("solve_timeout", "Ran out of time being located",
     "The star-matcher tried every strategy on these and ran out of time before "
     "it found a match — often a hazy or star-poor sub. They'll be tried again "
     "on the next scan; if it keeps happening, raise the ASTAP timeout in "
     "Settings and run Plate Solve again."),
    ("removed", "You removed these",
     "Frames you rejected by hand."),
    ("missing", "Their files aren't on your disk any more",
     "You told AstroStack these subs are gone, so it carries on without them. "
     "Nothing was deleted by the app — and if the files ever turn up again, "
     "they go straight back into the stack."),
    ("error", "Couldn't be read or measured",
     "These files couldn't be read (they may be corrupt or were still "
     "downloading), so they're skipped. The rest are fine."),
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
        # "ran out of time" is the one solve failure with an obvious fix, so it
        # gets its own bucket and advice rather than the generic "couldn't be
        # matched to the star field".
        return ("solve_timeout"
                if reason == f"solve_failed:{SOLVE_FAILED_TIMEOUT}"
                else "solve_failed")
    if reason == "user":
        return "removed"
    if reason == REJECT_REASON_FILE_MISSING:
        # The owner's own "those subs are gone, carry on without them". Its own
        # bucket rather than the vague "other", because it is a thing he *did*
        # and the one bucket where the reassurance ("the app deleted nothing")
        # is the whole point.
        return "missing"
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
    "solve_timeout": "A lot of frames were left out — mostly subs the star-matcher "
                     "ran out of time on. They'll be tried again on the next scan; "
                     "if it keeps happening, raise the ASTAP timeout in Settings "
                     "and run Plate Solve again.",
}


def _verdict(dropped: int, used: int, unsolved: int = 0,
             grouped: dict[str, int] | None = None,
             solve_timeout: int = 0) -> dict[str, str]:
    """A single reassuring headline from the dropped fraction.

    ``unsolved`` (accepted-but-not-plate-solved frames) is the beginner's one
    *actionable* case — the frames aren't bad, they just haven't been located in
    the sky yet — so when they outnumber what actually stacked, lead with a
    plate-solve nudge rather than the generic "cloud or wind" copy.
    ``solve_timeout`` is the same shape one step along: those subs *were* offered
    to the solver, repeatedly, and it ran out of time — so re-running Plate Solve
    alone would burn the same minutes again. When they dominate, name the knob
    that would actually rescue them. Checked after the plate-solve nudge, which
    is the cheaper fix, and inert (byte-for-byte today's wording) at 0.

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
    if solve_timeout > 0 and solve_timeout > used:
        return {"tone": "warn",
                "text": "Most of your subs ran out of time being located in the "
                        "sky, so only a few made the stack. Raise the ASTAP "
                        "timeout in Settings and run Plate Solve again."}
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
    counts: dict[str, int], n_accepted: int, n_unsolved: int = 0,
    n_unreadable: int = 0, n_solve_timeout: int = 0,
) -> dict:
    """Group a ``reject_reason`` tally into friendly buckets + a verdict.

    ``counts`` is the raw namespaced tally (``{"auto:streak": 12, "user": 3,
    …}``, all from *rejected* frames); ``n_accepted`` is how many frames are
    accepted. ``n_unsolved`` is how many of those accepted frames have **not
    plate-solved yet** — they are kept but never reach the stacker (which
    combines only accepted+solved frames), so they must be counted as *left out*,
    not *used*, or a beginner is told a thin/gibberish stack was a "healthy
    night". ``n_unreadable`` is the *subset* of those unsolved subs that failed
    QC entirely (unreadable/corrupt/truncated FITS, a ``qc_error`` reason left
    ``accept=1``): they never stack for a different reason — they couldn't be
    *read*, not merely located — so they're attributed to the "couldn't be read"
    bucket and excluded from the plate-solve nudge (telling a beginner to
    plate-solve a corrupt file is wrong advice). ``n_solve_timeout`` is the other
    such subset: subs the solver *did* try, on every rung of its ladder, until it
    ran out of time (the canonical ``solve_failed:solve timed out`` reason). They
    are not "not located yet" — re-running Plate Solve without giving the solver
    longer just spends the same minutes again — so they get their own bucket and
    their own advice. The two subsets are disjoint by construction (a
    ``qc_error`` frame's reason is never overwritten by a solve failure) and are
    clamped into ``n_unsolved`` defensively. Returns a JSON-safe dict::

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
    # own bucket and remove them from "used" so the accounting is honest. Of
    # those, the ones that couldn't even be read (``n_unreadable``, a subset) are
    # a *different* cause: attribute them to the "couldn't be read" error bucket
    # rather than "not located yet", so the plate-solve nudge never fires on a
    # corrupt file. Clamp the subset defensively so a bad count can't make the
    # located-pending tally go negative.
    n_unsolved = max(0, int(n_unsolved))
    n_unreadable = min(max(0, int(n_unreadable)), n_unsolved)
    n_solve_timeout = min(max(0, int(n_solve_timeout)), n_unsolved - n_unreadable)
    n_located_pending = n_unsolved - n_unreadable - n_solve_timeout
    if n_located_pending > 0:
        grouped["unsolved"] = grouped.get("unsolved", 0) + n_located_pending
    if n_unreadable > 0:
        grouped["error"] = grouped.get("error", 0) + n_unreadable
    if n_solve_timeout > 0:
        grouped["solve_timeout"] = grouped.get("solve_timeout", 0) + n_solve_timeout

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
        "verdict": _verdict(dropped, used, n_located_pending, grouped,
                            n_solve_timeout),
        "buckets": buckets,
    }
