"""The Sky surfaces when one project DB **opens cleanly and then errors**.

Four cross-target walks guard ``Project.open`` and skip a project this build
cannot open at all — the §9 rollback shape, where ``_check_schema`` refuses a
newer ``user_version``. ``sky.py``'s three walks guarded only that, and put the
reads *after* it in a bare ``try``/``finally`` with no ``except``, so a DB that
opens and then raises on its first row read took out the whole surface: the Sky
Map, the "Where you've been" map image, and the square-degree read-out beside it.

That shape is not hypothetical, which is the thing the bug's own filing could not
settle. ``Project.open`` reads page 1, ``PRAGMA user_version`` and the schema —
it never touches a row — so **one corrupt data page** inside ``project.sqlite``
opens without complaint and raises ``sqlite3.DatabaseError: database disk image
is malformed`` on the first ``SELECT``. A bad block or an interrupted write on a
NAS produces exactly that, and :func:`_corrupt_one_data_page` below builds it.

Each test puts a good target beside the broken one, because "no 500" is only half
the contract: the owner must still get the picture the app *could* answer about.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import Project, StackRunRow

pytest.importorskip("matplotlib")
pytest.importorskip("PIL")

_H, _W = 24, 32
_SCALE_DEG = 0.001                      # 3.6 arcsec/px, Seestar-ish
_PX_DEG2 = _SCALE_DEG * _SCALE_DEG


def _make_run(data_root, safe: str, *, crval1: float = 150.0) -> None:
    """One plate-solved run with a master FITS and a real preview PNG.

    Enough for all three surfaces at once: ``/api/sky`` sizes its tile from the
    stored canvas WCS, ``my-map.png`` masks and draws the preview, and
    ``/api/sky/coverage`` measures the FITS's own solid angle.
    """
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        cube = np.full((3, _H, _W), 0.3, dtype=np.float32)

        hdr = fits.Header()
        hdr["CTYPE1"] = "RA---TAN"
        hdr["CTYPE2"] = "DEC--TAN"
        hdr["CRPIX1"] = (_W - 1) / 2 + 1
        hdr["CRPIX2"] = (_H - 1) / 2 + 1
        hdr["CRVAL1"] = crval1
        hdr["CRVAL2"] = 20.0
        hdr["CD1_1"] = -_SCALE_DEG
        hdr["CD1_2"] = 0.0
        hdr["CD2_1"] = 0.0
        hdr["CD2_2"] = _SCALE_DEG
        fits_path = tdir / "m.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)

        preview_path = tdir / "m_preview.png"
        from seestack.stack.output import _write_preview_png
        _write_preview_png(preview_path, np.moveaxis(cube, 0, -1))

        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="m", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=9,
                canvas_h=_H, canvas_w=_W, coverage_min=0, coverage_max=9,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def _db_path(data_root, safe: str) -> Path:
    lib = Library.open_or_create(data_root / "library")
    try:
        entry = lib.find_target(safe)
        assert entry is not None
        return lib.target_dir(entry) / "project.sqlite"
    finally:
        lib.close()


def _opens_then_errors(project_dir: Path) -> bool:
    """Is this DB in the state these tests are *about* — open clean, read raises?

    Asked rather than assumed, because the guards could otherwise be "proved" by a
    fixture that in fact raises at ``Project.open``, which the four sibling walks
    already survive: the test would be green for the wrong reason.
    """
    try:
        proj = Project.open(project_dir)
    except Exception:  # noqa: BLE001 — corrupt at open: the shape already covered
        return False
    try:
        list(proj.iter_stack_runs())
    except Exception:  # noqa: BLE001 — any read error is the shape we want
        return True
    finally:
        proj.close()
    return False


def _drop_stack_runs(data_root, safe: str) -> None:
    """Make one target's project open-but-unreadable, deterministically.

    ``_check_schema`` reconciles *columns* on every open and deliberately skips a
    table that is absent entirely ("handled by the base-schema recreate" — which
    only runs when ``user_version`` is behind, so never for this DB). So the open
    succeeds and the first ``SELECT`` raises ``no such table``. Done by hand
    because no supported code path produces it, exactly as
    ``test_cleanup_suggestions._stamp_newer_schema`` does for the sibling shape.
    """
    db = _db_path(data_root, safe)
    conn = sqlite3.connect(db)
    try:
        conn.execute("DROP TABLE stack_runs")
        conn.commit()
    finally:
        conn.close()
    assert _opens_then_errors(db.parent), "fixture is not the opens-then-errors shape"


def _corrupt_one_data_page(data_root, safe: str) -> None:
    """The realistic shape: one bad 4 KiB page of ``project.sqlite``.

    Page 1 carries the header and the schema root, which is all ``Project.open``
    reads, so overwriting an interior *data* page leaves the open clean and makes
    the first row read raise ``database disk image is malformed``. *Which* interior
    page does that depends on the B-tree's layout — 14 of the 22 pages of a
    300-run DB did when this was measured — so rather than hard-code a page number
    a future schema would move, this restores the original bytes and tries the
    next page until one lands in the state.
    """
    db = _db_path(data_root, safe)
    original = db.read_bytes()
    page = 4096
    for n in range(1, max(len(original) // page, 1)):
        db.write_bytes(original)
        with db.open("r+b") as f:
            f.seek(page * n)
            f.write(b"\x5a" * page)
        if _opens_then_errors(db.parent):
            return
    db.write_bytes(original)
    pytest.fail("no single-page corruption produced an opens-then-errors DB")


def _two_targets(client) -> tuple[str, str]:
    safes = sorted(t["safe_name"] for t in client.get("/api/targets").json())
    assert len(safes) == 2, safes
    return safes[0], safes[1]


# ---- the three sky surfaces ------------------------------------------------

def test_sky_map_skips_the_unreadable_project_and_still_places_the_other(
        client, solved_library):
    """``GET /api/sky``: one bad DB cost the whole dome before the guard."""
    good, bad = _two_targets(client)
    _make_run(solved_library, good)
    _make_run(solved_library, bad, crval1=200.0)
    assert len(client.get("/api/sky").json()["images"]) == 2

    _drop_stack_runs(solved_library, bad)
    r = client.get("/api/sky")
    assert r.status_code == 200
    assert [im["safe"] for im in r.json()["images"]] == [good]


def test_my_map_png_skips_the_unreadable_project_and_still_renders(
        client, solved_library):
    """``GET /api/sky/my-map.png``: this one is an ``<img>`` on the page, so the
    500 showed up as a broken image with nothing to click."""
    good, bad = _two_targets(client)
    _make_run(solved_library, good)
    _make_run(solved_library, bad)
    assert client.get("/api/sky/my-map.png").status_code == 200

    _drop_stack_runs(solved_library, bad)
    r = client.get("/api/sky/my-map.png")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_sky_coverage_skips_the_unreadable_project_and_still_counts_the_other(
        client, solved_library):
    """``GET /api/sky/coverage``: the square-degree read-out beside the map.

    The good target's own canvas is still measured, so the guard degrades the
    number by exactly the picture it could not read — it doesn't zero it.
    """
    good, bad = _two_targets(client)
    _make_run(solved_library, good)
    _make_run(solved_library, bad, crval1=200.0)
    assert client.get("/api/sky/coverage").json()["n_pictures"] == 2

    _drop_stack_runs(solved_library, bad)
    body = client.get("/api/sky/coverage").json()
    assert body["n_pictures"] == 1
    assert body["deg2"] == pytest.approx(_H * _W * _PX_DEG2, rel=1e-6)


# ---- and the shape that makes all three reachable on real hardware ---------

def test_one_corrupt_data_page_is_the_real_trigger_behind_those_guards(
        client, solved_library):
    """A bad block under ``project.sqlite`` — not a hand-stamped pragma.

    The bug was filed as traced-not-reproduced because the certain-raise shape
    its siblings had happens *at open*. This is the shape that does reach the
    reads, and it needs nothing more exotic than one unlucky 4 KiB page.
    """
    good, bad = _two_targets(client)
    _make_run(solved_library, good)
    _make_run(solved_library, bad)
    _corrupt_one_data_page(solved_library, bad)

    r = client.get("/api/sky")
    assert r.status_code == 200
    assert [im["safe"] for im in r.json()["images"]] == [good]
