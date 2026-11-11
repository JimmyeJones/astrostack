"""ASTAP's console output is not guaranteed to be UTF-8.

``_run_astap`` captured ASTAP's stdout/stderr with ``text=True``, which decodes
with the locale's encoding *strictly*. One byte that is not UTF-8 — a Latin-1
degree sign in a "Solution found: … +41° …" line, or a frame's own file name
echoed back in a legacy encoding — raised ``UnicodeDecodeError`` out of
``subprocess.run`` *after* ASTAP had solved and written its sidecars. That is
not an ``ASTAPError``, so it skipped the solve ladder's other rungs, and
``solve_one`` stored the frame as unsolved with a decoder traceback as its
reason. These run a real stub binary through the real ``solve_one``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth import make_synth_wcs_text, write_seestar_fits  # noqa: E402

from seestack.solve.runner import solve_one  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX shell stub")


def _stub(tmp_path: Path, *, solve: bool) -> Path:
    """A stub ASTAP whose console output carries a lone ``0xB0`` byte (a
    Latin-1 degree sign — not valid UTF-8), and that solves or not."""
    wcs = make_synth_wcs_text(ra_center_deg=10.68, dec_center_deg=41.27)
    (tmp_path / "wcs.txt").write_text(wcs.ljust((len(wcs) // 2880 + 1) * 2880))
    (tmp_path / "ini.txt").write_text("CRVAL1=10.68\nCRVAL2=41.27\nCDELT2=0.0013\nCROTA2=0.0\n")
    body = (
        f'cp "{tmp_path}/wcs.txt" "$B.wcs"; cp "{tmp_path}/ini.txt" "$B.ini"\n'
        "printf 'Solution found: 00: 42 43.2  +41\\260 16\\047 12\\n'\n"
        "exit 0\n"
    ) if solve else (
        "printf 'No solution found \\260 for %s\\n' \"$F\" >&2\n"
        "exit 1\n"
    )
    stub = tmp_path / "astap"
    stub.write_text(
        "#!/bin/sh\n"
        'while [ $# -gt 0 ]; do [ "$1" = -f ] && F="$2"; shift; done\n'
        'B="${F%.*}"\n' + body
    )
    stub.chmod(0o755)
    return stub


def _frame(tmp_path: Path) -> Path:
    frame = tmp_path / "Light_M 31_10.0s_IRCUT_0001.fit"
    write_seestar_fits(frame, width=64, height=48, n_stars=8, seed=3)
    return frame


def test_a_solve_whose_output_is_not_utf8_is_still_solved(tmp_path):
    frame = _frame(tmp_path)
    r = solve_one(frame_id=1, fits_path=str(frame),
                  astap_path=str(_stub(tmp_path, solve=True)), fov_deg=2.1, timeout_s=30.0)
    assert r.solved, f"a successful solve was recorded as a failure: {r.error}"
    assert r.error is None
    assert r.wcs_text and "CRVAL1" in r.wcs_text
    assert r.ra_center_deg == pytest.approx(10.68, abs=1e-3)


def test_a_failed_solve_with_non_utf8_output_keeps_a_readable_reason(tmp_path):
    frame = _frame(tmp_path)
    r = solve_one(frame_id=1, fits_path=str(frame),
                  astap_path=str(_stub(tmp_path, solve=False)), fov_deg=2.1, timeout_s=30.0)
    assert not r.solved
    assert "UnicodeDecodeError" not in (r.error or "")
    # ASTAP's own words survive (the bad byte becomes a replacement character),
    # and the scratch path it echoed is mapped back to the owner's frame name.
    assert "No solution found" in (r.error or "")
    assert frame.name in (r.error or "")
