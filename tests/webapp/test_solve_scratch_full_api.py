"""A full temp dir reaches the Target page as its own setup banner
(``reject-summary.solve_setup_problem.kind == "scratch"``), not as subs that
"couldn't be located" (Scout 2026-11-11, sweep (3))."""

from __future__ import annotations


def test_reject_summary_names_a_full_temp_dir(client, built_library, data_root):
    from seestack.io.library import Library
    from seestack.solve.astap import SOLVE_SETUP_SCRATCH_FULL

    frames = client.get("/api/targets/M_42/frames").json()
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            for f in frames[:3]:
                proj.update_frame(f["id"], wcs_json=None,
                                  reject_reason=f"solve_failed:{SOLVE_SETUP_SCRATCH_FULL}")
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get("/api/targets/M_42/frames/reject-summary").json()
    assert body["solve_setup_problem"] == {"kind": "scratch", "frames": 3}
    # The verdict never tells the owner to go and check his subs for these.
    assert body["summary"]["verdict"]["key"] != "dominant:solve_failed"
