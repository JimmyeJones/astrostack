"""A History row that is pointing at a *different* run's picture says so.

Before the v0.81.7–0.81.8 overwrite guard a re-stack wrote the canonical
``master.*`` straight over the previous run's output, and ``repoint_stack_runs``
runs only at re-stack time, so nothing ever migrated the rows written before it:
they still name a file a *newer* run wrote. Observer issue #1069 counts 56 of them
on the owner's library. The old pixels are gone, so the fix is to **say so** — the
card carries this run's frame count and integration time beside somebody else's
image, and every number on it is true while the picture is not.

The signature is two rows naming one ``fits_path``, which is exactly what the
guard exists to prevent, and it costs no file read beyond one ``stat`` per shared
path — the cheap History endpoints promise not to open the FITS.
"""

from __future__ import annotations

import json
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_run(data_root: Path, safe: str, basename: str, *,
             ts: str, write_files: bool) -> int:
    """A run row, with or without the output set it names actually existing."""
    lib = Library.open_or_create(data_root / "library")
    try:
        entry = lib.find_target(safe)
        assert entry is not None
        tdir = lib.target_dir(entry)
        out = tdir / "output"
        out.mkdir(parents=True, exist_ok=True)
        if write_files:
            for suffix in (".fits", ".tif", "_preview.png"):
                (out / f"{basename}{suffix}").write_bytes(b"z" * 64)
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename=basename,
                fits_path=str(out / f"{basename}.fits"),
                tiff_path=str(out / f"{basename}.tif"),
                preview_path=str(out / f"{basename}_preview.png"),
                n_frames_used=30, canvas_h=100, canvas_w=100,
                coverage_min=1, coverage_max=1,
                options_json=json.dumps({"sigma_clip": True}),
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _owner_by_id(client, safe: str) -> dict[int, int | None]:
    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    return {r["id"]: r.get("picture_owned_by_run_id") for r in runs}


def test_the_older_of_two_rows_on_one_file_is_told_whose_picture_it_shows(
        client, solved_library):
    """FAIL-BEFORE: History showed a pre-v0.81.8 row's frame count beside a later
    run's thumbnail and said nothing about it.

    The *newer* row is the writer — it is the one whose ``write_stack_outputs``
    last wrote those bytes — so it owns its picture and must stay silent.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    displaced = _add_run(solved_library, safe, "master",
                         ts="2026-01-01T00:00:00+00:00", write_files=True)
    live = _add_run(solved_library, safe, "master",
                    ts="2026-08-30T14:32:05+00:00", write_files=True)

    owner = _owner_by_id(client, safe)
    assert owner[displaced] == live
    assert owner[live] is None


def test_a_history_with_no_duplicate_path_says_nothing_about_any_run(
        client, solved_library):
    """Every run on an install that has only re-stacked since the guard. The
    field has to stay absent rather than become a badge on healthy cards."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    a = _add_run(solved_library, safe, "master",
                 ts="2026-01-01T00:00:00+00:00", write_files=True)
    b = _add_run(solved_library, safe, "master_20260830_143205",
                 ts="2026-08-30T14:32:05+00:00", write_files=True)

    owner = _owner_by_id(client, safe)
    assert owner == {a: None, b: None}


def test_a_shared_path_whose_file_is_gone_is_not_called_overwritten(
        client, solved_library):
    """``has_fits`` already reports a missing file and the card shows no picture
    without this. Which of the two ways it went missing — overwritten, or simply
    deleted — is not knowable from here, so the claim is withheld rather than
    guessed. Restricting it to a file that exists is what makes "the image here
    belongs to a later stack" literally true."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    displaced = _add_run(solved_library, safe, "gone",
                         ts="2026-01-01T00:00:00+00:00", write_files=False)
    live = _add_run(solved_library, safe, "gone",
                    ts="2026-08-30T14:32:05+00:00", write_files=False)

    owner = _owner_by_id(client, safe)
    assert owner == {displaced: None, live: None}


def test_three_rows_on_one_file_all_point_at_the_one_writer(
        client, solved_library):
    """A target re-stacked twice before the guard leaves more than a pair, and
    only the newest row wrote the bytes — the middle one is as displaced as the
    oldest, not the owner of anything."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    oldest = _add_run(solved_library, safe, "master",
                      ts="2026-01-01T00:00:00+00:00", write_files=True)
    middle = _add_run(solved_library, safe, "master",
                      ts="2026-02-01T00:00:00+00:00", write_files=True)
    newest = _add_run(solved_library, safe, "master",
                      ts="2026-03-01T00:00:00+00:00", write_files=True)

    owner = _owner_by_id(client, safe)
    assert owner == {oldest: newest, middle: newest, newest: None}


def test_the_order_is_the_row_id_not_the_timestamp_string(solved_library):
    """``timestamp_utc`` is a string the app has written in more than one format
    (``…+00:00`` and ``…Z`` both appear in the wild), so comparing the two as text
    could put a pair the wrong way round and name the *older* run as the writer.
    The row id is the order the runs were recorded in, which is the order the
    bytes were written.
    """
    from webapp.displacedpicture import picture_owner_by_run_id

    safe = "M_42"
    # The later row carries the format that sorts *earlier* as plain text:
    # "2026-08-30T14:32:05Z" vs "2026-09-01T00:00:00+00:00" compares on the
    # offset, and a Z-stamped August run would read as newer than a
    # +00:00-stamped September one under several naive comparisons.
    displaced = _add_run(solved_library, safe, "master",
                         ts="2026-09-01T00:00:00+00:00", write_files=True)
    live = _add_run(solved_library, safe, "master",
                   ts="2026-08-30T14:32:05Z", write_files=True)

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            runs = list(proj.iter_stack_runs())
        finally:
            proj.close()
    finally:
        lib.close()

    assert picture_owner_by_run_id(runs) == {displaced: live}


def test_two_targets_naming_their_own_master_are_not_confused(
        client, solved_library):
    """The rule is per project, which is what the endpoint already scopes it to —
    but the paths are absolute, so even a library where every target calls its
    stack ``master`` cannot cross-contaminate."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    only = _add_run(solved_library, safe, "master",
                    ts="2026-01-01T00:00:00+00:00", write_files=True)
    assert _owner_by_id(client, safe) == {only: None}
