"""The combine dispatcher runs the branch ``combine_method`` names — proved on
real stacks, not by reading the source.

``run_stack``'s ``if/elif`` chain used to re-write its own frame-count gates
(``min_max_reject and n >= 3``, ``sigma_clip and n >= 4``). The same three
conditions were written out four times across the module, and the drift that
made the duplication matter had already happened once: a fifth surface, the
Stack form, disagreed with them (fixed in v0.323.1 by giving the gates one
public definition, :func:`combine_method`).

The dispatcher and ``_records_rejection_map`` now branch on that definition, so
they cannot fall behind it. These tests are the evidence *for the other
direction*: that the definition still describes what the run does. They read
``REJMODE``, which each branch body writes from its own ``RejectionStats`` — so
a branch taken against ``combine_method``'s answer would show up here, whereas
asserting on ``STACKER`` (which ``combine_method`` itself fills in) could not.
"""

from __future__ import annotations

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.stacker import (  # noqa: E402
    StackOptions,
    _records_rejection_map,
    combine_method,
    run_stack,
)

_BASE_OPTS = dict(
    background_flatten=False, suppress_hot_pixels=False,
    max_workers=2, output_name="out",
)

#: What each combine writes into ``REJMODE``. ``"mean"`` writes no card at all —
#: no rejection pass ran, so there is nothing honest to record.
_REJMODE_OF = {
    "mean": None,
    "min-max-reject": "min-max-reject",
    "sigma-clip": "sigma-clip",
}


def _build_project(tmp_path, n_frames: int) -> Project:
    from tests.synth import make_synth_wcs_text as _wcs_text
    from tests.synth import write_seestar_fits

    proj = Project.create(tmp_path / "p", name="dispatch_test")
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(n_frames):
        path = write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, seed=7, noise_seed=100 + i,
            n_stars=10,
        )
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=_wcs_text(),
            ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    return proj


def _stack_rejmode(tmp_path, n_frames: int, **overrides) -> str | None:
    """``REJMODE`` off the finished master, or ``None`` when no card was written."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n_frames)
    try:
        result = run_stack(proj, StackOptions(**{**_BASE_OPTS, **overrides}))
    finally:
        proj.close()
    with fits.open(result.fits_path) as hdul:
        return dict(hdul[0].header).get("REJMODE")


# Both sides of every gate the dispatcher has, so re-inlining a wrong one shows.
@pytest.mark.parametrize(("n", "opts"), [
    (3, {}),                                          # sigma-clip needs 4 → mean
    (4, {}),                                          # …and takes it at 4
    (2, {"sigma_clip": False, "min_max_reject": True}),   # min/max needs 3 → mean
    (3, {"sigma_clip": False, "min_max_reject": True}),   # …and takes it at 3
    (4, {"sigma_clip": True, "min_max_reject": True}),    # min/max wins over κ-σ
])
def test_the_run_takes_the_branch_combine_method_names(tmp_path, n, opts):
    expected = combine_method(StackOptions(**opts), n)
    assert _stack_rejmode(tmp_path, n, **opts) == _REJMODE_OF[expected]


def test_records_rejection_map_agrees_with_the_combine_it_will_run(tmp_path):
    """The mirror that used to carry the same three conditions a second time.

    Only the two *data-driven* rejections record a map: κ-σ, and the two-pass
    drizzle. A min/max run's drop is structural (2k samples per pixel by
    construction), and a plain mean drops nothing — neither has a map to write.
    """
    for n in (2, 3, 4, 12):
        for opts in ({}, {"sigma_clip": False, "min_max_reject": True},
                     {"sigma_clip": True, "min_max_reject": True}):
            o = StackOptions(record_rejection_map=True, **opts)
            assert _records_rejection_map(o, n) is (
                combine_method(o, n) == "sigma-clip"), (n, opts)
    # Drizzle is the exception: its map rides on ``drizzle_reject``, not on the
    # combine name, and it too needs four frames before the pass dispatches.
    drz = StackOptions(record_rejection_map=True, drizzle=True, drizzle_reject=True)
    assert combine_method(drz, 4) == "drizzle"
    assert _records_rejection_map(drz, 4) is True
    assert _records_rejection_map(drz, 3) is False
    from dataclasses import replace
    assert _records_rejection_map(replace(drz, drizzle_reject=False), 12) is False
    # And asking for no map at all is still the first word on the subject.
    assert _records_rejection_map(
        StackOptions(record_rejection_map=False), 50) is False
