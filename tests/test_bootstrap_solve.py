"""Stack-then-solve bootstrap — pure logic + orchestration, no real ASTAP.

The one ASTAP call is injected (``deep_solver``), so these tests validate the
registration → integration → WCS-propagation → DB-write pipeline end to end
against synthetic ground truth without needing a solver install.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("skimage")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.solve.bootstrap import (  # noqa: E402
    bootstrap_solve,
    integrate_deep_image,
    propagate_wcs,
    register_members,
)
from seestack.solve.runner import SolveResult  # noqa: E402
from tests.synth import make_star_field, make_synth_wcs_text, write_seestar_fits  # noqa: E402

W, H = 240, 160
PIXSCALE = 5.0
RA0, DEC0 = 83.6, -5.4

# Small distinct dithers (dx, dy) — within a star box so make_star_field shifts
# the whole field cleanly. Member 0 is the reference (no shift).
SHIFTS = [(0, 0), (2, 1), (-2, 1), (1, -2), (2, 2), (-1, -2), (3, -1), (-2, -2)]


def _gray_from_shift(dx, dy, *, peak_noise=50.0, seed=7):
    """A background-flattened luminance frame with the field dithered by (dx,dy)."""
    from seestack.io.fits_loader import bilinear_debayer

    mosaic = make_star_field(
        width=W, height=H, n_stars=25, seed=seed, sky_noise=peak_noise,
        star_shift=(float(dx), float(dy)), noise_seed=seed + 100 + dx * 3 + dy,
    )
    rgb = bilinear_debayer(mosaic.astype(np.float32))
    gray = rgb.mean(axis=2)
    flat = np.clip(gray - float(np.median(gray)), 0.0, None)
    return flat.astype(np.float32)


def test_register_members_recovers_the_dither_shift():
    grays = [_gray_from_shift(dx, dy) for dx, dy in SHIFTS]
    shifts = register_members(grays, ref_index=0)
    assert shifts[0] == (0.0, 0.0)
    for (dx, dy), s in zip(SHIFTS[1:], shifts[1:], strict=True):
        assert s is not None
        # phase correlation returns (row, col) = (-dy, -dx) to align onto ref.
        assert s[0] == pytest.approx(-dy, abs=1.0)
        assert s[1] == pytest.approx(-dx, abs=1.0)


def test_register_members_rejects_out_of_bounds_shift():
    grays = [_gray_from_shift(0, 0), _gray_from_shift(2, 1)]
    shifts = register_members(grays, ref_index=0, max_shift_px=0.5)
    assert shifts[0] == (0.0, 0.0)
    assert shifts[1] is None  # a 2px shift exceeds the 0.5px cap → skipped


def test_integrate_deep_image_averages_down_the_noise():
    # Faint field: many subs, low star peak, heavy sky noise → the mean should
    # cut the per-pixel noise ~sqrt(N) vs a single sub (the whole point).
    grays = [_gray_from_shift(dx, dy, peak_noise=120.0, seed=11) for dx, dy in SHIFTS]
    shifts = register_members(grays, ref_index=0)
    deep = integrate_deep_image(grays, shifts, ref_index=0)
    assert deep.shape == grays[0].shape
    # Measure background noise on a star-free corner of the covered region.
    corner = np.s_[H // 2 - 20 : H // 2 + 20, W // 2 - 20 : W // 2 + 20]
    single_noise = float(np.std(grays[0][corner]))
    deep_noise = float(np.std(deep[corner]))
    assert deep_noise < single_noise  # averaging reduced the noise


def test_propagate_wcs_matches_ground_truth_crpix():
    # The deep image solved to the reference sub's true WCS (no shift).
    base = make_synth_wcs_text(
        width=W, height=H, ra_center_deg=RA0, dec_center_deg=DEC0,
        pixscale_arcsec=PIXSCALE, crpix_shift=(0.0, 0.0),
    )
    # Shifts as phase correlation would report them: (-dy, -dx).
    shifts = [(-dy, -dx) for dx, dy in SHIFTS]
    out = propagate_wcs(base, shifts, ref_index=0)
    from seestack.io.wcs_io import wcs_from_text

    for (dx, dy), wtext in zip(SHIFTS, out, strict=True):
        w = wcs_from_text(wtext)
        truth = wcs_from_text(make_synth_wcs_text(
            width=W, height=H, ra_center_deg=RA0, dec_center_deg=DEC0,
            pixscale_arcsec=PIXSCALE, crpix_shift=(float(dx), float(dy)),
        ))
        assert np.allclose(w.wcs.crpix, truth.wcs.crpix, atol=1e-6)


def _make_project_with_faint_subs(tmp_path, n=8, add_wcs_truth=False):
    """A project of ``n`` accepted, unsolved, dithered synth subs on disk."""
    proj = Project.create(tmp_path / "proj", name="Faint")
    truth = {}
    for i in range(n):
        dx, dy = SHIFTS[i]
        p = tmp_path / f"sub_{i:03d}.fit"
        write_seestar_fits(
            p, width=W, height=H, n_stars=25, seed=7,
            star_shift=(float(dx), float(dy)), noise_seed=200 + i,
        )
        fid = proj.add_frame(FrameRow(source_path=str(p)))
        truth[fid] = (dx, dy)
    return proj, truth


def _ref_wcs_solver(*args, **kwargs):
    """Injected deep solver: pretend ASTAP solved the deep image to the reference
    sub's true (unshifted) WCS."""
    wcs_text = make_synth_wcs_text(
        width=W, height=H, ra_center_deg=RA0, dec_center_deg=DEC0,
        pixscale_arcsec=PIXSCALE, crpix_shift=(0.0, 0.0),
    )
    return SolveResult(
        frame_id=-1, fits_path="deep.fits", solved=True, wcs_text=wcs_text,
        ra_center_deg=RA0, dec_center_deg=DEC0, pixscale_arcsec=PIXSCALE,
        rotation_deg=0.0, error=None,
    )


def test_bootstrap_solve_rescues_and_propagates(tmp_path):
    proj, truth = _make_project_with_faint_subs(tmp_path, n=8)
    try:
        res = bootstrap_solve(proj, min_frames=4, deep_solver=_ref_wcs_solver)
        assert res.engaged
        assert res.deep_solved
        assert res.n_propagated >= 6  # most subs rescued
        # Every rescued frame now carries a WCS whose CRPIX matches its true dither.
        from seestack.io.wcs_io import wcs_from_text
        for f in proj.iter_frames():
            if f.wcs_json is None:
                continue
            dx, dy = truth[f.id]
            w = wcs_from_text(f.wcs_json)
            truth_w = wcs_from_text(make_synth_wcs_text(
                width=W, height=H, ra_center_deg=RA0, dec_center_deg=DEC0,
                pixscale_arcsec=PIXSCALE, crpix_shift=(float(dx), float(dy)),
            ))
            # Registration is integer-pixel, so allow ~1.5px slack.
            assert np.allclose(w.wcs.crpix, truth_w.wcs.crpix, atol=1.5)
            assert f.ra_center_deg is not None and f.dec_center_deg is not None
    finally:
        proj.close()


def test_bootstrap_does_not_engage_with_too_few_unsolved(tmp_path):
    proj, _ = _make_project_with_faint_subs(tmp_path, n=3)
    try:
        res = bootstrap_solve(proj, min_frames=8, deep_solver=_ref_wcs_solver)
        assert not res.engaged
        assert not res.deep_solved
        assert "too few unsolved" in res.reason
        assert all(f.wcs_json is None for f in proj.iter_frames())
    finally:
        proj.close()


def test_bootstrap_does_not_engage_when_enough_already_solved(tmp_path):
    proj, _ = _make_project_with_faint_subs(tmp_path, n=8)
    try:
        # Mark 4 as already solved.
        for i, f in enumerate(proj.iter_frames()):
            if i < 4:
                proj.update_frame(f.id, wcs_json="dummy")
        res = bootstrap_solve(proj, min_frames=4, deep_solver=_ref_wcs_solver)
        assert not res.engaged
        assert "already solved" in res.reason
    finally:
        proj.close()


def test_bootstrap_leaves_everything_untouched_when_deep_solve_fails(tmp_path):
    proj, _ = _make_project_with_faint_subs(tmp_path, n=8)

    def _failing_solver(*args, **kwargs):
        return SolveResult(
            frame_id=-1, fits_path="deep.fits", solved=False, wcs_text=None,
            ra_center_deg=None, dec_center_deg=None, pixscale_arcsec=None,
            rotation_deg=None, error="no solution",
        )

    try:
        res = bootstrap_solve(proj, min_frames=4, deep_solver=_failing_solver)
        assert res.engaged
        assert not res.deep_solved
        assert res.n_propagated == 0
        assert all(f.wcs_json is None for f in proj.iter_frames())
    finally:
        proj.close()


def test_bootstrap_skips_deliberately_rejected_subs(tmp_path):
    proj, _ = _make_project_with_faint_subs(tmp_path, n=8)
    try:
        # Reject one sub for a real reason — it must never be rescued/propagated.
        rejected_id = None
        for i, f in enumerate(proj.iter_frames()):
            if i == 2:
                proj.update_frame(f.id, accept=False, reject_reason="user")
                rejected_id = f.id
                break
        res = bootstrap_solve(proj, min_frames=4, deep_solver=_ref_wcs_solver)
        assert res.deep_solved
        rej = proj.get_frame(rejected_id)
        assert rej.wcs_json is None  # rejected sub stays untouched
        assert rej.reject_reason == "user"
    finally:
        proj.close()


def test_run_qc_and_solve_wires_bootstrap_flag(tmp_path, monkeypatch):
    """The scanner runs the bootstrap only when asked, and threads its summary."""
    import seestack.solve.bootstrap as bootstrap_mod
    from seestack.io.scanner import run_qc_and_solve
    from seestack.solve.bootstrap import BootstrapResult

    calls = {"n": 0}

    def _fake_bootstrap(project, **kwargs):
        calls["n"] += 1
        return BootstrapResult(engaged=True, deep_solved=True, n_propagated=5)

    monkeypatch.setattr(bootstrap_mod, "bootstrap_solve", _fake_bootstrap)

    proj, _ = _make_project_with_faint_subs(tmp_path, n=8)
    try:
        # Off → bootstrap never called.
        summary = run_qc_and_solve(
            proj, run_qc=False, run_solve=True, serial=True,
            bootstrap_solve=False,
        )
        assert calls["n"] == 0
        assert "bootstrap_engaged" not in summary

        # On → bootstrap called, summary carries its outcome.
        summary = run_qc_and_solve(
            proj, run_qc=False, run_solve=True, serial=True,
            bootstrap_solve=True,
        )
        assert calls["n"] == 1
        assert summary["bootstrap_engaged"] is True
        assert summary["bootstrap_solved"] is True
        assert summary["bootstrap_propagated"] == 5
    finally:
        proj.close()


def test_bootstrap_clears_stale_solve_failed_reason_on_rescue(tmp_path):
    proj, _ = _make_project_with_faint_subs(tmp_path, n=8)
    try:
        target_id = None
        for i, f in enumerate(proj.iter_frames()):
            if i == 1:
                proj.update_frame(f.id, reject_reason="solve_failed:no solution")
                target_id = f.id
                break
        res = bootstrap_solve(proj, min_frames=4, deep_solver=_ref_wcs_solver)
        assert res.deep_solved
        frame = proj.get_frame(target_id)
        assert frame.wcs_json is not None
        assert frame.reject_reason is None  # stale solve_failed cleared
    finally:
        proj.close()
