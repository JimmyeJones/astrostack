"""``agent-dogfood.sh --restack`` must still be pointing at real things.

The flag reaches into the app by **name**: it sets subs aside through
``POST /api/targets/{safe}/frames/bulk``, re-processes through
``POST /api/targets/{safe}/process``, and then reports what
``/stack-runs``, ``/deepening-reel/info`` and ``/noise-delta/info`` answer about
the pair it made. Every one of those links is a string in a shell script, and a
string is exactly the kind of link that rots silently — rename an endpoint or
change the bulk action's spelling and the pass keeps running, prints a warning
nobody reads, and the two-run state this flag exists to reach quietly stops
happening. Same guard as ``test_dogfood_lag_anchors.py``, for the other hole.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "agent-dogfood.sh"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_flag_is_wired_and_off_by_default():
    """It grows the field sample's Target page (a compare card, a reel, a second
    History row), so it must never be what the default pass measures — the
    script's own header says so."""
    src = _script()
    assert "DO_RESTACK=0" in src, "the flag no longer defaults off"
    assert "--restack) DO_RESTACK=1" in src, "the flag is no longer parsed"
    assert "--restack" in src.split("set -euo pipefail")[0], (
        "the flag vanished from the usage header, which is what `-h` prints"
    )


def test_it_runs_before_the_ordinary_stack_step():
    """`stack_target` returns early once a run exists, so the two runs have to be
    made *before* it — otherwise this flag adds a third run instead of being the
    pair, and the "is the newest deeper?" line it prints becomes a lie."""
    src = _script()
    assert src.index('if [ "$DO_RESTACK" = 1 ]') \
        < src.index('if [ "$DO_STACK" = 1 ]; then\n  stack_target')


def test_the_endpoints_it_calls_all_exist():
    from webapp.main import create_app

    paths = create_app().openapi()["paths"]
    src = _script()
    for route in ("/api/targets/{safe}/frames",
                  "/api/targets/{safe}/frames/bulk",
                  "/api/targets/{safe}/process",
                  "/api/targets/{safe}/stack-runs",
                  "/api/targets/{safe}/deepening-reel/info",
                  "/api/targets/{safe}/noise-delta/info"):
        assert route in paths, f"{route} is no longer a route"
        # The script spells them with $SAFE substituted in.
        assert route.replace("{safe}", "$SAFE") in src, f"{route} is no longer called"


def test_the_bulk_actions_it_uses_are_still_spelled_that_way():
    """`reject` then `accept` is how it makes the first run thin and the second
    deep. A renamed action would leave both runs at full depth — two identical
    masters, on which every card this flag exists to photograph says "no
    change"."""
    from webapp.schemas import BulkFrameAction

    src = _script()
    assert '\\"action\\": \\"reject\\"' in src
    assert '\\"action\\": \\"accept\\"' in src
    # And the model still takes an `action` plus the `ids` the script sends.
    assert {"action", "ids"} <= set(BulkFrameAction.model_fields)


def test_it_reports_the_two_ways_the_pair_can_fail_silently():
    """A second run that failed, or one that is not actually deeper, leaves every
    cross-run surface self-hidden — and the pass would still read CLEAN. The same
    trap the observing site's `location_source` line and --big's `proxy_scale`
    line close for their own flags, so this one says it out loud too."""
    src = _script()
    assert "FEWER THAN TWO RUNS" in src
    assert "is NOT deeper" in src
