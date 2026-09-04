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
    _min_max_reject_runs,
    _records_rejection_map,
    combine_method,
    estimate_stack,
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


def _build_project(tmp_path, n_frames: int, *, with_quality: bool = False) -> Project:
    """A small solved project. ``with_quality`` stamps *varying* QC metrics, so
    quality weighting has something to bite on (frames missing every metric all
    weigh 1.0, and the WGT* provenance is then absent for a reason that has
    nothing to do with which combine ran)."""
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
            fwhm_px=(3.0 + 0.5 * i) if with_quality else None,
            star_count=(120 - 8 * i) if with_quality else None,
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


# --- The *other* mirror of the same gate: "did the min/max path run?" ----------
# ``min_max_reject and not drizzle and n >= 3`` was written out at seven further
# sites — the memory estimate and OOM guard's ``reject_arrays``, and
# ``weights_applied``, which decides whether the finished stack *claims* its
# quality weighting was honoured. They now ask ``combine_method`` too; these are
# the tests that the answer still describes what the run does.


@pytest.mark.parametrize("n", [0, 1, 2, 3, 4, 12])
@pytest.mark.parametrize("opts", [
    {},
    {"min_max_reject": True},
    {"sigma_clip": False, "min_max_reject": True},
    {"sigma_clip": True, "min_max_reject": True},
    {"drizzle": True, "min_max_reject": True},
    {"drizzle": True, "min_max_reject": True, "sigma_clip": True},
    {"min_max_reject": False, "sigma_clip": False},
])
def test_min_max_reject_runs_is_the_dispatchers_own_answer(n, opts):
    o = StackOptions(**opts)
    assert _min_max_reject_runs(o, n) is (combine_method(o, n) == "min-max-reject")


def _stack_weight_cards(tmp_path, n_frames: int, **overrides) -> dict:
    """The WGT* provenance cards off a finished, quality-weighted master."""
    from astropy.io import fits

    proj = _build_project(tmp_path, n_frames, with_quality=True)
    try:
        result = run_stack(proj, StackOptions(
            **{**_BASE_OPTS, "quality_weighted": True, **overrides}))
    finally:
        proj.close()
    with fits.open(result.fits_path) as hdul:
        header = dict(hdul[0].header)
    return {k: header[k] for k in ("WGTMODE", "WGTSKIP") if k in header}


@pytest.mark.parametrize(("n", "opts"), [
    (2, {"sigma_clip": False, "min_max_reject": True}),  # below the gate → mean
    (3, {"sigma_clip": False, "min_max_reject": True}),  # …and min/max at 3
    (4, {}),                                             # κ-σ honours weights
    (4, {"sigma_clip": True, "min_max_reject": True}),   # min/max wins over κ-σ
    (4, {"drizzle": True, "drizzle_scale": 1.0,          # drizzle wins over both
         "min_max_reject": True}),
])
def test_the_weighting_claim_matches_the_combine_that_ran(tmp_path, n, opts):
    """A stack must not claim weighting was honoured on the one path that ignores it.

    The min/max order-statistic combine picks by rank, so its per-frame weights
    never touch a pixel — ``WGTSKIP`` says so, and ``WGTMODE`` must be absent.
    Every other combine applies them. This is the same question ``REJMODE``
    answers above, asked of the sentence the History Info card shows a user.
    """
    cards = _stack_weight_cards(tmp_path, n, **opts)
    ran_min_max = combine_method(StackOptions(**opts), n) == "min-max-reject"
    assert ("WGTSKIP" in cards) is ran_min_max, cards
    assert ("WGTMODE" in cards) is not ran_min_max, cards


@pytest.mark.parametrize(("n", "opts"), [
    (2, {"sigma_clip": False, "min_max_reject": True}),
    (3, {"sigma_clip": False, "min_max_reject": True}),
    (4, {}),
    (4, {"sigma_clip": True, "min_max_reject": True}),
])
def test_the_estimate_charges_reject_planes_only_when_min_max_runs(tmp_path, n, opts):
    """The pre-run memory estimate charges the accumulator's extra canvas planes
    exactly when the run would allocate them — i.e. when the min/max combine is
    the one that dispatches. Measured as a *difference* against k=1, so it reads
    the charged planes rather than the whole peak.
    """
    proj = _build_project(tmp_path, n)
    try:
        base = estimate_stack(proj, StackOptions(**{**opts, "min_max_reject_count": 1}))
        deep = estimate_stack(proj, StackOptions(**{**opts, "min_max_reject_count": 4}))
    finally:
        proj.close()
    ran_min_max = combine_method(StackOptions(**opts), n) == "min-max-reject"
    assert (deep.peak_bytes > base.peak_bytes) is ran_min_max, (
        n, opts, base.peak_bytes, deep.peak_bytes)
