"""``agent-dogfood.sh --big`` must still be pointing at real things.

The flag reaches into the app by **name** three times: it asks
``POST /api/sample`` for ``{"shape": "big"}``, reads the ``big_safe`` key back
off the status response, and then asks ``/editor/loupe-info`` what the app says
about the shrunk preview. All three links are strings in a shell script, and a
string is exactly the kind of link that rots silently — rename any of them and
the pass keeps running, prints a warning nobody reads, and the one surface this
flag exists to reach quietly stops being reachable.

That is the failure ``test_dogfood_probe_anchors.py`` was written for and
``test_dogfood_lag_anchors.py`` repeated for the other half of the tooling; this
is the same guard for the third.

The last test here is the one that matters most: the flag's *entire* value is
that this sample's canvas is past ``PROXY_MAX_PX``, and a sample that quietly
drifted back under it would leave every pass reporting CLEAN about a surface it
was no longer drawing — which is precisely the state that made this flag
necessary in the first place.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "agent-dogfood.sh"
EDITOR_DRIVE = REPO / "scripts" / "dogfood_editor.mjs"
FRONTEND_SRC = REPO / "frontend" / "src"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_flag_is_wired_and_off_by_default():
    """Opt-in, like ``--mosaic``: the full-size sample costs a stack, and a pass
    nobody runs finds nothing."""
    src = _script()
    assert "DO_BIG=0" in src, "the flag no longer defaults off"
    assert "--big) DO_BIG=1" in src, "the flag is no longer parsed"
    assert "--big" in src.split("set -euo pipefail")[0], (
        "the flag vanished from the usage header, which is what `-h` prints"
    )


def test_the_shape_it_asks_for_is_one_the_api_accepts():
    from webapp.routers.sample import SampleLoadIn

    assert '{"shape":"big"}' in _script()
    # The literal the script POSTs must be a value the request model allows —
    # a rename would otherwise 422 into the script's `|| echo warn` and pass.
    assert SampleLoadIn(shape="big").shape == "big"


def test_the_status_key_it_reads_is_one_the_api_answers():
    from webapp.routers.sample import SampleStatusOut

    assert "big_safe" in _script()
    assert "big_safe" in SampleStatusOut.model_fields
    # Additive and defaulted, like the mosaic fields beside it: an older caller
    # reading this response must see exactly what it saw before.
    assert SampleStatusOut(loaded=False).big_safe is None


def test_the_endpoint_it_reads_still_exists():
    from webapp.main import create_app

    assert "editor/loupe-info" in _script()
    paths = create_app().openapi()["paths"]
    assert any(p.endswith("/editor/loupe-info") for p in paths)


def test_the_sample_it_loads_is_genuinely_past_the_proxy_cap():
    """The flag's whole claim, checked against the two constants that decide it.

    Cheap — the layout is arithmetic, no pixels — and it fails the moment the
    sample is sized back under the cap, which is the silent regression that
    would leave every ``--big`` pass reporting CLEAN about a surface it had
    stopped drawing.
    """
    from seestack.edit.proxy import PROXY_MAX_PX
    from webapp import sample_data

    _panels, window = sample_data._mosaic_layout(sample_data._MOSAIC_BIG)
    assert max(window) > PROXY_MAX_PX, (
        "the full-size sample no longer decimates the editor proxy, so --big "
        "reaches nothing the --mosaic pass did not already reach"
    )
    # …and the other two are the reason it had to exist.
    _panels, small = sample_data._mosaic_layout(sample_data._MOSAIC_SMALL)
    assert max(small) <= PROXY_MAX_PX
    assert max(sample_data._WIDTH, sample_data._HEIGHT) <= PROXY_MAX_PX


# --- the editor drive's full-size-check leg --------------------------------
#
# `--big` exists so the shrunk-preview surface can be *reached*; the editor
# drive's `driveFullSizeCheck()` is what actually opens it. It addresses the
# modal by `data-testid`, which is the same string link the probe's own anchors
# test guards — rename one in the frontend and the drive keeps running, keeps
# reporting clean, and silently stops checking that half.


def _drive_testids() -> set[str]:
    """Every ``full-size-check-*`` id the editor drive asks the page for."""
    src = EDITOR_DRIVE.read_text(encoding="utf-8")
    ids = set(re.findall(r'"(full-size-check-[a-z0-9-]+)"', src))
    assert ids, "the editor drive no longer addresses the full-size check at all"
    return ids


def _rendered_testids() -> set[str]:
    """Every ``data-testid`` literal rendered by non-test frontend source."""
    out: set[str] = set()
    for path in FRONTEND_SRC.rglob("*.tsx"):
        if ".test." in path.name:
            continue
        out |= set(re.findall(r'data-testid="([a-z0-9-]+)"', path.read_text(encoding="utf-8")))
    return out


def test_every_id_the_drive_asks_for_is_really_rendered():
    missing = sorted(_drive_testids() - _rendered_testids())
    assert not missing, (
        f"dogfood_editor.mjs addresses {missing}, which no component renders — "
        "the drive would look for them, find nothing, and report clean"
    )


def test_the_drive_still_covers_the_parts_only_a_click_reaches():
    """A future edit must not quietly narrow this back to "the button exists".

    The modal, its navigator, the marker that says *where* the window is, and
    the split comparison are each behind a click, and the split is behind two.
    Nothing but this drive reaches any of them outside jsdom.
    """
    ids = _drive_testids()
    for needed in ("full-size-check-open", "full-size-check-image",
                   "full-size-check-navigator", "full-size-check-marker",
                   "full-size-check-where", "full-size-check-split-toggle",
                   "full-size-check-split-divider", "full-size-check-caption"):
        assert needed in ids, f"the drive stopped checking {needed}"


def test_the_drive_says_when_it_could_not_reach_the_surface():
    """A pass that never opened the modal must say so, not report nothing — the
    `location_source` lesson (v0.436.1): a silent skip reads as a clean run."""
    src = EDITOR_DRIVE.read_text(encoding="utf-8")
    assert "--big" in src, (
        "the drive no longer tells a reader how to reach the surface it skipped"
    )
    assert "not offered" in src


def test_the_field_leg_picks_the_field_sample_by_name():
    """Observed on the first ``--big`` pass: `/api/targets`' first row is ordered
    by activity, so with a second demo loaded and stacked the "sample" leg drove
    the **mosaic** — both editor drives on one target, and the field sample's
    ``$SHOTS`` (whose page heights the §1 baselines are measured against) holding
    a mosaic's numbers under the same filenames.
    """
    src = _script()
    head = src.split("# 3b.")[0]
    assert '"$BASE/api/sample"' in head, (
        "the field leg no longer asks which target the field sample is"
    )
    # The fall-back stays, so a --serve against a real library with no sample
    # loaded still picks a target rather than none.
    assert 't[0]["safe_name"]' in head
