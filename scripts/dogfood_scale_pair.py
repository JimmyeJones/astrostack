"""Ask the two bundled mosaic samples the same questions and diff the answers.

``webapp.sample_data``'s own comment is the premise: the small mosaic sample and
the full-size one "differ in *scale alone* and a finding on one is a question
about the other" — same 2x2 grid, same 82 % step, same uneven depth, same hazy
panel, one shared star catalog at one shared on-sky density, stars rendered at
one shared 4.0 px FWHM, one shared plate scale. Only the sensor differs
(480x320 vs 900x600), so the union canvas grows from ~907 px to ~1686 px and the
editor's preview goes from undecimated to ``proxy_scale`` 2.

That makes the pair an *instrument*: any answer that claims to describe the
**sky** rather than the **picture** must come back the same from both, and one
that moves when only the sensor did is a bug until somebody explains it. Not a
theoretical instrument — v0.492.33 was exactly this failure, and it was
invisible until somebody asked both ("Galaxy" from one, "Star cluster" from the
other, confidence 1.0 each, because ``classify_target``'s opening footprint was
a fixed 7x7 in *proxy* pixels while the star mask next door scaled its own).
``agent-dogfood.sh --big`` already loaded the pair; it probed the two
independently and never compared, which is why the instrument existed and
nothing used it.

This is a **finder, not a gate**: it prints a short list to read. Some
differences are honest, and each question names its own (the full-size canvas
really does catch more of M42, so ``framing``'s coverage *should* differ); the
raw cues behind a verdict move ~30 % relative between the two even when every
verdict holds, which is why a tolerance here is a reading aid and never a
pass/fail. Anything this turns up still needs a real regression test
(AGENTS.md §7).

**Read a MOVED number against the stride before calling it a canvas bug.** The
pair differs in two ways at once: the canvas's extent, and — because the bigger
union canvas passes ``PROXY_MAX_PX`` — the proxy *stride*. On this rig's first
real run ``sky_sigma`` moved 0.0004 → 0.0007 and that turned out to be the
stride alone: asked of **one** master at steps 1/2/4 it reads 0.000429 /
0.000651 / 0.000736, and the two samples agree to three digits at every stride.
So for anything measured on the proxy, the second question is "does it still
move when I hold the canvas and change only the stride?" — one call against one
master, and it separated a real finding from a non-finding here in minutes.

Run it through ``scripts/agent-dogfood.sh --mosaic --big``, which boots the app,
loads and stacks both samples and then calls this with their safe names.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

#: What the two columns are called in the report. The small mosaic is the
#: fixture every prior mosaic finding was measured on.
LABEL_A = "small"
LABEL_B = "full-size"

#: What a fetcher returns when it could not get an answer at all.
UNREACHABLE = "__unreachable__"


def health_claims(payload: Any) -> dict[str, Any]:
    """``stack-health`` reduced to what it says about *depth and calibration*.

    Both samples are the same 21 subs over the same two nights with no masters
    bound, so which notes fire, how loud each is, and what each offers to do
    are all canvas-independent. The messages themselves quote pixel counts, so
    they are left to the informational half.
    """
    notes = sorted((payload or {}).get("notes") or [],
                   key=lambda n: str(n.get("kind")))
    return {
        "notes": ", ".join(
            f"{n.get('kind')}/{n.get('severity')}/{n.get('action') or '-'}"
            for n in notes) or "(none)",
        "background_clean": (payload or {}).get("background_clean"),
    }


def framing_claims(payload: Any) -> dict[str, Any]:
    """``framing`` reduced to the parts that cannot move with the sensor.

    Which object the app decided this is, and which *shape* of picture it says
    it is, are about the sky and about the stacker's own ``is_mosaic`` verdict.
    The rest — the coverage, the verdict level, the nudge — is about how much
    sky the canvas caught, which is the one thing that genuinely differs here;
    it is carried into the report unchecked, so the honest difference is printed
    with its own numbers rather than only described.
    """
    d = payload or {}
    nudge = d.get("nudge") or {}
    return {
        "answered": payload is not None,
        "canvas": d.get("canvas"),
        "object_name": d.get("object_name"),
        "size_arcmin": d.get("size_arcmin"),
        "level": d.get("level"),
        "coverage_pct": d.get("coverage_pct"),
        "off_centre": d.get("off_centre"),
        "nudge_direction": nudge.get("direction"),
    }


@dataclass(frozen=True)
class Question:
    """One question asked of both samples, and what its answer may depend on."""

    #: How the report names it — the endpoint, so a reader can go and look.
    title: str
    #: URL template, with ``{safe}`` and ``{run}``.
    path: str
    #: Whether the endpoint is a POST (the two editor hints are).
    post: bool
    #: Reduces a raw payload to the claims worth comparing; ``None`` compares
    #: the payload's own top-level keys.
    claims: Callable[[Any], dict[str, Any]] | None
    #: The keys whose answer is about the sky, so must not depend on the canvas.
    must_agree: tuple[str, ...]
    #: Relative tolerance per key; absent means exact. The two samples draw
    #: their *noise* from different streams on purpose, which is why the
    #: background numbers get the loosest ones.
    tolerance: dict[str, float] = field(default_factory=dict)
    #: One line on what may honestly differ here, printed with the answers so
    #: the list can be read without a second document open.
    may_differ: str = ""


QUESTIONS: tuple[Question, ...] = (
    Question(
        title="editor/preset-suggestion",
        path="/api/targets/{safe}/stack-runs/{run}/editor/preset-suggestion",
        post=True,
        claims=None,
        must_agree=("preset_id", "label"),
        may_differ="`confidence` is pinned to 1.0 inside two of its three gates "
                   "(backlog, 2026-10-04); `reason` quotes raw cues that move "
                   "~30 % relative with the canvas even when the verdict holds",
    ),
    Question(
        title="editor/auto-analysis",
        path="/api/targets/{safe}/stack-runs/{run}/editor/auto-analysis",
        post=True,
        claims=None,
        must_agree=("is_mosaic", "noisy", "auto_crop", "median_fwhm",
                    "sharpen_radius", "sky", "sky_sigma", "noise_fraction"),
        tolerance={"median_fwhm": 0.10, "sharpen_radius": 0.10, "sky": 0.15,
                   "sky_sigma": 0.25, "noise_fraction": 0.25},
        may_differ="`trim_fraction` is NOT comparable: the panels' pointing "
                   "jitter is the same *pixel* count in both samples, so the "
                   "same ragged corner is a smaller share of the bigger canvas",
    ),
    Question(
        title="framing",
        path="/api/targets/{safe}/stack-runs/{run}/framing",
        post=False,
        claims=framing_claims,
        must_agree=("answered", "canvas", "object_name", "size_arcmin"),
        may_differ="the level, coverage_pct, off_centre and the nudge all SHOULD "
                   "be free to differ — the full-size canvas catches ~3.5x the sky",
    ),
    Question(
        title="stack-health",
        path="/api/targets/{safe}/stack-health",
        post=False,
        claims=health_claims,
        must_agree=("notes", "background_clean"),
        may_differ="nothing here is expected to move: same 21 subs, same two "
                   "nights, no masters bound on either",
    ),
)


def agree(a: Any, b: Any, tol: float | None = None) -> bool:
    """Whether two answers are the same answer.

    ``bool`` is checked before ``int``/``float`` on purpose: ``True == 1`` in
    Python, and a verdict that turned into a number is not something this may
    call equal.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, int | float) and isinstance(b, int | float):
        if not tol:
            return a == b
        return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)
    return a == b


def _short(v: Any, cap: int = 70) -> str:
    s = v if isinstance(v, str) else json.dumps(v)
    return s if len(s) <= cap else f"{s[:cap - 3]}..."


def _moved_lines(key: str, va: Any, vb: Any) -> list[str]:
    """A finding, rendered so the reader can see *what* moved.

    One line each, and a wide cap, because truncating to a column hid the whole
    finding on this rig's first real run: ``stack-health``'s note list moved, and
    both sides printed the same truncated prefix. A comma-separated list of
    claims (which is how the reduced ``stack-health`` and anything like it comes
    out) also gets its two one-sided differences spelled out, since that is the
    finding and the shared part is noise.
    """
    out = [f"      MOVED  {key}",
           f"             {LABEL_A:<9} = {_short(va, 300)}",
           f"             {LABEL_B:<9} = {_short(vb, 300)}"]
    if isinstance(va, str) and isinstance(vb, str) and ", " in va + vb:
        only_a = [x for x in va.split(", ") if x not in vb.split(", ")]
        only_b = [x for x in vb.split(", ") if x not in va.split(", ")]
        if only_a or only_b:
            out.append(f"             only in {LABEL_A}: {', '.join(only_a) or '-'}"
                       f"   only in {LABEL_B}: {', '.join(only_b) or '-'}")
    return out


def compare(q: Question, a: Any, b: Any) -> dict[str, Any]:
    """Two answers to one question, sorted into what moved and what did not.

    ``moved`` is the finding. ``same`` is the evidence that the question was
    really asked — a report that prints only failures cannot be told apart from
    one that asked nothing. ``others`` is the informational half, and holds the
    differences each question's ``may_differ`` names as honest.
    """
    bad = [d[UNREACHABLE] for d in (a, b)
           if isinstance(d, dict) and UNREACHABLE in d]
    if bad:
        return {"unreachable": bad, "same": [], "moved": [], "others": []}
    ra = q.claims(a) if q.claims else (a or {})
    rb = q.claims(b) if q.claims else (b or {})
    same: list[tuple[str, Any]] = []
    moved: list[tuple[str, Any, Any]] = []
    for key in q.must_agree:
        va, vb = ra.get(key), rb.get(key)
        if agree(va, vb, q.tolerance.get(key)):
            same.append((key, va))
        else:
            moved.append((key, va, vb))
    rest = sorted((set(ra) | set(rb)) - set(q.must_agree))
    others = [(k, ra.get(k), rb.get(k)) for k in rest
              if not agree(ra.get(k), rb.get(k))]
    return {"unreachable": [], "same": same, "moved": moved, "others": others}


def report(fetch: Callable[[Question, int], Any],
           questions: tuple[Question, ...] = QUESTIONS) -> list[str]:
    """The whole report as lines, given something that answers a question.

    ``fetch(question, side)`` returns the payload for side 0 (the small sample)
    or side 1 (the full-size one), or a dict carrying :data:`UNREACHABLE`. It is
    injected so the report's own reading of an answer is testable without an app.
    """
    out: list[str] = []
    moved_total = checked_total = 0
    for q in questions:
        res = compare(q, fetch(q, 0), fetch(q, 1))
        out.append(f"   [scale] {q.title}")
        if res["unreachable"]:
            out.append("      UNREACHABLE on one or both: "
                       + "; ".join(res["unreachable"]))
            out.append("      (read that as a result too — this pair IS the instrument)")
            continue
        for key, val in res["same"]:
            out.append(f"      same   {key:<22} {_short(val)}")
        for key, va, vb in res["moved"]:
            out.extend(_moved_lines(key, va, vb))
        checked_total += len(res["same"]) + len(res["moved"])
        moved_total += len(res["moved"])
        if res["others"]:
            out.append("      also differs (may be honest): "
                       + ", ".join(f"{k} {_short(va)}->{_short(vb)}"
                                   for k, va, vb in res["others"][:6]))
        if q.may_differ:
            out.append(f"      note: {q.may_differ}")
    if not checked_total:
        out.append("   [scale] nothing could be asked — see the UNREACHABLE line(s) above")
        return out
    out.append(f"   [scale] {moved_total} of {checked_total} canvas-independent "
               "answers moved with the canvas")
    if moved_total:
        out.append("   [scale] every MOVED line is a claim about the SKY that changed")
        out.append("           when only the SENSOR did — read each as a bug until explained")
    else:
        out.append("   [scale] CLEAN on everything asked — and the list above is")
        out.append("           what was asked: a question nobody asks is not one answered")
    return out


def _urllib_fetch(base: str,
                  sides: tuple[tuple[str, str], tuple[str, str]],
                  ) -> Callable[[Question, int], Any]:
    import urllib.request

    def fetch(q: Question, side: int) -> Any:
        safe, run = sides[side]
        url = base + q.path.format(safe=safe, run=run)
        req = urllib.request.Request(
            url, data=b"" if q.post else None,
            method="POST" if q.post else "GET")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read()
        except Exception as exc:  # noqa: BLE001 — "no answer" is itself a result
            return {UNREACHABLE: f"{type(exc).__name__}: {exc}"}
        try:
            return json.loads(body or b"null")
        except ValueError:
            return {UNREACHABLE: "answered, but not JSON"}

    return fetch


def main(argv: list[str] | None = None) -> int:
    """``dogfood_scale_pair.py <small_safe> <small_run> <big_safe> <big_run>``."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 4 or not all(args):
        print("   [scale] skipped: needs BOTH mosaic samples, stacked "
              "(--mosaic --big)")
        return 0
    base = os.environ.get("BASE", "http://127.0.0.1:8000").rstrip("/")
    fetch = _urllib_fetch(base, ((args[0], args[1]), (args[2], args[3])))
    for line in report(fetch):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
