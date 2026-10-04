"""The scale-invariance instrument must keep its sensitivity, and keep pointing
at real routes.

``scripts/dogfood_scale_pair.py`` asks the two bundled mosaic samples — which
differ in *scale alone* (``webapp.sample_data``) — the same questions and prints
what moved. Its whole value is that it would have caught v0.492.33, where
``classify_target`` called the same sky a galaxy on the small canvas and a star
cluster on the big one. So the tests that matter are: does it still *say so* when
handed that pair of answers, does it stay quiet on the differences that are
honest, and do the four questions it asks still name live endpoints with the
right method? The last one is the rot an anchors test exists for — every link is
a string in a dev script, so a renamed route keeps the pass running and silently
stops asking (same guard as ``test_dogfood_restack_anchors.py``).
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "agent-dogfood.sh"
HELPER = REPO / "scripts" / "dogfood_scale_pair.py"


def _helper():
    spec = importlib.util.spec_from_file_location("dogfood_scale_pair", HELPER)
    mod = importlib.util.module_from_spec(spec)
    # Registered before exec: a frozen dataclass resolves its own annotations
    # through ``sys.modules[cls.__module__]``, which is ``None`` for a module
    # loaded by path alone.
    sys.modules["dogfood_scale_pair"] = mod
    spec.loader.exec_module(mod)
    return mod


# One plausible pair of answers, as the app returns them: the *same* picture,
# shot with the two samples' two sensors. Everything canvas-independent agrees.
_SMALL = {
    "editor/preset-suggestion": {
        "preset_id": "nebula", "label": "Nebula",
        "reason": "broad extended glow over 7% of the frame", "confidence": 1.0},
    "editor/auto-analysis": {
        "sky": 0.102, "sky_sigma": 0.0031, "noisy": False, "noise_fraction": 0.12,
        "median_fwhm": 4.1, "sharpen_radius": 1.2, "is_mosaic": True,
        "trim_fraction": 0.081, "trim_fraction_available": 0.081, "auto_crop": True},
    "framing": {
        "level": "clipped", "text": "about 55% of it is in this picture",
        "coverage": 0.55, "coverage_pct": 55, "off_centre": 0.21,
        "canvas": "mosaic", "nudge": {"direction": "south", "degrees": 0.4,
                                      "text": "nudge south", "short": "0.4 S"},
        "recentre": None, "recentre_refused": None,
        "object_name": "M 42", "size_arcmin": 85.0},
    "stack-health": {
        "run_id": 7,
        "notes": [{"kind": "uncalibrated", "severity": "info",
                   "message": "adding darks is the biggest cleanup",
                   "action": "calibration"}],
        "background_clean": True},
}


def _pair(**overrides):
    """``(small, full_size)`` answers; ``overrides`` patch the full-size half."""
    big = copy.deepcopy(_SMALL)
    for title, patch in overrides.items():
        big[title].update(patch)
    return _SMALL, big


def _report(mod, small, big):
    def fetch(q, side):
        return (small if side == 0 else big)[q.title]
    return "\n".join(mod.report(fetch))


def test_the_pre_v0_492_33_verdict_split_is_reported_as_a_finding():
    """The one bug of this class that has actually happened: the archetype chip
    called the same sky a galaxy at one canvas size and a star cluster at the
    other. A rig that does not shout here has no sensitivity at all."""
    mod = _helper()
    small, big = _pair(**{"editor/preset-suggestion":
                          {"preset_id": "cluster", "label": "Star cluster"}})
    out = _report(mod, small, big)
    assert "MOVED  preset_id" in out
    assert "MOVED  label" in out
    # Both sides of a finding, in full: see the note-list test below.
    assert "small     = Nebula" in out
    assert "full-size = Star cluster" in out
    assert "2 of " in out and "answers moved with the canvas" in out
    assert "read each as a bug until explained" in out


def test_a_finding_in_a_long_list_of_claims_names_the_part_that_moved():
    """How this rig reported its own first real finding, before the fix: the
    ``stack-health`` note list moved, and both sides printed the *same*
    truncated prefix, so the output said something had changed and not what.
    A finding the reader cannot read is not a finding."""
    mod = _helper()
    small, big = _pair(**{"stack-health": {"notes": [
        *_SMALL["stack-health"]["notes"],
        {"kind": "trim_border", "severity": "info",
         "message": "about 8% of the canvas is ragged edge",
         "action": "trim_border"},
    ]}})
    out = _report(mod, small, big)
    assert "MOVED  notes" in out
    assert "only in small: -" in out
    assert "only in full-size: trim_border/info/trim_border" in out


def test_an_identical_pair_reads_clean_and_says_what_it_asked():
    """A report that prints only failures cannot be told apart from one that
    asked nothing, so the clean reading has to carry its own evidence."""
    mod = _helper()
    out = _report(mod, _SMALL, copy.deepcopy(_SMALL))
    assert "MOVED" not in out
    assert "0 of " in out
    assert "CLEAN on everything asked" in out
    # The evidence: every canvas-independent answer it checked, named.
    for key in ("preset_id", "label", "is_mosaic", "median_fwhm", "sky",
                "canvas", "object_name", "notes"):
        assert f"same   {key}" in out


def test_the_honest_differences_are_informational_not_findings():
    """Two differences are built into the fixture pair and must never read as
    bugs: the panels' jitter is a fixed *pixel* count, so the ragged corner is a
    smaller share of the bigger canvas; and the bigger canvas really does catch
    more of M42."""
    mod = _helper()
    small, big = _pair(**{
        "editor/auto-analysis": {"trim_fraction": 0.023,
                                 "trim_fraction_available": 0.023},
        "framing": {"level": "good", "coverage": 1.0, "coverage_pct": 100,
                    "nudge": None},
    })
    out = _report(mod, small, big)
    assert "MOVED" not in out
    assert "trim_fraction 0.081->0.023" in out
    assert "coverage_pct 55->100" in out


def test_a_measurement_that_drifts_is_tolerated_and_one_that_jumps_is_not():
    """The two samples draw their noise from different streams on purpose, so a
    few percent of drift in a background number is the fixture, not a finding —
    while a real scale dependence moves it far further (the raw cues behind a
    verdict move ~30 % relative)."""
    mod = _helper()
    assert mod.agree(0.102, 0.104, 0.15)
    assert not mod.agree(0.102, 0.30, 0.15)
    # No tolerance means exact: a verdict is not a measurement.
    assert not mod.agree(4.1, 4.2)
    # ``True == 1`` in Python, and a verdict that turned into a number is not
    # the same answer.
    assert not mod.agree(True, 1)
    assert not mod.agree(False, 0.0)
    assert mod.agree(True, True)


def test_an_unreachable_answer_is_printed_rather_than_counted_clean():
    mod = _helper()
    out = "\n".join(mod.report(
        lambda q, side: {mod.UNREACHABLE: "URLError: connection refused"},
        mod.QUESTIONS[:1]))
    assert "UNREACHABLE" in out
    assert "nothing could be asked" in out
    assert "CLEAN" not in out


def test_every_question_names_a_live_route_with_the_right_method():
    """The rot an anchors test exists for: each question is a URL string in a
    dev script, so a renamed route or a GET that became a POST would keep the
    pass running and quietly stop asking."""
    from webapp.main import create_app

    mod = _helper()
    paths = create_app().openapi()["paths"]
    for q in mod.QUESTIONS:
        route = q.path.replace("{run}", "{run_id}")
        assert route in paths, f"{route} is no longer a route"
        method = "post" if q.post else "get"
        assert method in paths[route], f"{route} is no longer a {method.upper()}"


def test_the_shell_pass_runs_it_and_only_with_both_halves_of_the_pair():
    """It is meaningless with one sample, and the flag that loads the big one is
    not the flag that loads the small one — so a pass given only ``--big`` has
    to be told, not quietly skipped."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "scripts/dogfood_scale_pair.py" in src, "the pass no longer runs the diff"
    assert '[ -n "$BIG_SAFE" ] && [ -n "$MOSAIC_SAFE" ]' in src, (
        "the diff is no longer gated on BOTH halves of the pair"
    )
    assert "add --mosaic to this pass" in src, (
        "a --big-only pass is no longer told why the diff did not run"
    )
