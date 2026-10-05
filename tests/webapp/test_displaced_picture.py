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

import pytest

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


# --------------------------------------------------------------------------
# …and the same row must not be allowed to WRITE the file it does not own.
#
# "Adjust → Save as preview" re-renders from the FITS and overwrites
# ``run.preview_path``. On a displaced row that path is the *live* run's preview
# PNG — the file its History thumbnail, Target hero, Library tile and Sky Map
# tile are all served from. Measured before the guard, on a shared pair: saving
# from the older card replaced the live run's 64x64 preview with an 86x86 render
# turned 155° to North, while the rotation was recorded on the *older* row and
# the live row's ``preview_north_up_deg`` stayed NULL — the exact mismatch that
# column exists to prevent. This was filed as "cosmetic" with v0.492.40 and is
# not: the Sky Map places the live tile from a rotation the file no longer has.
# --------------------------------------------------------------------------

_PREVIEW_H = _PREVIEW_W = 64

#: Enough field rotation that a North-up save visibly resizes the canvas
#: (64x64 → 86x86), so a test can tell "the bytes were rewritten" from "the
#: bytes were rewritten *and turned*" without decoding pixels.
_ROT_DEG = 25.0


def _write_output_set(out: Path, basename: str) -> tuple[Path, Path]:
    """A renderable FITS (so the save endpoint gets past its own 404s) with a
    rotated WCS (so "North up" has a rotation to apply), plus a preview PNG at
    the canvas's own size. Returns ``(fits_path, preview_path)``."""
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(3)
    cube = (rng.normal(0.02, 0.003, size=(3, _PREVIEW_H, _PREVIEW_W))
            + 0.4).astype(np.float32)
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [(_PREVIEW_W - 1) / 2 + 1, (_PREVIEW_H - 1) / 2 + 1]
    wcs.wcs.crval = [150.0, 20.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    th = np.radians(_ROT_DEG)
    cd = 0.001
    wcs.wcs.cd = np.array([[-cd * np.cos(th), cd * np.sin(th)],
                           [cd * np.sin(th), cd * np.cos(th)]])
    fits_path = out / f"{basename}.fits"
    fits.PrimaryHDU(data=cube, header=wcs.to_header()).writeto(
        fits_path, overwrite=True)
    preview = out / f"{basename}_preview.png"
    Image.new("RGB", (_PREVIEW_W, _PREVIEW_H), (10, 20, 30)).save(preview)
    return fits_path, preview


def _add_real_run(data_root: Path, safe: str, basename: str, *, ts: str) -> int:
    """A run row over a real output set of its own."""
    lib = Library.open_or_create(data_root / "library")
    try:
        entry = lib.find_target(safe)
        assert entry is not None
        fits_path, preview = _write_output_set(
            lib.target_dir(entry) / "output", basename)
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename=basename,
                fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview), n_frames_used=5,
                canvas_h=_PREVIEW_H, canvas_w=_PREVIEW_W,
                coverage_min=1, coverage_max=1,
                options_json=json.dumps({"output_name": "m42"}),
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _shared_output_set(data_root: Path, safe: str) -> tuple[int, int, Path]:
    """Two rows naming **one** real output set — the pre-v0.81.8 shape.

    Returns ``(displaced run id, live run id, the shared preview path)``.
    """
    displaced = _add_real_run(data_root, safe, "master",
                              ts="2026-01-01T00:00:00+00:00")
    live = _add_real_run(data_root, safe, "master",
                         ts="2026-08-30T14:32:05+00:00")
    lib = Library.open_or_create(data_root / "library")
    try:
        entry = lib.find_target(safe)
        assert entry is not None
        preview = lib.target_dir(entry) / "output" / "master_preview.png"
    finally:
        lib.close()
    return displaced, live, preview


def _row(data_root: Path, safe: str, run_id: int):
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()


def test_adjusting_a_displaced_row_does_not_rewrite_the_live_runs_preview(
        client, solved_library):
    """FAIL-BEFORE: the save returned 200 and the live run's preview PNG changed.

    Refused rather than redirected: this run's own pixels are gone — there is no
    file of its own to write — which is precisely what its "picture overwritten"
    badge says.
    """
    pytest.importorskip("PIL")
    safe = client.get("/api/targets").json()[0]["safe_name"]
    displaced, live, preview = _shared_output_set(solved_library, safe)
    assert _owner_by_id(client, safe)[displaced] == live

    before = preview.read_bytes()
    r = client.post(f"/api/targets/{safe}/stack-runs/{displaced}/preview",
                    json={"stretch": 0.25, "black": 0.0})

    assert r.status_code == 409
    assert str(live) in r.json()["detail"]
    assert preview.read_bytes() == before


def test_the_live_runs_recorded_rotation_cannot_desync_from_its_own_pixels(
        client, solved_library):
    """FAIL-BEFORE: ``north_up`` from the displaced card turned the live run's
    64x64 preview into an 86x86 one and recorded the 155° on the *older* row, so
    the Sky Map placed the live tile's un-rotated geometry against turned pixels
    — the failure ``preview_north_up_deg`` exists to prevent."""
    pytest.importorskip("PIL")
    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    displaced, live, preview = _shared_output_set(solved_library, safe)

    r = client.post(f"/api/targets/{safe}/stack-runs/{displaced}/preview",
                    json={"stretch": 0.25, "black": 0.0, "north_up": True})

    assert r.status_code == 409
    assert Image.open(preview).size == (_PREVIEW_W, _PREVIEW_H)
    assert _row(solved_library, safe, live).preview_north_up_deg is None
    # And nothing was stamped on the refused row either: a 409 writes no column.
    assert _row(solved_library, safe, displaced).preview_north_up_deg is None


def test_keep_processed_is_refused_on_a_displaced_row_too(
        client, solved_library):
    """The second save path (re-bake the run's own recipe) writes the same file,
    so it is guarded by the same check rather than by a second one."""
    pytest.importorskip("PIL")
    safe = client.get("/api/targets").json()[0]["safe_name"]
    displaced, _live, preview = _shared_output_set(solved_library, safe)

    before = preview.read_bytes()
    r = client.post(f"/api/targets/{safe}/stack-runs/{displaced}/preview",
                    json={"keep_processed": True, "north_up": True})

    assert r.status_code == 409
    assert preview.read_bytes() == before


def test_the_run_that_owns_the_picture_can_still_save_it(
        client, solved_library):
    """The guard must not cost the live run its own Adjust. It is the *writer* of
    the shared file, so saving from its card is the one correct way to change
    those bytes — and this is the half a "refuse on any shared path" rule would
    have broken."""
    pytest.importorskip("PIL")
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _displaced, live, preview = _shared_output_set(solved_library, safe)

    before = preview.read_bytes()
    r = client.post(f"/api/targets/{safe}/stack-runs/{live}/preview",
                    json={"stretch": 0.25, "black": 0.0})

    assert r.status_code == 200
    assert preview.read_bytes() != before
    assert _row(solved_library, safe, live).preview_stretch == pytest.approx(0.25)


def test_an_ordinary_run_with_its_own_output_set_saves_as_before(
        client, solved_library):
    """A history with no duplicate path — every install that has only re-stacked
    since v0.81.8, where each row owns the set it names — reaches the save
    exactly as it did, on the *older* row as much as the newer."""
    pytest.importorskip("PIL")
    safe = client.get("/api/targets").json()[0]["safe_name"]
    older = _add_real_run(solved_library, safe, "master_20260101_000000",
                          ts="2026-01-01T00:00:00+00:00")
    newer = _add_real_run(solved_library, safe, "master",
                          ts="2026-08-30T14:32:05+00:00")

    assert _owner_by_id(client, safe) == {older: None, newer: None}
    for run_id in (older, newer):
        r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                        json={"stretch": 0.25, "black": 0.0})
        assert r.status_code == 200


def test_the_write_guard_has_no_existence_gate_but_the_display_claim_does(
        client, solved_library):
    """Two questions, deliberately different rules.

    "This card shows a later run's picture" is a claim about bytes that are
    *there* — with the file gone the card already says "no picture" and which way
    it went is unknowable. "Do not write a file another row serves" is not: the
    save would **create** that file, handing the live row a thumbnail rendered
    from another row's sliders while its own stretch columns stay NULL.
    """
    from webapp.displacedpicture import (
        picture_owner_by_run_id,
        preview_owner_by_run_id,
    )

    safe = client.get("/api/targets").json()[0]["safe_name"]
    displaced = _add_run(solved_library, safe, "master",
                         ts="2026-01-01T00:00:00+00:00", write_files=False)
    live = _add_run(solved_library, safe, "master",
                   ts="2026-08-30T14:32:05+00:00", write_files=False)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            runs = list(proj.iter_stack_runs())
        finally:
            proj.close()
    finally:
        lib.close()

    assert picture_owner_by_run_id(runs) == {}
    assert preview_owner_by_run_id(runs) == {displaced: live}
