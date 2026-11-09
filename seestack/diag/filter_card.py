"""Does the Seestar say in each sub whether its light-pollution filter was in?

The S30 has a one-tap LP filter. On an emission nebula it is what pulls the
glow out of a suburban sky; on a galaxy or a star cluster it throws away most
of the light. A beginner flips it by habit, and nothing in the app tells him
which nights had it in. The backlog idea that would ("Was the light-pollution
filter on?", Scout 2026-11-01) is gated on one fact only his subs can give:
**does the camera write a filter card at all, and with which values?** If it
writes none, the idea is dropped.

**Method.** A sample of subs — a few per target, spread over as many nights as
the target has — has its FITS header read (header only, read-only; the pixels
are never opened). For each sub it records:

* the value of the standard ``FILTER`` card, as a short *token*
  (:func:`_token`) — or that the card is absent or blank;
* the names (never the values) of any other card whose name says "filter",
  in case the Seestar uses its own keyword.

and tallies them over subs, targets, nights and the catalogue family of each
target (galaxy / nebula / cluster). It also counts nights on which one target's
subs carry **more than one** value — the per-night tally the idea would show
only makes sense if the filter does not change within a night.

**Privacy.** A filter card holds an equipment word ("LP", "IRCUT"), not
anything about the person, but the contract (:mod:`seestack.diag`) forbids
header values in general, so a value is reported only when it is a short,
plain word that cannot be a path, a coordinate or a serial (:func:`_token`);
anything else is counted under ``other_values`` without its text.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from seestack.diag import Diagnostic, DiagnosticStopped, check_result_is_safe

#: Subs read per target, and in all. A header read is cheap (one block), so
#: this is about the single worker's time on a NAS, not memory.
SUBS_PER_TARGET = 8
MAX_SUBS = 800

#: A value is reported as itself only if it is a short plain word: letters,
#: digits, space, ``+ - _ . /`` and at most three digits in a row (so a serial
#: number or a date can never come through), and it passes the package's own
#: path/location check.
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 +._/-]{0,11}$")
_LONG_DIGITS = re.compile(r"\d{4,}")
#: Card *names* reported: FITS keywords are at most eight such characters.
_KEYWORD = re.compile(r"^[A-Z0-9_-]{1,8}$")


def _token(value: Any) -> str | None:
    """The filter value as a safe, normalised token, ``"(blank)"`` for an
    empty card, or ``None`` when it is not a plain word (counted, not shown)."""
    if isinstance(value, bool):
        return "(true)" if value else "(false)"
    text = str(value).strip()
    if not text:
        return "(blank)"
    if not _TOKEN.match(text) or _LONG_DIGITS.search(text):
        return None
    try:
        check_result_is_safe(text)
    except ValueError:
        return None
    return text


def _filter_like_keys(header: Any) -> list[str]:
    out = []
    for key in header:  # astropy Header iterates keywords
        k = str(key).strip().upper()
        if k == "FILTER" or not _KEYWORD.match(k):
            continue
        if "FILT" in k or k.startswith("LP") or k in ("IRCUT", "UVIR"):
            out.append(k)
    return sorted(set(out))


def _frame_path(f: Any) -> str | None:
    for p in (getattr(f, "cached_path", None), getattr(f, "source_path", None)):
        if p and Path(p).exists():
            return p
    return None


def _sample(frames: list[Any], k: int) -> list[tuple[Any, int]]:
    """Up to ``k`` ``(frame, night number)`` pairs for one target.

    A "night" is one capture session — subs no more than
    :data:`seestack.session_recap.DEFAULT_SESSION_GAP_HOURS` apart, split the
    way every night-shaped screen splits them — numbered oldest first.

    Two properties v1 lacked, both needed for the answer to mean anything on
    the owner's targets, which run to hundreds of nights:

    * **Nights spread over the whole history**, not the oldest few — a firmware
      update that started writing the card would otherwise be invisible.
    * **Two subs per night, its first and its last**, so a filter flipped
      partway through a night shows up as two values. With one sub per night
      the within-night check could only ever read zero.

    When a target has fewer nights than the budget allows, the rest of the
    budget goes to subs spread through the nights already chosen, then to the
    newest of the nights not chosen."""
    from seestack.session_recap import (
        DEFAULT_SESSION_GAP_HOURS,
        _split_sessions,
        parse_capture_time,
    )

    timed = sorted(((dt, i, f) for i, f in enumerate(frames)
                    if (dt := parse_capture_time(f.timestamp_utc)) is not None),
                   key=lambda t: (t[0], t[1]))
    sessions = [[f for _, _, f in s] for s in
                _split_sessions(timed, DEFAULT_SESSION_GAP_HOURS)]
    undated = [f for f in frames if parse_capture_time(f.timestamp_utc) is None]
    if undated:
        sessions.append(undated)  # one pseudo-night; still sampled, never merged
    if not sessions or k <= 0:
        return []
    n_pick = min(len(sessions), max(1, k // 2))
    if n_pick == 1:
        idx = [len(sessions) - 1] if len(sessions) > 1 else [0]
    else:
        idx = sorted({round(j * (len(sessions) - 1) / (n_pick - 1)) for j in range(n_pick)})
    out: list[tuple[Any, int]] = []
    rest: list[list[Any]] = []
    for si in idx:
        s = sessions[si]
        ends = [s[0], s[-1]] if len(s) > 1 else [s[0]]
        out.extend((f, si) for f in ends)
        middle = s[1:-1]
        # Interior subs, centre first then outward, for any spare budget.
        order = sorted(range(len(middle)), key=lambda m: abs(m - (len(middle) - 1) / 2))
        rest.append([middle[m] for m in order])
    out = out[:k]
    i = 0
    while len(out) < k and any(rest):
        q = rest[i % len(rest)]
        if q:
            out.append((q.pop(0), idx[i % len(rest)]))
        i += 1
    # Still short (the chosen nights were one sub each): the last sub of the
    # nights not chosen, newest first.
    for si in reversed(range(len(sessions))):
        if len(out) >= k:
            break
        if si not in idx:
            out.append((sessions[si][-1], si))
    return out


def _family(entry: Any) -> str:
    try:
        from seestack.edit.presets import catalog_family
        from seestack.objectinfo import identify_object

        info = identify_object(entry.name, entry.ra_deg, entry.dec_deg)
        fam = catalog_family(info.type) if info is not None else None
    except Exception:  # noqa: BLE001 — identification is best-effort
        fam = None
    return fam or "unidentified"


def _bump(table: dict[str, dict[str, Any]], key: str, target: str, night: str,
          family: str) -> None:
    row = table.setdefault(key, {"subs": 0, "_t": set(), "_n": set(), "by_family": {}})
    row["subs"] += 1
    row["_t"].add(target)
    row["_n"].add(night)
    row["by_family"][family] = row["by_family"].get(family, 0) + 1


def _finish(table: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {k: {"subs": r["subs"], "targets": len(r["_t"]), "nights": len(r["_n"]),
                "by_family": dict(sorted(r["by_family"].items()))}
            for k, r in sorted(table.items())}


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    """Tally the sampled subs' filter cards. Reads headers only."""
    from astropy.io import fits

    plan: list[tuple[str, str, Any, int]] = []   # (target, family, frame, night no.)
    for entry in library.list_targets():
        try:
            proj = library.open_target(entry.safe_name)
        except Exception:  # noqa: BLE001 — a broken target is skipped
            continue
        try:
            frames = list(proj.iter_frames())
        finally:
            proj.close()
        if not frames:
            continue
        fam = _family(entry)
        plan.extend((entry.safe_name, fam, f, night_no)
                    for f, night_no in _sample(frames, SUBS_PER_TARGET))
    plan = plan[:MAX_SUBS]

    values: dict[str, dict[str, Any]] = {}
    keys: dict[str, dict[str, Any]] = {}
    other = {"subs": 0, "_distinct": set()}
    per_night: dict[tuple[str, int], list[str]] = {}
    unreadable = 0
    targets: set[str] = set()
    nights: set[str] = set()
    for i, (target, fam, f, night_no) in enumerate(plan):
        if should_stop is not None and should_stop():
            raise DiagnosticStopped("stopped")
        if progress is not None:
            progress("reading headers", i + 1, len(plan))
        path = _frame_path(f)
        try:
            if path is None:
                raise OSError("missing")
            header = fits.getheader(path, 0)
        except Exception:  # noqa: BLE001 — an unreadable sub is counted, not fatal
            unreadable += 1
            continue
        # Tallies count distinct UTC dates (a date, never finer — the contract);
        # the within-night check uses the session number from the sampler.
        night = (f.timestamp_utc or "")[:10] or "?"
        targets.add(target)
        nights.add(night)
        if "FILTER" in header:
            tok = _token(header["FILTER"])
            if tok is None:
                other["subs"] += 1
                other["_distinct"].add(str(header["FILTER"]).strip())
                tok = "(other)"
            else:
                _bump(values, tok, target, night, fam)
        else:
            tok = "(absent)"
            _bump(values, tok, target, night, fam)
        per_night.setdefault((target, night_no), []).append(tok)
        for k in _filter_like_keys(header):
            _bump(keys, k, target, night, fam)

    read = len(plan) - unreadable
    return {
        "subs_sampled": len(plan),
        "subs_read": read,
        "subs_unreadable": unreadable,
        "targets": len(targets),
        "nights": len(nights),
        "filter_card": _finish(values),
        "filter_card_other_values": {"subs": other["subs"],
                                     "distinct": len(other["_distinct"])},
        "other_filter_keywords": _finish(keys),
        "target_nights_read": len(per_night),
        "target_nights_with_two_or_more_read": sum(
            1 for v in per_night.values() if len(v) > 1),
        "target_nights_with_more_than_one_value": sum(
            1 for v in per_night.values() if len(set(v)) > 1),
        "how_to_read": (
            "filter_card counts sampled subs by the value of their FILTER card; "
            "(absent) means the card is not written. If every sub is (absent) and "
            "other_filter_keywords is empty, the camera does not record the filter "
            "and the LP-filter idea is dropped. A night is one capture session; "
            "each sampled night is read at its first and last sub, so "
            "target_nights_with_more_than_one_value out of "
            "target_nights_with_two_or_more_read is how often the value changed "
            "within a night. Values that are not short plain "
            "words are counted in filter_card_other_values without their text."
        ),
    }


def ready(library) -> bool:  # noqa: ANN001
    """Any target with at least one sub."""
    return any((e.n_frames or 0) > 0 for e in library.list_targets())


DIAGNOSTIC = Diagnostic(
    name="filter_card_values",
    version=2,
    question=("Does the Seestar record in each sub whether its light-pollution filter "
              "was in, and with which values? (gate on the 'Was the LP filter on?' "
              "idea, Scout 2026-11-01)"),
    run=run,
    ready=ready,
)
