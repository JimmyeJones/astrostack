"""An ASTAP ``.ini`` that carries a non-finite number is a missing value.

Python's ``float()`` accepts ``nan``, ``inf`` and ``infinity``, so a sidecar
whose ``CRVAL1``/``CDELT2`` read that way used to parse "successfully". A NaN
centre then reached SQLite, which stores NaN as NULL — a solved frame with a
valid ``.wcs`` but no centre, the very trap ``solve_one``'s ``.wcs`` fallback
exists for, which only fires on ``None``. An infinite centre was stored as-is
and crashed ``Library.refresh_target_stats`` (``round(inf)``) on every refresh
of that target. These run a real stub binary through the real ``solve_one``.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

from seestack.solve.astap import _parse_astap_ini  # noqa: E402
from seestack.solve.runner import apply_solve_result_to_db, solve_one  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX shell stub")


def _stub(tmp_path: Path, ini: str) -> Path:
    """A stub ASTAP that "solves": a valid ``.wcs`` and the given ``.ini``."""
    wcs = make_synth_wcs_text(ra_center_deg=83.6, dec_center_deg=-5.4)
    (tmp_path / "wcs.txt").write_text(wcs.ljust((len(wcs) // 2880 + 1) * 2880))
    (tmp_path / "ini.txt").write_text(ini)
    stub = tmp_path / "astap"
    stub.write_text(
        "#!/bin/sh\n"
        'while [ $# -gt 0 ]; do [ "$1" = -f ] && F="$2"; shift; done\n'
        'B="${F%.*}"\n'
        f'cp "{tmp_path}/wcs.txt" "$B.wcs"; cp "{tmp_path}/ini.txt" "$B.ini"\n'
        "exit 0\n"
    )
    stub.chmod(0o755)
    return stub


@pytest.mark.parametrize("bad", ["nan", "inf", "-Infinity"])
def test_parse_ini_treats_a_non_finite_centre_as_missing(tmp_path, bad):
    ini = tmp_path / "frame.ini"
    ini.write_text(f"CRVAL1={bad}\nCRVAL2=-5.4\nCDELT2=0.0013\n")
    with pytest.raises(Exception):  # noqa: B017 — the caller catches any parse failure
        _parse_astap_ini(ini)


def test_parse_ini_non_finite_rotation_reads_as_the_default(tmp_path):
    ini = tmp_path / "frame.ini"
    ini.write_text("CRVAL1=83.6\nCRVAL2=-5.4\nCDELT2=0.0013\nCROTA2=nan\n")
    ra, dec, pix, rot = _parse_astap_ini(ini)
    assert (ra, dec, rot) == (83.6, -5.4, 0.0)
    assert pix == pytest.approx(0.0013 * 3600.0)


@pytest.mark.parametrize("bad", ["nan", "inf"])
def test_solve_one_recovers_the_centre_from_the_wcs_when_the_ini_is_non_finite(tmp_path, bad):
    frame = tmp_path / "incoming" / "M_42" / "Light_M42_10.0s_0001.fit"
    frame.parent.mkdir(parents=True)
    write_seestar_fits(frame, width=480, height=320, n_stars=30, seed=1)
    before = frame.read_bytes()
    stub = _stub(tmp_path, f"CRVAL1={bad}\nCRVAL2={bad}\nCDELT2={bad}\nCROTA2={bad}\n")

    res = solve_one(1, str(frame), astap_path=str(stub), timeout_s=10.0)

    assert res.solved is True
    # Recovered from the .wcs, finite — not a NaN that SQLite turns into NULL.
    assert res.ra_center_deg == pytest.approx(83.6, abs=1e-6)
    assert res.dec_center_deg == pytest.approx(-5.4, abs=1e-6)
    for v in (res.pixscale_arcsec, res.rotation_deg):
        assert v is None or math.isfinite(v)
    assert frame.read_bytes() == before
    assert sorted(p.name for p in frame.parent.iterdir()) == [frame.name]


def test_an_infinite_ini_centre_does_not_break_the_target_stats_refresh(tmp_path):
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    incoming = tmp_path / "incoming"
    (incoming / "M_42").mkdir(parents=True)
    for i in range(2):
        write_seestar_fits(incoming / "M_42" / f"f_{i}.fit",
                           width=480, height=320, n_stars=30, seed=i)
    stub = _stub(tmp_path, "CRVAL1=inf\nCRVAL2=-5.4\nCDELT2=inf\nCROTA2=-inf\n")

    lib = Library.open_or_create(tmp_path / "library")
    try:
        scan_and_organize(lib, incoming, copy_to_cache=False)
        entry = lib.list_targets()[0]
        proj = lib.open_target(entry.safe_name)
        try:
            for f in proj.iter_frames():
                apply_solve_result_to_db(
                    proj, solve_one(f.id, f.source_path, astap_path=str(stub), timeout_s=10.0))
            centres = [(f.ra_center_deg, f.dec_center_deg) for f in proj.iter_frames()]
        finally:
            proj.close()
        assert centres and all(
            ra is not None and math.isfinite(ra) and math.isfinite(dec) for ra, dec in centres)
        lib.refresh_target_stats(entry.safe_name)  # raised OverflowError before the fix
    finally:
        lib.close()
