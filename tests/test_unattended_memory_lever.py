"""The non-drizzle memory lever a walk-away run may take instead of refusing.

The memory guard's job is to refuse a stack that would OOM-kill the container
rather than let it try — and when a watching user is there, refusing is the right
answer: the message names the one lever that would fit and they click it. Nobody
reads it at 3 a.m., so on the **unattended** path a refusal means a target that
made a picture yesterday simply stops.

v0.281.0 taught the drizzle half of that to take its lever (a smaller
super-resolution scale) instead. This is the non-drizzle half, and it is the
safer of the two: the lever is dropping the *extra* outlier passes — k>1 back to
the proven single min/max drop — which changes nothing about the picture's size,
shape or file, only how much multi-trail rejection it got. The boundary these
tests exist to hold is that it stays exactly that narrow: an attended run still
refuses, a run that fits is untouched, a canvas no lever can rescue still
refuses, and the mosaic-cropping lever is still never taken on its own.
"""

from __future__ import annotations

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack import stacker as st  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402


def _build_project(tmp_path, n_frames: int = 5) -> Project:
    """A small solved project the stacker can run end to end."""
    proj = Project.create(tmp_path / "p", name="unattended_lever")
    raws = tmp_path / "raws"
    raws.mkdir()
    for i in range(n_frames):
        path = write_seestar_fits(
            raws / f"f{i}.fit", add_wcs=True, seed=7, noise_seed=400 + i,
            n_stars=8,
        )
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=480, height_px=320, bayer_pattern="RGGB",
            wcs_json=make_synth_wcs_text(),
            ra_center_deg=83.6, dec_center_deg=-5.4,
        ))
    return proj


def _opts(**overrides) -> StackOptions:
    base = dict(
        drizzle=False, min_max_reject=True, min_max_reject_count=3,
        # ``auto_reject`` would re-decide the method from the frame count, which
        # is a different question from the one under test.
        auto_reject=False, sigma_clip=False,
        background_flatten=False, suppress_hot_pixels=False, max_workers=2,
    )
    base.update(overrides)
    return StackOptions(**base)


def _budget_between_k_gb(shape, low: int, high: int) -> float:
    """A budget (GB) fitting a k=``low`` min/max stack but not a k=``high`` one."""
    lo, _ = st._estimate_peak_bytes(
        shape, drizzle=False, drizzle_scale=1.0,
        reject_arrays=st._min_max_reject_arrays(low))
    hi, _ = st._estimate_peak_bytes(
        shape, drizzle=False, drizzle_scale=1.0,
        reject_arrays=st._min_max_reject_arrays(high))
    assert lo < hi
    return (lo + hi) / 2 / 1e9


def _canvas(proj) -> tuple[int, int]:
    est = st.estimate_stack(proj, _opts(output_name="probe"))
    return (est.canvas_h, est.canvas_w)


def test_unattended_drops_the_extra_outlier_passes_instead_of_refusing(tmp_path):
    """The gap this closes: a walk-away stack configured for k=3 on a tight
    budget used to raise MemoryError with advice nobody was there to read, so the
    target silently stopped producing pictures — when k=1 would have made one."""
    from astropy.io import fits

    proj = _build_project(tmp_path)
    try:
        gb = _budget_between_k_gb(_canvas(proj), 1, 3)

        # Watched: still refused, with the concrete lever named. Unchanged.
        with pytest.raises(MemoryError, match="lower Extra outlier passes to 1"):
            run_stack(proj, _opts(output_name="watched"), memory_budget_gb=gb)

        # Unattended: a picture instead, with the single min/max drop.
        res = run_stack(proj, _opts(output_name="walkaway", unattended=True),
                        memory_budget_gb=gb)
        assert res.fits_path.exists()
        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
        assert hdr["REJKRQ"] == 3   # what was asked for
        assert hdr["REJKAD"] == 1   # …and what actually ran
        # The pair has to *explain* itself long after the job log has rolled, so
        # the comments must survive the 80-column card intact rather than being
        # silently truncated on the way out.
        assert hdr.comments["REJKAD"].endswith("to fit memory")
        assert hdr.comments["REJKRQ"].endswith("originally requested")
        # The run record persists the count that ran, so a later reprocess
        # rebuilds the same picture rather than re-hitting the same refusal.
        for run in proj.iter_stack_runs():
            if run.output_basename == "walkaway":
                import json

                assert json.loads(run.options_json)["min_max_reject_count"] == 1
                break
        else:  # pragma: no cover — the run must be there
            raise AssertionError("no stack run recorded for the walk-away stack")
    finally:
        proj.close()


def test_the_degraded_picture_is_the_same_shape_as_the_one_asked_for(tmp_path):
    """What makes this lever safe to take unattended: unlike the drizzle-scale
    step, nothing the owner can see about the picture changes — same canvas, same
    pixel grid. Pinned against a healthy-budget k=1 run of the same frames."""
    from astropy.io import fits

    proj = _build_project(tmp_path)
    try:
        gb = _budget_between_k_gb(_canvas(proj), 1, 3)
        degraded = run_stack(proj, _opts(output_name="degraded", unattended=True),
                             memory_budget_gb=gb)
        plain = run_stack(proj, _opts(output_name="plain", min_max_reject_count=1),
                          memory_budget_gb=64.0)
        with fits.open(degraded.fits_path) as a, fits.open(plain.fits_path) as b:
            assert a[0].data.shape == b[0].data.shape
            assert "REJKAD" not in b[0].header  # …and the honest run says nothing
    finally:
        proj.close()


def test_a_run_that_fits_is_never_degraded_and_stamps_nothing(tmp_path):
    """The self-hiding half: on a healthy budget an unattended k=3 run must be
    exactly the run it is today — the requested count, and no card."""
    from astropy.io import fits

    proj = _build_project(tmp_path)
    try:
        res = run_stack(proj, _opts(output_name="fine", unattended=True),
                        memory_budget_gb=64.0)
        with fits.open(res.fits_path) as hdul:
            hdr = hdul[0].header
        assert "REJKAD" not in hdr
        assert "REJKRQ" not in hdr
        for run in proj.iter_stack_runs():
            if run.output_basename == "fine":
                import json

                assert json.loads(run.options_json)["min_max_reject_count"] == 3
                break
        else:  # pragma: no cover — the run must be there
            raise AssertionError("no stack run recorded")
    finally:
        proj.close()


def test_unattended_still_refuses_when_even_one_pass_will_not_fit(tmp_path):
    """Only a canvas the *k=1* stack can hold is degraded. When even the single
    min/max drop is over budget there is no honest picture to make, so the guard
    must still refuse rather than quietly producing something the box can't hold."""
    proj = _build_project(tmp_path)
    try:
        unity, _ = st._estimate_peak_bytes(
            _canvas(proj), drizzle=False, drizzle_scale=1.0,
            reject_arrays=st._min_max_reject_arrays(1))
        with pytest.raises(MemoryError, match="working memory"):
            run_stack(proj, _opts(output_name="hopeless", unattended=True),
                      memory_budget_gb=unity / 2 / 1e9)
    finally:
        proj.close()


def test_a_k1_unattended_run_over_budget_is_never_quietly_rescued(tmp_path):
    """There is no *extra* pass to drop at k=1, so the only remaining lever on a
    single-field stack is one the engine deliberately never takes on its own. The
    refusal has to survive: quietly cropping or re-canvassing someone's field is
    a different order of change from dropping a rejection pass."""
    proj = _build_project(tmp_path)
    try:
        with pytest.raises(MemoryError, match="working memory"):
            run_stack(proj, _opts(output_name="k1", min_max_reject_count=1,
                                  unattended=True),
                      memory_budget_gb=0.000001)
    finally:
        proj.close()
