"""``agent-dogfood.sh --dithered`` must still be pointing at real things.

Same guard as ``test_dogfood_big_anchors.py``, for the sixth sample shape. The
flag reaches into the app by **name**: it asks ``POST /api/sample`` for
``{"shape": "dithered"}``, reads ``dithered_safe`` back off the status response,
and then reads four surfaces of that run by path. Every one of those links is a
string in a shell script, and a string is exactly the kind of link that rots
silently — rename any of them and the pass keeps running, prints a warning nobody
reads, and the one surface this flag exists to reach quietly stops being
reachable.

The last test is the one that matters most, and it is the direct analogue of
``--big``'s: this flag's *entire* value is that the sample's coverage depths are a
**continuum** rather than plateaus. A sample that quietly drifted back onto a
plateau — a collapsed per-sub pointing, a narrowed spread — would leave every
pass reporting CLEAN about the one mosaic shape the tooling was built to reach,
which is precisely the state that made the flag necessary.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "agent-dogfood.sh"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_flag_is_wired_and_off_by_default():
    """Opt-in, like ``--mosaic`` and ``--big``: it costs a 78-sub stack, and a
    pass nobody runs finds nothing."""
    src = _script()
    assert "DO_DITHERED=0" in src, "the flag no longer defaults off"
    assert "--dithered) DO_DITHERED=1" in src, "the flag is no longer parsed"
    assert "--dithered" in src.split("set -euo pipefail")[0], (
        "the flag vanished from the usage header, which is what `-h` prints"
    )


def test_the_shape_it_asks_for_is_one_the_api_accepts():
    from webapp.routers.sample import SampleLoadIn

    assert '{"shape":"dithered"}' in _script()
    # The literal the script POSTs must be a value the request model allows —
    # a rename would otherwise 422 into the script's `|| echo warn` and pass.
    assert SampleLoadIn(shape="dithered").shape == "dithered"


def test_the_status_key_it_reads_is_one_the_api_answers():
    from webapp.routers.sample import SampleStatusOut

    assert "dithered_safe" in _script()
    assert "dithered_safe" in SampleStatusOut.model_fields
    # Additive and defaulted, like every block beside it: an older caller reading
    # this response must see exactly what it saw before.
    assert SampleStatusOut(loaded=False).dithered_safe is None


def test_the_surfaces_it_reads_still_exist():
    from webapp.main import create_app

    src = _script()
    wanted = ("editor/trim-suggestion", "stack-health", "mosaic-map", "stack-runs")
    for name in wanted:
        assert name in src, f"the script stopped reading {name}"
    paths = create_app().openapi()["paths"]
    for name in wanted:
        assert any(name in path for path in paths), (
            f"the app no longer serves {name}")


def test_the_keys_it_reads_off_the_run_listing_are_ones_the_app_answers():
    """The readout prints the canvas and the coverage range off ``/stack-runs``.

    It deliberately does *not* reach for ``coverage_thin_frac`` /
    ``uncovered_frac`` / ``is_mosaic`` there — those are not on that response, and
    the honest places to read them are ``/stack-health`` (which says them as
    sentences) and ``/editor/trim-suggestion`` (which answers ``is_mosaic``). This
    pins that choice so nobody re-adds a key the listing does not serve.
    """
    from webapp.routers.sample import SampleStatusOut  # noqa: F401 — import guard
    from webapp.schemas import StackRunOut

    fields = StackRunOut.model_fields
    for key in ("canvas_w", "canvas_h", "n_frames_used",
                "coverage_min", "coverage_max"):
        assert key in fields, f"/stack-runs no longer answers {key}"


def test_the_sample_it_loads_really_has_no_plateau():
    """The flag's whole reason to exist, measured on the layout it loads.

    Geometry only — the footprint sum, which is what the frame-count coverage map
    the rules read *is* — so this runs in milliseconds on every suite. The
    end-to-end version, through a real ``run_stack`` and including the weighted
    map's own (different) branch, is in
    ``tests/webapp/test_sample_data.py::test_the_dithered_sample_stacks_onto_a_canvas_with_no_plateau``.
    """
    import numpy as np

    from tests import shapes
    from webapp import sample_data

    cfg = sample_data._MOSAIC_DITHERED
    panels, window = sample_data._mosaic_layout(cfg)
    cov = np.zeros((window[1], window[0]), dtype=np.float64)
    for panel in panels:
        for x, y in panel.sub_origins:
            cov[y:y + cfg.frame_h, x:x + cfg.frame_w] += 1.0
    cov[cov == 0] = np.nan

    shapes.assert_the_plateau_search_finds_a_phantom(cov, what="--dithered sample")
    # And the blocky sample this one is the counterpart to is *not* that shape —
    # the control, and the reason the flag had to exist at all.
    blocky_cfg = sample_data._MOSAIC_SMALL
    blocky, blocky_window = sample_data._mosaic_layout(blocky_cfg)
    blocky_cov = np.zeros((blocky_window[1], blocky_window[0]), dtype=np.float64)
    for panel in blocky:
        for _ in range(panel.n_subs):
            x, y = panel.origin
            blocky_cov[y:y + blocky_cfg.frame_h,
                       x:x + blocky_cfg.frame_w] += 1.0
    blocky_cov[blocky_cov == 0] = np.nan
    found = shapes.plateau_search_level(blocky_cov)
    assert found is not None, "the blocky sample stopped finding a plateau"
    median = float(np.median(shapes.covered_values(blocky_cov)))
    assert found < 1.5 * median, (
        "the blocky sample now presents a phantom too, so it is no longer the "
        "control this flag is measured against")
