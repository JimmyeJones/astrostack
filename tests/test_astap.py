"""ASTAP wrapper — discovery and ini parsing (no real solve)."""

import subprocess
from pathlib import Path

import pytest

from seestack.solve.astap import (
    ASTAPError,
    ASTAPSolver,
    _parse_astap_ini,
    find_astap,
    find_star_db_dir,
)


def test_find_astap_with_explicit_missing(tmp_path):
    bogus = tmp_path / "does_not_exist.exe"
    assert find_astap(bogus) is None


def test_find_astap_with_explicit_existing(tmp_path):
    fake = tmp_path / "astap.exe"
    fake.write_bytes(b"")
    assert find_astap(fake) == fake


def test_solver_raises_when_missing(tmp_path, monkeypatch):
    # No astap on PATH and not at the explicit path.
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ASTAPError):
        ASTAPSolver(astap_path=tmp_path / "nope.exe")


def test_parse_ini(tmp_path):
    ini = tmp_path / "frame.ini"
    ini.write_text(
        "PLTSOLVD=T\n"
        "CRVAL1=83.6331\n"
        "CRVAL2=-5.3911\n"
        "CDELT1=-0.0007\n"
        "CDELT2=0.0007\n"
        "CROTA2=12.5\n"
    )
    ra, dec, pix, rot = _parse_astap_ini(ini)
    assert ra == pytest.approx(83.6331)
    assert dec == pytest.approx(-5.3911)
    # 0.0007 deg/px = 2.52 arcsec/px
    assert pix == pytest.approx(0.0007 * 3600.0)
    assert rot == pytest.approx(12.5)


def test_parse_ini_missing_file(tmp_path):
    with pytest.raises(ASTAPError):
        _parse_astap_ini(tmp_path / "missing.ini")


def test_find_star_db_dir_beside_binary(tmp_path):
    # .290 files sitting next to the astap binary are found automatically.
    (tmp_path / "astap").write_bytes(b"")
    (tmp_path / "d05_0101.290").write_bytes(b"x")
    assert find_star_db_dir(tmp_path / "astap") == tmp_path


def test_find_star_db_dir_1476_format(tmp_path):
    # The D-series databases (d05/d50) use .1476 files, not .290.
    (tmp_path / "astap").write_bytes(b"")
    (tmp_path / "d05_0101.1476").write_bytes(b"x")
    assert find_star_db_dir(tmp_path / "astap") == tmp_path


def test_find_star_db_dir_none_when_absent(tmp_path):
    (tmp_path / "astap").write_bytes(b"")
    # A stray non-database file must not count as a star database.
    (tmp_path / "readme.txt").write_bytes(b"x")
    assert find_star_db_dir(tmp_path / "astap") is None


def test_find_star_db_dir_env_override(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    dbdir = tmp_path / "data"
    bindir.mkdir()
    dbdir.mkdir()
    (bindir / "astap").write_bytes(b"")
    (dbdir / "h17_0101.290").write_bytes(b"x")
    monkeypatch.setenv("SEESTACK_ASTAP_DATA", str(dbdir))
    assert find_star_db_dir(bindir / "astap") == dbdir


def test_solver_passes_db_dir(tmp_path, monkeypatch):
    # The -d flag is added to the ASTAP command when a star DB is present.
    (tmp_path / "astap").write_bytes(b"")
    (tmp_path / "d05_0101.290").write_bytes(b"x")
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")

    solver = ASTAPSolver(astap_path=tmp_path / "astap")
    assert solver.db_dir == tmp_path

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class _P:
            returncode = 1
            stdout = ""
            stderr = "no solution"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    solver.solve(frame)
    assert "-d" in captured["cmd"]
    assert str(tmp_path) in captured["cmd"]


def _sidecar_paths(cmd):
    """Where the real ASTAP would put its sidecars for this command line: beside
    the file named by ``-f``.

    The solver hands ASTAP a scratch **copy** and never the source frame, because
    ASTAP writes beside ``-f`` and with ``copy_to_cache`` off that path is a raw
    sub in the owner's read-only ``incoming/`` tree (AGENTS.md §10). A fake that
    writes beside the *original* frame is therefore modelling a binary that does
    not exist — and would go on "passing" if the solver started handing over the
    source path again.
    """
    target = Path(cmd[cmd.index("-f") + 1])
    return target.with_suffix(".wcs"), target.with_suffix(".ini")


def _write_solved_sidecars(cmd):
    """Behave like a successful ASTAP run: sidecars beside the ``-f`` file."""
    wcs, ini = _sidecar_paths(cmd)
    wcs.write_text("CRVAL1=10\n")
    ini.write_text("CRVAL1=10\nCRVAL2=20\nCDELT2=0.0007\nCROTA2=0\n")


def _make_solver(tmp_path):
    (tmp_path / "astap").write_bytes(b"")
    (tmp_path / "d05_0101.290").write_bytes(b"x")
    return ASTAPSolver(astap_path=tmp_path / "astap")


def test_adaptive_ladder_escalates_downsample(tmp_path, monkeypatch):
    # ASTAP "fails" until the frame is downsampled (binned) to suppress noise,
    # then solves. solve() should walk the ladder and return the solved result.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class _P:
            stdout = ""
            stderr = ""
            returncode = 1
        # Only "solve" (write sidecars, rc 0) once ASTAP is told to downsample.
        if "-z" in cmd:
            _write_solved_sidecars(cmd)
            _P.returncode = 0
        else:
            _P.returncode = 1
            _P.stderr = "no solution found"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)
    assert result.solved
    # First attempt had no -z (default); a later one added it.
    assert "-z" not in calls[0]
    assert any("-z" in c for c in calls)


def test_adaptive_ladder_stops_on_fatal_error(tmp_path, monkeypatch):
    # A "no star database" failure is unrecoverable — don't burn the whole ladder.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)
    n = {"calls": 0}

    def fake_run(cmd, **kwargs):
        n["calls"] += 1

        class _P:
            returncode = 1
            stdout = ""
            stderr = "Error: no star database found"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)
    assert not result.solved
    assert n["calls"] == 1  # stopped after the first (fatal) attempt


def test_adaptive_ladder_survives_a_timeout_on_the_first_rung(tmp_path, monkeypatch):
    # A timeout on the slow full-res first rung must NOT abort the ladder: the
    # faster downsampled rungs run on fewer pixels and can still solve the frame.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)

    def fake_run(cmd, **kwargs):
        # First rung (no -z) runs long and times out; a downsampled rung solves.
        if "-z" not in cmd:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 60))
        _write_solved_sidecars(cmd)

        class _P:
            stdout = ""
            stderr = ""
            returncode = 0
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)
    assert result.solved  # rescued by a later rung instead of giving up on the timeout


def test_adaptive_ladder_raises_only_after_every_rung_times_out(tmp_path, monkeypatch):
    # If *every* rung times out the failure is surfaced — but only after the whole
    # ladder has been tried, not on the first timeout.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)
    n = {"calls": 0}

    def fake_run(cmd, **kwargs):
        n["calls"] += 1
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 60))

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    with pytest.raises(ASTAPError):
        solver.solve(frame)
    assert n["calls"] == len(ASTAPSolver._SOLVE_LADDER)  # tried every rung first


def test_solve_once_emits_z_and_s_flags(tmp_path, monkeypatch):
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class _P:
            returncode = 1
            stdout = ""
            stderr = "no solution"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    solver._solve_once(frame, downsample=4, max_stars=200)
    cmd = captured["cmd"]
    assert "-z" in cmd and "4" in cmd
    assert "-s" in cmd and "200" in cmd


def test_solve_ladder_never_bins_past_2x():
    # 2026-07 plate-solve audit (real ASTAP CLI + d05 DB): binning past 2x
    # destroys faint-star detection even on bright Seestar frames, so the old
    # bin-4 rung could never rescue anything a Seestar produces. The ladder must
    # never bin past 2x. (Fails before the reorder — the old rung binned 4x.)
    for rung in ASTAPSolver._SOLVE_LADDER:
        ds = rung.get("downsample")
        assert ds is None or ds <= 2, f"ladder rung bins past 2x: {rung}"


def test_solve_ladder_has_full_res_widened_star_pool_rung():
    # The audit's fix keeps/boosts a full-resolution rung: since ASTAP already
    # auto-bins 1x1 (best detection), the only lever left at full res is widening
    # the detected-star pool (raise -s). Assert such a rung exists — a bin-1 (or
    # auto) rung that raises max_stars above ASTAP's ~500 default.
    boosted = [
        r
        for r in ASTAPSolver._SOLVE_LADDER
        if r.get("downsample") in (None, 1) and (r.get("max_stars") or 0) > 500
    ]
    assert boosted, "ladder has no full-resolution widened-star-pool rung"


def test_solve_ladder_first_rung_is_astap_default():
    # Most frames solve on the cheap default rung; it must stay first and impose
    # no star cap so ASTAP picks its own best detection.
    first = ASTAPSolver._SOLVE_LADDER[0]
    assert first.get("downsample") is None
    assert first.get("max_stars") is None


def test_ladder_solves_on_full_res_widened_star_pool_rung(tmp_path, monkeypatch):
    # A frame that ASTAP only locks once more of its faint stars are offered to
    # the matcher (simulated: solve only when a high -s is present) is rescued by
    # the widened-star-pool rung — proving that rung is reached and useful, not
    # dead weight like the removed bin-4 rung.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)

    def fake_run(cmd, **kwargs):
        class _P:
            stdout = ""
            stderr = "no solution"
            returncode = 1

        # Solve only when the star pool is widened past the default (-s >= 1000).
        if "-s" in cmd and int(cmd[cmd.index("-s") + 1]) >= 1000:
            _write_solved_sidecars(cmd)
            _P.returncode = 0
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)
    assert result.solved


def _capture_cmd(monkeypatch):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class _P:
            returncode = 1
            stdout = ""
            stderr = "no solution"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    return captured


def test_solver_adds_position_hint(tmp_path, monkeypatch):
    solver = _make_solver(tmp_path)
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    captured = _capture_cmd(monkeypatch)
    solver.solve(frame, ra_hint_deg=83.6, dec_hint_deg=-5.4, radius_deg=10.0)
    cmd = captured["cmd"]
    assert "-ra" in cmd and "-spd" in cmd
    assert abs(float(cmd[cmd.index("-ra") + 1]) - 83.6 / 15.0) < 1e-3   # degrees → hours
    assert abs(float(cmd[cmd.index("-spd") + 1]) - (-5.4 + 90.0)) < 1e-3  # dec → south-polar-dist
    assert float(cmd[cmd.index("-r") + 1]) == 10.0


def test_solver_omits_hint_when_absent(tmp_path, monkeypatch):
    solver = _make_solver(tmp_path)
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    captured = _capture_cmd(monkeypatch)
    solver.solve(frame)
    assert "-ra" not in captured["cmd"] and "-spd" not in captured["cmd"]


def test_every_rung_timing_out_raises_the_canonical_timeout_token(tmp_path, monkeypatch):
    # "Ran out of time" is the one solve failure with an obvious fix (give the
    # solver longer), but only if it can be told apart from an ordinary "no
    # catalog match" *after* the raw log has been truncated for storage. The
    # ladder therefore leads its error with a stable canonical token.
    from seestack.solve.astap import SOLVE_FAILED_TIMEOUT, is_solve_timeout_error

    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 60))

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    with pytest.raises(ASTAPError) as exc:
        solver.solve(frame)
    assert str(exc.value).startswith(SOLVE_FAILED_TIMEOUT)
    assert is_solve_timeout_error(str(exc.value))
    # The per-attempt detail is still there for debugging.
    assert "attempt 3" in str(exc.value)


def test_a_rung_that_finished_and_found_nothing_is_not_called_a_timeout(tmp_path, monkeypatch):
    # A frame where some rung *ran to completion* and reported no match is an
    # ordinary per-frame failure: raising the timeout wouldn't rescue it, so it
    # must never be reported as "ran out of time".
    from seestack.solve.astap import is_solve_timeout_error

    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)

    def fake_run(cmd, **kwargs):
        if "-z" not in cmd:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 60))

        class _P:
            returncode = 1
            stdout = ""
            stderr = "no solution found"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)          # a result, not a raise
    assert not result.solved
    assert not is_solve_timeout_error(result.log_tail)


def test_is_solve_timeout_error_ignores_unrelated_text():
    from seestack.solve.astap import is_solve_timeout_error

    assert not is_solve_timeout_error(None)
    assert not is_solve_timeout_error("")
    assert not is_solve_timeout_error("no solution found")
    assert not is_solve_timeout_error("no star database")


# --------------------------------------------------------------------------- #
# 🔒 The scratch-copy guarantee, at unit level (AGENTS.md §10)
#
# ``tests/webapp/test_incoming_readonly_guard.py`` proves the *outcome* end to
# end with a stub binary. These pin the two properties that outcome rests on, so
# a regression names its own cause instead of surfacing as "a folder changed".
# --------------------------------------------------------------------------- #

def test_astap_is_never_pointed_at_the_callers_own_frame(tmp_path, monkeypatch):
    # The single fact the whole guarantee reduces to: ASTAP derives its sidecar
    # names from ``-f``, so ``-f`` must never be a path in the caller's tree.
    frames = tmp_path / "incoming" / "M_42_sub"
    frames.mkdir(parents=True)
    frame = frames / "Light_M42_10.0s_0001.fit"
    frame.write_bytes(b"the owner's only copy")
    solver = _make_solver(tmp_path)
    seen: list[tuple[Path, bytes]] = []

    def fake_run(cmd, **kwargs):
        given = Path(cmd[cmd.index("-f") + 1])
        # Record what ASTAP was handed, and *what it holds*, while it still exists.
        seen.append((given, given.read_bytes()))
        _write_solved_sidecars(cmd)

        class _P:
            stdout = ""
            stderr = ""
            returncode = 0
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    solver.solve(frame)

    assert seen, "ASTAP was never invoked"
    given, given_bytes = seen[0]
    assert given != frame
    assert frames not in given.parents, (
        f"ASTAP was pointed inside the frame's own folder: {given}")
    # Same *name*, so ASTAP's own log tail still names the frame the user knows…
    assert given.name == frame.name
    # …and the same bytes, so it is solving the owner's actual pixels.
    assert given_bytes == frame.read_bytes()


def test_the_result_names_the_callers_frame_not_the_scratch_copy(tmp_path, monkeypatch):
    # Staging is an implementation detail; callers store and display this path,
    # and a scratch path leaking into the project DB would be a dangling record.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)

    def fake_run(cmd, **kwargs):
        _write_solved_sidecars(cmd)

        class _P:
            stdout = ""
            stderr = ""
            returncode = 0
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)
    assert result.solved
    assert result.fits_path == frame


def test_a_stale_sidecar_beside_the_frame_cannot_fake_a_solve(tmp_path, monkeypatch):
    """A solve is "solved" only if *this* run wrote the sidecar.

    ``solved`` is ``returncode == 0 and sidecar.exists()`` — existence, not
    authorship. A ``.wcs`` left beside a frame by an older build of this app, or
    by the owner running ASTAP himself, used to sit exactly where the wrapper
    looked, so a run that found nothing could inherit somebody else's answer and
    persist it as this frame's WCS. Solving in a scratch directory that starts
    empty closes that by construction; this pins it, because nothing else does.
    """
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    frame.with_suffix(".wcs").write_text("CRVAL1=999\n")   # someone else's answer
    frame.with_suffix(".ini").write_text("CRVAL1=999\nCRVAL2=99\nCDELT2=0.1\nCROTA2=0\n")
    solver = _make_solver(tmp_path)

    def fake_run(cmd, **kwargs):
        class _P:  # ASTAP ran, matched nothing, wrote nothing
            stdout = ""
            stderr = "no solution found"
            returncode = 0
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    assert not solver.solve(frame).solved
