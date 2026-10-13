"""``run_stack`` taking the automatic drizzle decision for itself.

The pure verdict is pinned in ``tests/test_auto_drizzle.py``; this is the half
that matters to the owner — a walk-away run that *acts* on it: a bigger canvas,
drizzle's own two-pass rejection turned on with it, and the whole decision
stamped into the finished picture's header so it can explain its own size long
after the job log has rolled.

The decision's depth bar is 200 subs on one output pixel, which is the right
number and a terrible test fixture, so most of these runs lower it through the
module constant the decision reads at call time. Everything else — the canvas,
the dither measured off each sub's own WCS, the memory pricing — is the real
thing.

**One of them does not lower it**: ``test_the_real_depth_bar_is_cleared_with_the
_constant_unpatched`` runs the drizzling branch at exactly
``AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL``, on a small sensor rather than a lowered
bar, because "the positive path is tested only with its bar lowered" was a
proven gap in a feature that is **on by default and unattended** — and a
monkeypatched constant cannot show that 200 is a number the code can actually
reach. The price of the real bar is one ~15 s test; the price of not having it
was that nothing in this repo had ever run the branch the owner's install runs.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("drizzle")

from astropy.io import fits  # noqa: E402

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack import autodrizzle  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402
from tests.synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

W, H = 480, 320


def _project(tmp_path, shifts) -> Project:
    """A target whose subs are dithered by ``shifts`` — stars moved on the
    sensor, WCS reference pixel moved with them, so the sky is the same patch."""
    proj = Project.create(tmp_path / "p", name="M_42")
    raws = tmp_path / "raws"
    raws.mkdir()
    for i, shift in enumerate(shifts):
        path = write_seestar_fits(raws / f"f{i}.fit", add_wcs=True,
                                  seed=11, noise_seed=200 + i, n_stars=12,
                                  star_shift=shift)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=W, height_px=H, bayer_pattern="RGGB",
            wcs_json=make_synth_wcs_text(width=W, height=H, crpix_shift=shift),
            ra_center_deg=83.6, dec_center_deg=-5.4, exposure_s=10.0,
        ))
    return proj


def _run(proj, *, _on_auto_drizzle=None, **overrides):
    opts = dict(background_flatten=False, suppress_hot_pixels=False,
                max_workers=2, output_name="out", unattended=True)
    opts.update(overrides)
    return run_stack(proj, StackOptions(**opts),
                     on_auto_drizzle=_on_auto_drizzle)


DITHERED = [(i * 0.37, i * 0.53) for i in range(6)]
PARKED = [(0.0, 0.0)] * 6


def test_a_deep_dithered_unattended_run_drizzles_itself(tmp_path, monkeypatch):
    """The feature, end to end: nobody ticked anything and the picture comes
    back super-resolved, with drizzle's own rejection on and the reason in the
    header.

    Fails before the fix in the way the owner noticed it: the canvas is the
    sensor's own 480×320 and no card says why."""
    monkeypatch.setattr(autodrizzle, "AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL", 5)
    proj = _project(tmp_path, DITHERED)
    res = _run(proj, auto_drizzle=True)
    with fits.open(res.fits_path) as hdul:
        data = np.asarray(hdul[0].data)
        header = dict(hdul[0].header)
    # ×1.5 of the native canvas, which is the whole point.
    assert data.shape[1:] == (int(round(H * 1.5)), int(round(W * 1.5)))
    assert header["ADRZAUTO"] is True
    assert header["ADRZWHY"] == autodrizzle.REASON_DEEP_AND_DITHERED
    assert float(header["ADRZSCL"]) == pytest.approx(1.5)
    assert int(header["ADRZSPP"]) == 6
    assert int(header["ADRZBAR"]) == 5
    assert float(header["ADRZDTH"]) >= autodrizzle.AUTO_DRIZZLE_MIN_DITHER_PX
    # Drizzle's two-pass rejection came with it — an unattended drizzle without
    # it would keep every satellite that slipped past frame QC.
    assert header["STACKER"].startswith("drizzle")
    run = next(iter(proj.iter_stack_runs()))
    stored = json.loads(run.options_json)
    assert stored["drizzle"] is True
    assert stored["drizzle_reject"] is True
    assert float(stored["drizzle_scale"]) == pytest.approx(1.5)
    proj.close()


def test_the_caller_is_told_what_the_drizzle_it_chose_will_cost(
        tmp_path, monkeypatch):
    """``on_auto_drizzle`` fires once, with what it takes to price the run.

    The owner asked to be told how long an automatic drizzle will take and then
    left alone (sign-off item 19, 2026-10-13), and the engine cannot say that
    sentence — the seconds come from his own past runs, which only the webapp
    reads. So it hands the decision out. The two cost classes are the load
    bearing part: they are what separates the runs a rate may be read across,
    and the engine is the only place that knows both without re-resolving
    ``auto_reject`` and the ``drizzle_reject`` affordability check.
    """
    monkeypatch.setattr(autodrizzle, "AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL", 5)
    proj = _project(tmp_path, DITHERED)
    seen = []
    _run(proj, auto_drizzle=True, _on_auto_drizzle=seen.append)
    assert len(seen) == 1
    chosen = seen[0]
    assert chosen.decision.drizzle is True
    assert chosen.decision.reason == autodrizzle.REASON_DEEP_AND_DITHERED
    assert float(chosen.decision.scale) == pytest.approx(1.5)
    assert chosen.n_frames == len(DITHERED)
    # The **pre-drizzle** canvas, which is what the owner's past runs were
    # measured on — not the ×1.5 grid this one will allocate.
    assert chosen.canvas_px == W * H
    assert chosen.cost_class == "drizzle+reject"
    # …and what this very run would have been without the automatic drizzle,
    # which is the "a plain stack would take about …" half of the sentence.
    assert chosen.plain_cost_class not in ("drizzle", "drizzle+reject")
    proj.close()


def test_a_run_that_does_not_drizzle_tells_the_caller_nothing(
        tmp_path, monkeypatch):
    """No note on a run that stayed plain — the sentence is about a drizzle, and
    the Jobs row must stay as quiet as it is today on every other job."""
    monkeypatch.setattr(autodrizzle, "AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL", 5)
    seen = []
    proj = _project(tmp_path, PARKED)
    _run(proj, auto_drizzle=True, _on_auto_drizzle=seen.append)
    assert seen == []
    proj.close()
    # …and likewise with the posture never written at all.
    seen.clear()
    proj = _project(tmp_path / "b", DITHERED)
    _run(proj, auto_drizzle=False, _on_auto_drizzle=seen.append)
    assert seen == []
    proj.close()


def test_a_note_that_raises_does_not_cost_the_stack(tmp_path, monkeypatch):
    """A sentence on a job row must never be able to fail a stack that is
    otherwise fine — the rule every side note in this app follows."""
    monkeypatch.setattr(autodrizzle, "AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL", 5)
    proj = _project(tmp_path, DITHERED)

    def _boom(_chosen):
        raise RuntimeError("no")

    res = _run(proj, auto_drizzle=True, _on_auto_drizzle=_boom)
    with fits.open(res.fits_path) as hdul:
        # Still drizzled, still finished.
        assert np.asarray(hdul[0].data).shape[1:] == (int(round(H * 1.5)),
                                                      int(round(W * 1.5)))
    proj.close()


def test_with_the_posture_off_nothing_changes(tmp_path, monkeypatch):
    """The fail-before control, and the §9 promise: an existing install that
    never writes the posture stacks byte-for-byte as it does today."""
    monkeypatch.setattr(autodrizzle, "AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL", 5)
    proj = _project(tmp_path, DITHERED)
    res = _run(proj, auto_drizzle=False)
    with fits.open(res.fits_path) as hdul:
        assert np.asarray(hdul[0].data).shape[1:] == (H, W)
        header = dict(hdul[0].header)
    assert "ADRZAUTO" not in header
    assert "ADRZWHY" not in header
    proj.close()


def test_an_explicit_drizzle_is_never_overruled(tmp_path, monkeypatch):
    """``auto_drizzle`` only ever *adds* a drizzle. A run that already asked for
    one keeps its own scale — the posture must not quietly re-scale a stack the
    owner set up."""
    monkeypatch.setattr(autodrizzle, "AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL", 5)
    proj = _project(tmp_path, DITHERED)
    res = _run(proj, auto_drizzle=True, drizzle=True, drizzle_scale=1.0)
    with fits.open(res.fits_path) as hdul:
        assert np.asarray(hdul[0].data).shape[1:] == (H, W)
        assert "ADRZAUTO" not in dict(hdul[0].header)
    proj.close()


def test_subs_that_never_moved_are_not_drizzled(tmp_path, monkeypatch):
    """Without sub-pixel variety drizzle adds a grid, not detail — and the
    picture says so rather than coming back quietly the same size."""
    monkeypatch.setattr(autodrizzle, "AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL", 5)
    proj = _project(tmp_path, PARKED)
    res = _run(proj, auto_drizzle=True)
    with fits.open(res.fits_path) as hdul:
        assert np.asarray(hdul[0].data).shape[1:] == (H, W)
        header = dict(hdul[0].header)
    assert header["ADRZAUTO"] is False
    assert header["ADRZWHY"] == autodrizzle.REASON_TOO_LITTLE_DITHER
    assert float(header["ADRZDTH"]) == pytest.approx(0.0, abs=1e-6)
    proj.close()


def test_a_shallow_run_is_not_drizzled_and_says_how_short_it_fell(tmp_path):
    """The real bar, unpatched: six subs against 200 on a pixel."""
    proj = _project(tmp_path, DITHERED)
    res = _run(proj, auto_drizzle=True)
    with fits.open(res.fits_path) as hdul:
        assert np.asarray(hdul[0].data).shape[1:] == (H, W)
        header = dict(hdul[0].header)
    assert header["ADRZAUTO"] is False
    assert header["ADRZWHY"] == autodrizzle.REASON_TOO_FEW_SAMPLES
    assert int(header["ADRZSPP"]) == 6
    assert int(header["ADRZBAR"]) == autodrizzle.AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL
    # Nothing was measured about the dither: the depth already answered it, and
    # measuring it is a WCS read per sub.
    assert "ADRZDTH" not in header
    proj.close()


def test_the_real_depth_bar_is_cleared_with_the_constant_unpatched(tmp_path):
    """The positive path at the number that ships, with nothing patched.

    Every other drizzling run in this file lowers
    ``AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL`` to 5, and that was filed as a proven
    gap: a feature that is on by default and decides for itself on a walk-away
    night had **no** test that the branch it takes is reachable at 200, which is
    a different claim from "the branch works when the bar is 5". A lowered
    constant cannot make it, and neither can the bundled samples — ``--mosaic``
    and ``--big`` are six subs per pointing and ``--deep`` is not stacked.

    So the fixture pays the bar instead of moving it: a small sensor and exactly
    ``AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL`` subs on one pointing, which is the
    depth a single field reports (the canvas is one frame, so
    ``samples_per_output_pixel`` returns ``None`` and the frame count *is* the
    per-pixel depth). The frame count is read from the constant, so the day the
    bar moves this test follows it rather than quietly landing under it.

    ~15 s, and deliberately the only one of its kind here."""
    n = autodrizzle.AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL
    w, h = 160, 120
    proj = Project.create(tmp_path / "deep", name="M_42")
    raws = tmp_path / "deep_raws"
    raws.mkdir()
    for i in range(n):
        shift = ((i * 0.37) % 2.0, (i * 0.53) % 2.0)
        path = write_seestar_fits(raws / f"d{i}.fit", width=w, height=h, add_wcs=True,
                                  seed=11, noise_seed=400 + i, n_stars=10,
                                  star_shift=shift)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=w, height_px=h, bayer_pattern="RGGB",
            wcs_json=make_synth_wcs_text(width=w, height=h, crpix_shift=shift),
            ra_center_deg=83.6, dec_center_deg=-5.4, exposure_s=10.0,
        ))
    res = run_stack(proj, StackOptions(
        background_flatten=False, suppress_hot_pixels=False, max_workers=2,
        output_name="deep", unattended=True, auto_drizzle=True))
    with fits.open(res.fits_path) as hdul:
        data = np.asarray(hdul[0].data)
        header = dict(hdul[0].header)
    assert data.shape[1:] == (int(round(h * 1.5)), int(round(w * 1.5)))
    assert header["ADRZAUTO"] is True
    assert header["ADRZWHY"] == autodrizzle.REASON_DEEP_AND_DITHERED
    # The bar in the header is the shipped constant, not a patched one — which
    # is the whole point of this test existing beside the others.
    assert int(header["ADRZBAR"]) == autodrizzle.AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL
    assert int(header["ADRZBAR"]) == 200
    assert int(header["ADRZSPP"]) >= int(header["ADRZBAR"])
    assert float(header["ADRZSCL"]) == pytest.approx(1.5)
    assert float(header["ADRZDTH"]) >= autodrizzle.AUTO_DRIZZLE_MIN_DITHER_PX
    assert header["STACKER"].startswith("drizzle")
    proj.close()


def test_a_canvas_with_no_room_in_the_budget_declines_rather_than_refusing(
        tmp_path, monkeypatch):
    """The memory half. A budget that can hold the ordinary canvas but not even
    the smallest offered drizzle must leave the run making its ordinary picture
    — never raise, and never come back with nothing.

    The budget is computed from the engine's own pricing rather than guessed, so
    the test cannot drift into "the native canvas didn't fit either" (which would
    pass for the wrong reason, by refusing the whole run)."""
    from seestack.stack.stacker import _estimate_peak_bytes

    monkeypatch.delenv("ASTROSTACK_MAX_STACK_GB", raising=False)
    monkeypatch.setattr(autodrizzle, "AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL", 5)
    native, _ = _estimate_peak_bytes((H, W), drizzle=False, drizzle_scale=1.0)
    smallest, _ = _estimate_peak_bytes(
        (H, W), drizzle=True, drizzle_reject=True,
        drizzle_scale=autodrizzle.AUTO_DRIZZLE_MIN_SCALE)
    assert native < smallest
    budget_gb = (native + (smallest - native) / 2) / 1e9

    proj = _project(tmp_path, DITHERED)
    res = run_stack(
        proj,
        StackOptions(background_flatten=False, suppress_hot_pixels=False,
                     max_workers=2, output_name="tight", unattended=True,
                     auto_drizzle=True),
        memory_budget_gb=budget_gb)
    with fits.open(res.fits_path) as hdul:
        assert np.asarray(hdul[0].data).shape[1:] == (H, W)
        header = dict(hdul[0].header)
    assert header["ADRZAUTO"] is False
    assert header["ADRZWHY"] == autodrizzle.REASON_NO_ROOM_IN_BUDGET
    proj.close()
