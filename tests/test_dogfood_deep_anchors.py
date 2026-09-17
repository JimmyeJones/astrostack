"""``agent-dogfood.sh --deep`` must still be pointing at real things.

The flag reaches into the app by **name** three times: it asks
``POST /api/sample`` for ``{"shape": "deep"}``, reads the ``deep_safe`` and
``deep_n_frames`` keys back off the status response, and then
``dogfood_deep.mjs`` addresses the frames table and its window foot by
``data-testid``. All of those links are strings in a shell script and a browser
drive, and a string is exactly the kind of link that rots silently — rename any
of them and the pass keeps running, prints a warning nobody reads, and the one
magnitude this flag exists to measure quietly stops being measured. Same guard
as ``test_dogfood_probe_anchors.py`` / ``_lag_`` / ``_big_``, for the fourth.

The last two tests are the ones that matter most, and they are the same shape as
``--big``'s "is it really past the proxy cap?": this flag's *entire* value is
that the sample is past the frames table's render window, and a default that
drifted back under it would leave every pass printing a cheerful sub count about
a table it was no longer stressing.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "agent-dogfood.sh"
DEEP_DRIVE = REPO / "scripts" / "dogfood_deep.mjs"
FRONTEND_SRC = REPO / "frontend" / "src"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_flag_is_wired_and_off_by_default():
    """Opt-in, like ``--mosaic`` and ``--big``: generation and QC are per-frame,
    so ~1,200 subs is about two minutes a default pass should not pay."""
    src = _script()
    assert "DO_DEEP=0" in src, "the flag no longer defaults off"
    assert "--deep) DO_DEEP=1" in src, "the flag is no longer parsed"
    assert "--deep" in src.split("set -euo pipefail")[0], (
        "the flag vanished from the usage header, which is what `-h` prints"
    )


def test_the_shape_it_asks_for_is_one_the_api_accepts():
    from webapp.routers.sample import SampleLoadIn

    assert '{"shape":"deep"}' in _script()
    assert SampleLoadIn(shape="deep").shape == "deep"


def test_the_status_keys_it_reads_are_ones_the_api_answers():
    from webapp.routers.sample import SampleStatusOut

    src = _script()
    for key in ("deep_safe", "deep_n_frames"):
        assert key in src, f"the script no longer reads {key}"
        assert key in SampleStatusOut.model_fields
    # Additive and defaulted, like the mosaic/big fields beside them: an older
    # caller reading this response must see exactly what it saw before.
    assert SampleStatusOut(loaded=False).deep_safe is None
    assert SampleStatusOut(loaded=False).deep_n_frames == 0


def test_the_pass_proves_it_reached_the_scale_rather_than_going_quiet():
    """The ``location_source`` / ``proxy_scale`` lesson, third time (v0.455.1):
    a seeding flag needs a line that proves the state was reached, not a line
    that is silent when it was not. A deep pass that generated six subs and said
    nothing about it is the empty state wearing a better hat."""
    src = _script()
    assert "with ${DEEP_N} subs" in src, (
        "the pass no longer prints how many subs it actually got"
    )
    assert "FEWER THAN 400 SUBS" in src, (
        "the pass no longer says when it is not at scale"
    )


def test_it_deliberately_does_not_stack_the_deep_target():
    """1,200 subs is a stack nobody in a scheduled run will wait for, and nothing
    this flag measures needs a picture. Pinned because "stack everything" is the
    obvious-looking edit."""
    src = _script()
    assert 'stack_target "$DEEP_SAFE"' not in src


def _drive_testids() -> set[str]:
    src = DEEP_DRIVE.read_text(encoding="utf-8")
    ids = set(re.findall(r'data-testid="([a-z0-9-]+)"', src))
    assert ids, "the deep drive no longer addresses the frames table at all"
    return ids


def _rendered_testids() -> set[str]:
    out: set[str] = set()
    for path in FRONTEND_SRC.rglob("*.tsx"):
        if ".test." in path.name:
            continue
        out |= set(re.findall(r'data-testid="([a-z0-9-]+)"',
                              path.read_text(encoding="utf-8")))
    return out


def test_every_id_the_drive_asks_for_is_really_rendered():
    missing = sorted(_drive_testids() - _rendered_testids())
    assert not missing, (
        f"dogfood_deep.mjs addresses {missing}, which no component renders — "
        "the drive would look for them, find nothing, and report 0 rows"
    )


def test_the_drive_still_measures_the_three_things_only_a_browser_can():
    """A future edit must not quietly narrow this back to "it screenshotted".

    The row count is the one the page-height probe structurally cannot see (the
    table's scroll container fixes its height); the node count is the number that
    moves with the rows; and the auto-grow is the one path jsdom can never cover
    at all, having no ``IntersectionObserver``.
    """
    src = DEEP_DRIVE.read_text(encoding="utf-8")
    assert "rows rendered" in src
    assert "DOM nodes" in src
    assert "IntersectionObserver" in src
    assert "the auto-grow did not fire" in src, (
        "the drive no longer says when the scroll path stopped working — which "
        "is a degradation nobody notices, since the button still reaches every row"
    )


def test_the_deep_sample_is_genuinely_past_the_frames_tables_render_window():
    """The flag's whole claim, checked against the two constants that decide it —
    one in Python, one in TypeScript, which is why nothing else notices."""
    from webapp import sample_data

    window_src = (REPO / "frontend" / "src" / "frameWindow.ts").read_text(encoding="utf-8")
    m = re.search(r"FRAME_WINDOW_STEP\s*=\s*(\d+)", window_src)
    assert m is not None, "FRAME_WINDOW_STEP is no longer a literal in frameWindow.ts"
    step = int(m.group(1))
    assert sample_data._DEEP_N_SUBS >= 3 * step, (
        "the deep sample no longer stresses the frames table's window, so "
        "--deep reaches nothing an ordinary pass did not already reach"
    )
    # …and the other three samples are the reason it had to exist.
    assert sample_data._N_SUBS < step
    assert sum(sample_data._MOSAIC_PANEL_SUBS) < step
