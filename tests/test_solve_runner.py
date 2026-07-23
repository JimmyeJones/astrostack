"""Solve runner — works without a real ASTAP install via mock."""

from unittest.mock import patch

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.solve.astap import (  # noqa: E402
    SOLVE_SETUP_ASTAP_MISSING,
    SOLVE_SETUP_NO_DATABASE,
    ASTAPResult,
    ASTAPSolver,
    classify_solve_setup_error,
)
from seestack.solve.runner import (  # noqa: E402
    SolveResult,
    apply_solve_result_to_db,
    build_solve_arglist,
    solve_one,
)


def test_build_solve_arglist_skips_solved(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # Create a fake file so the path-exists check passes.
        f1 = tmp_path / "a.fit"
        f1.write_bytes(b"")
        f2 = tmp_path / "b.fit"
        f2.write_bytes(b"")
        id1 = proj.add_frame(FrameRow(source_path=str(f1)))
        id2 = proj.add_frame(FrameRow(source_path=str(f2)))
        # Mark id1 as already solved.
        proj.update_frame(id1, wcs_json="dummy")

        args = build_solve_arglist(proj)
        ids = [a[0] for a in args]
        assert id1 not in ids
        assert id2 in ids
    finally:
        proj.close()


def test_build_solve_arglist_skips_deliberately_rejected_frames(tmp_path):
    """A frame the user/QC/streak/auto-grade rejected can never enter the stack
    (``run_stack`` combines only accepted+solved frames), so it must not be
    re-plate-solved on every scan — that's pure wasted ASTAP time.

    Regression: ``build_solve_arglist`` offered every frame without a ``wcs_json``
    with no ``accept`` filter, so a rejected sub was re-solved from scratch each
    scan even though it can never contribute to a stack.
    """
    proj = Project.create(tmp_path / "p", name="t")
    try:
        paths = []
        for name in ("a.fit", "b.fit", "c.fit"):
            p = tmp_path / name
            p.write_bytes(b"")
            paths.append(p)
        accepted = proj.add_frame(FrameRow(source_path=str(paths[0])))
        user_reject = proj.add_frame(FrameRow(source_path=str(paths[1])))
        grade_reject = proj.add_frame(FrameRow(source_path=str(paths[2])))
        # Deliberate rejections (a manual reject and an auto-grade drop) — out for
        # good, so never worth solving.
        proj.update_frame(user_reject, accept=False, reject_reason="user")
        proj.update_frame(grade_reject, accept=False, reject_reason="auto:grade:fwhm")

        ids = [a[0] for a in build_solve_arglist(proj)]
        assert accepted in ids               # accepted-unsolved → still offered
        assert user_reject not in ids        # rejected → skipped (fail-before: offered)
        assert grade_reject not in ids
    finally:
        proj.close()


def test_build_solve_arglist_still_offers_solve_failed_frames(tmp_path):
    """A frame whose *only* mark against it is a prior ``solve_failed:`` reason is
    a genuine retry candidate (e.g. once the star database is installed), so it
    must keep being offered even though ``accept`` may be 0 — skipping it would
    strand a first-light user's whole library as un-solvable."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        pa = tmp_path / "a.fit"
        pa.write_bytes(b"")
        pb = tmp_path / "b.fit"
        pb.write_bytes(b"")
        retry = proj.add_frame(FrameRow(source_path=str(pa)))
        rejected = proj.add_frame(FrameRow(source_path=str(pb)))
        # A prior solve failure that left the frame accepted (the usual case) — and,
        # defensively, even if some path set accept=0, a solve_failed:-only frame is
        # still a retry candidate.
        proj.update_frame(retry, accept=False, reject_reason="solve_failed:no star database")
        proj.update_frame(rejected, accept=False, reject_reason="user")

        ids = [a[0] for a in build_solve_arglist(proj)]
        assert retry in ids                  # solve_failed: → still retried
        assert rejected not in ids
    finally:
        proj.close()


def test_solve_one_handles_missing_astap(tmp_path):
    """If ASTAP isn't installed, solve_one returns a clean error result."""
    fits = tmp_path / "x.fit"
    fits.write_bytes(b"")
    # find_astap looks at PATH and standard install locations. With a bogus
    # explicit path we force "not found".
    with patch("seestack.solve.runner.ASTAPSolver", side_effect=__import__(
            "seestack.solve.astap", fromlist=["ASTAPError"]).ASTAPError("astap missing")):
        result = solve_one(1, str(fits), astap_path=str(tmp_path / "nope.exe"))
    assert isinstance(result, SolveResult)
    assert result.solved is False
    assert result.error is not None
    assert "astap" in result.error.lower()


def test_solve_one_with_mock_solver(tmp_path):
    """End-to-end with a mocked ASTAPSolver that returns a successful result."""
    fits = tmp_path / "x.fit"
    fits.write_bytes(b"")
    sidecar = tmp_path / "x.wcs"
    sidecar.write_bytes(b"")  # presence is enough for the wrapper

    fake_result = ASTAPResult(
        fits_path=fits,
        wcs_sidecar_path=sidecar,
        ra_center_deg=83.63,
        dec_center_deg=-5.39,
        pixscale_arcsec=2.5,
        rotation_deg=12.0,
        solved=True,
        log_tail="",
    )

    class FakeSolver:
        def __init__(self, *a, **kw):
            pass

        def solve(self, _path, **_kw):  # accepts ra_hint_deg/dec_hint_deg/radius_deg
            return fake_result

    with patch("seestack.solve.runner.ASTAPSolver", FakeSolver), \
         patch("seestack.io.wcs_io.wcs_text_from_sidecar", return_value="CRVAL1=1.0"):
        result = solve_one(7, str(fits))

    assert result.solved is True
    assert result.frame_id == 7
    assert result.ra_center_deg == 83.63
    assert result.wcs_text == "CRVAL1=1.0"
    assert result.error is None


def test_solve_one_backfills_centre_from_wcs_when_ini_unparseable(tmp_path):
    """ASTAP solved (valid ``.wcs``) but its ``.ini`` didn't yield a centre → the
    centre is recovered from the ``.wcs`` sidecar rather than left None.

    Regression: ``_parse_astap_ini`` raising (missing/garbled ``.ini``) left
    ``ra/dec_center_deg`` None while ``solved`` stayed True and the WCS was valid,
    so the frame stacked but was silently barred from being the reference frame and
    from seeding sibling plate-solve hints, and was never re-offered to fill it in.
    The CRVAL centre lives in the ``.wcs`` sidecar, so it must be backfilled."""
    pytest.importorskip("astropy")
    import numpy as np
    from astropy.wcs import WCS

    fits = tmp_path / "x.fit"
    fits.write_bytes(b"")
    sidecar = tmp_path / "x.wcs"
    sidecar.write_bytes(b"")  # presence is enough for the wrapper

    # A real WCS text blob whose CRVAL is the frame centre (as ASTAP writes it).
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [149.75, 69.06]
    w.wcs.crpix = [960.5, 540.5]
    w.wcs.cdelt = np.array([-2.5 / 3600.0, 2.5 / 3600.0])
    wcs_text = str(w.to_header(relax=True))

    # ASTAP "solved" but the .ini parse failed → centre came back None.
    fake_result = ASTAPResult(
        fits_path=fits, wcs_sidecar_path=sidecar,
        ra_center_deg=None, dec_center_deg=None,
        pixscale_arcsec=None, rotation_deg=None,
        solved=True, log_tail="",
    )

    class FakeSolver:
        def __init__(self, *a, **kw):
            pass

        def solve(self, _path, **_kw):
            return fake_result

    with patch("seestack.solve.runner.ASTAPSolver", FakeSolver), \
         patch("seestack.io.wcs_io.wcs_text_from_sidecar", return_value=wcs_text):
        result = solve_one(9, str(fits))

    assert result.solved is True
    assert result.wcs_text == wcs_text
    # The centre is recovered from the WCS, not left None.
    assert result.ra_center_deg == pytest.approx(149.75, abs=1e-6)
    assert result.dec_center_deg == pytest.approx(69.06, abs=1e-6)


def test_solve_one_keeps_astap_center_when_present(tmp_path):
    """When ASTAP's .ini yields a centre, it is used verbatim (no WCS override)."""
    fits = tmp_path / "x.fit"
    fits.write_bytes(b"")
    sidecar = tmp_path / "x.wcs"
    sidecar.write_bytes(b"")

    fake_result = ASTAPResult(
        fits_path=fits, wcs_sidecar_path=sidecar,
        ra_center_deg=83.63, dec_center_deg=-5.39,
        pixscale_arcsec=2.5, rotation_deg=12.0, solved=True, log_tail="",
    )

    class FakeSolver:
        def __init__(self, *a, **kw):
            pass

        def solve(self, _path, **_kw):
            return fake_result

    # Even if the .wcs disagreed, an ASTAP-provided centre wins (no backfill).
    with patch("seestack.solve.runner.ASTAPSolver", FakeSolver), \
         patch("seestack.io.wcs_io.wcs_text_from_sidecar", return_value="CRVAL1 = 999.0"):
        result = solve_one(7, str(fits))

    assert result.ra_center_deg == 83.63
    assert result.dec_center_deg == -5.39


def test_solve_one_backfilled_centre_makes_frame_reference_eligible(tmp_path):
    """The backfilled centre flows through to the DB so the frame is reference-
    and sibling-hint-eligible (both require non-None centres)."""
    from seestack.solve.runner import fallback_solve_hint

    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        apply_solve_result_to_db(proj, SolveResult(
            frame_id=fid, fits_path="x.fit", solved=True,
            wcs_text="CRVAL1=1.0", ra_center_deg=149.75, dec_center_deg=69.06,
            pixscale_arcsec=None, rotation_deg=None, error=None,
        ))
        f = proj.get_frame(fid)
        assert f is not None
        assert f.ra_center_deg == pytest.approx(149.75)
        assert f.dec_center_deg == pytest.approx(69.06)
        # A non-None centre is what fallback_solve_hint needs to seed siblings.
        assert fallback_solve_hint([f]) is not None
    finally:
        proj.close()


def test_apply_solve_result_writes_db(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        result = SolveResult(
            frame_id=fid, fits_path="x.fit", solved=True,
            wcs_text="CRVAL1=1.0", ra_center_deg=83.63, dec_center_deg=-5.39,
            pixscale_arcsec=2.5, rotation_deg=12.0, error=None,
        )
        apply_solve_result_to_db(proj, result)
        f = proj.get_frame(fid)
        assert f is not None
        assert f.wcs_json == "CRVAL1=1.0"
        assert f.ra_center_deg == 83.63
        assert f.pixscale_arcsec == 2.5
    finally:
        proj.close()


def test_apply_solve_result_failure_doesnt_clobber_accept(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        result = SolveResult(
            frame_id=fid, fits_path="x.fit", solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None,
            error="match failed",
        )
        apply_solve_result_to_db(proj, result)
        f = proj.get_frame(fid)
        assert f is not None
        # We don't auto-reject — solve failure is often transient.
        assert f.accept is True
        assert f.reject_reason and "solve_failed" in f.reject_reason
    finally:
        proj.close()


def test_apply_solve_failure_preserves_a_real_reject_reason(tmp_path):
    """A frame already rejected for a concrete cause keeps that reason when a later
    plate-solve fails — it is not clobbered to ``solve_failed:``.

    Regression: ``build_solve_arglist`` offers any frame without a ``wcs_json``
    (no ``accept`` gate), so an already-rejected star-poor sub is re-offered to
    solve and fails; the failure branch unconditionally overwrote its reason,
    (a) mis-attributing it in the reject-summary buckets and (b) — for an
    ``auto:grade:`` reason — dropping it from the cumulative 25% auto-grade cap
    denominator, leaking rejections past the rail.
    """
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for i, real in enumerate(
                ("user", "auto:grade:star_count", "bulk:fwhm_px", "auto:streak")):
            fid = proj.add_frame(FrameRow(source_path=f"x{i}.fit"))
            proj.update_frame(fid, accept=False, reject_reason=real)
            apply_solve_result_to_db(proj, SolveResult(
                frame_id=fid, fits_path="x.fit", solved=False,
                wcs_text=None, ra_center_deg=None, dec_center_deg=None,
                pixscale_arcsec=None, rotation_deg=None, error="no solution",
            ))
            f = proj.get_frame(fid)
            assert f is not None
            assert f.accept is False
            assert f.reject_reason == real  # untouched, not "solve_failed:no solution"
    finally:
        proj.close()


def test_apply_solve_failure_refreshes_a_prior_solve_failed_reason(tmp_path):
    """A frame whose only reason is a prior ``solve_failed:`` still gets its
    message refreshed on a later failure (the preserve-guard must not freeze it)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        apply_solve_result_to_db(proj, SolveResult(
            frame_id=fid, fits_path="x.fit", solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None, error="no solution",
        ))
        # A later scan hits the setup problem — the reason updates to the canonical
        # "no star database" so the banner can classify it.
        apply_solve_result_to_db(proj, SolveResult(
            frame_id=fid, fits_path="x.fit", solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None, error="no star database found",
        ))
        f = proj.get_frame(fid)
        assert f is not None
        assert f.reject_reason == "solve_failed:no star database"
    finally:
        proj.close()


def test_apply_solve_result_clears_stale_solve_failed_reason(tmp_path):
    """A frame that failed a solve, then succeeds on retry, has its stale
    ``solve_failed:`` reject reason cleared — not left contradicting the WCS.

    Regression: the success branch wrote WCS + coords but never cleared a prior
    ``solve_failed:`` reason, so after a user installed the missing ASTAP star
    database and re-ran solve, every now-solved frame kept a "plate-solve failed"
    chip and still inflated the Target page's solve-failure banner.
    """
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        # First pass fails (star database missing) — stores a solve_failed reason,
        # accept untouched.
        apply_solve_result_to_db(proj, SolveResult(
            frame_id=fid, fits_path="x.fit", solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None, error="no star database found",
        ))
        f = proj.get_frame(fid)
        assert f is not None and (f.reject_reason or "").startswith("solve_failed:")
        # Retry succeeds — WCS lands and the stale reason must be gone.
        apply_solve_result_to_db(proj, SolveResult(
            frame_id=fid, fits_path="x.fit", solved=True,
            wcs_text="CRVAL1=1.0", ra_center_deg=83.63, dec_center_deg=-5.39,
            pixscale_arcsec=2.5, rotation_deg=12.0, error=None,
        ))
        f = proj.get_frame(fid)
        assert f is not None
        assert f.wcs_json == "CRVAL1=1.0"
        assert f.reject_reason is None
    finally:
        proj.close()


def test_apply_solve_result_success_without_wcs_is_an_honest_failure(tmp_path):
    """ASTAP reports success but no usable WCS could be extracted (malformed
    sidecar / unparsable ``.ini``) → the frame is recorded as an explicit
    ``solve_failed:`` failure, not left as "solved with wcs_json=None".

    Regression: a nominal-success SolveResult with ``wcs_text=None`` was written
    straight through, leaving ``wcs_json`` NULL. ``build_solve_arglist`` skips
    only frames with a *truthy* ``wcs_json``, so the frame was re-solved on every
    scan forever, and ``run_stack`` treated the None WCS as unsolved so it never
    stacked — a silent, wasteful limbo. It must instead read as an honest failure
    (``accept`` untouched, since the pixels may be fine)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        apply_solve_result_to_db(proj, SolveResult(
            frame_id=fid, fits_path="x.fit", solved=True,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None, error=None,
        ))
        f = proj.get_frame(fid)
        assert f is not None
        # No usable WCS was stored, so it is NOT counted as solved...
        assert f.wcs_json is None
        # ...and it is flagged as a solve failure so it stops being re-offered.
        assert (f.reject_reason or "").startswith("solve_failed:")
        # accept is left alone — this is a location failure, not a bad frame.
        assert f.accept is True
    finally:
        proj.close()


def test_apply_solve_result_preserves_a_user_reject_on_success(tmp_path):
    """A successful solve never un-rejects a user/QC/streak decision — only a
    ``solve_failed:`` reason is self-healed."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        proj.update_frame(fid, accept=False, reject_reason="user")
        apply_solve_result_to_db(proj, SolveResult(
            frame_id=fid, fits_path="x.fit", solved=True,
            wcs_text="CRVAL1=1.0", ra_center_deg=83.63, dec_center_deg=-5.39,
            pixscale_arcsec=2.5, rotation_deg=12.0, error=None,
        ))
        f = proj.get_frame(fid)
        assert f is not None
        assert f.wcs_json == "CRVAL1=1.0"
        # The user's reject stands.
        assert f.reject_reason == "user"
        assert f.accept is False
    finally:
        proj.close()


def test_classify_solve_setup_error():
    """The setup classifier spots ASTAP/database missing but not per-frame fails."""
    # ASTAP binary missing — the installer message.
    assert classify_solve_setup_error(
        "astap.exe not found. Install ASTAP from https://www.hnsky.org/astap.htm"
    ) == SOLVE_SETUP_ASTAP_MISSING
    # Star database missing (ASTAP ran but had nothing to match against).
    assert classify_solve_setup_error("Error: no star database found") == SOLVE_SETUP_NO_DATABASE
    assert classify_solve_setup_error("star database not found") == SOLVE_SETUP_NO_DATABASE
    # ASTAP missing wins even if a database phrase also appears somewhere.
    assert classify_solve_setup_error(
        "astap not found; no star database"
    ) == SOLVE_SETUP_ASTAP_MISSING
    # Ordinary per-frame failures are NOT setup problems (never nag about setup
    # when the real issue is one bad/unsolvable frame).
    assert classify_solve_setup_error("no solution") is None
    assert classify_solve_setup_error("could not open file") is None
    assert classify_solve_setup_error("error reading frame") is None
    assert classify_solve_setup_error("") is None
    assert classify_solve_setup_error(None) is None


def test_apply_solve_result_canonicalises_setup_failure(tmp_path):
    """A 'no star database' message buried past the 120-char storage window is
    canonicalised so the setup signature is always reliably present.

    Regression: before the fix the raw log was truncated to its first 120 chars,
    dropping the 'no star database' phrase, so the Target page couldn't tell the
    database-missing setup problem from an ordinary per-frame failure."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        # A realistic long ASTAP log where the setup phrase lands well past char 120.
        buried = (
            "Reading FITS header... image 1080x1920 loaded. Detecting stars... "
            "found 214 stars. Searching solution radius 30 deg fov 1.3 deg. "
            "Attempt failed: no star database found in the search path"
        )
        assert len("no star database") + buried.index("no star database") > 120
        result = SolveResult(
            frame_id=fid, fits_path="x.fit", solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None,
            error=buried,
        )
        apply_solve_result_to_db(proj, result)
        f = proj.get_frame(fid)
        assert f is not None
        assert f.reject_reason == f"solve_failed:{SOLVE_SETUP_NO_DATABASE}"
        # And the canonical reason is still classifiable from the stored string.
        assert classify_solve_setup_error(f.reject_reason) == SOLVE_SETUP_NO_DATABASE
    finally:
        proj.close()


def test_apply_solve_result_keeps_raw_reason_for_per_frame_failure(tmp_path):
    """An ordinary (non-setup) failure keeps its raw truncated message."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        result = SolveResult(
            frame_id=fid, fits_path="x.fit", solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None,
            error="no solution found (too few stars)",
        )
        apply_solve_result_to_db(proj, result)
        f = proj.get_frame(fid)
        assert f is not None
        assert f.reject_reason == "solve_failed:no solution found (too few stars)"
        assert classify_solve_setup_error(f.reject_reason) is None
    finally:
        proj.close()
