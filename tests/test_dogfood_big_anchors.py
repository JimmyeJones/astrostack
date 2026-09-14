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

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "agent-dogfood.sh"


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
