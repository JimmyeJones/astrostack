"""The Full-res PNG, its menu size and the full-size archive for an **unedited,
trimmed canvas wider than the 8000 px cap** (Scout 2026-11-11, sweep (1)).

The canvas used to be shrunk to the cap *before* the trim, so a 9000 px canvas
trimmed to a true 7200 px downloaded at 6400 px, and the archive counted it as
"at its true size". The trim rectangle is pinned through
``pipeline.unedited_border_trim`` so the arithmetic is exact; the real
coverage-map rule is pinned elsewhere (``test_unedited_preview_trim.py``).
"""

from __future__ import annotations

import io
import json
import time
import zipfile

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow

CROP_FITS = (0.1, 0.0, 0.9, 1.0)      # 9000 → 7200: fits under the cap
CROP_OVER = (0.0, 0.0, 0.85, 1.0)     # 10000 → 8500: still over it


def _add_run(data_root, safe: str, *, w: int, h: int) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        tdir.mkdir(parents=True, exist_ok=True)
        fits_path = tdir / f"wide_{w}x{h}.fits"
        rng = np.random.default_rng(7)
        fits.PrimaryHDU(data=rng.random((3, h, w), dtype=np.float32) * 200.0
                        ).writeto(fits_path, overwrite=True)
        preview_path = tdir / "wide_preview.png"
        Image.new("RGB", (64, 48), (20, 40, 70)).save(preview_path)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="wide", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


@pytest.fixture
def pinned_trim(monkeypatch):
    """Every run's unedited trim is the rectangle the test chose."""
    from webapp import pipeline

    chosen: dict[str, tuple] = {}

    def _trim(run):  # noqa: ANN001
        return chosen.get(str(run.fits_path))

    monkeypatch.setattr(pipeline, "unedited_border_trim", _trim)
    return chosen


def _fits_of(data_root, safe: str, run_id: int) -> str:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(r.fits_path for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()


def _download(client, safe: str, run_id: int) -> tuple[int, int]:
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as im:
        return im.size


def _menu_size(client, safe: str, run_id: int) -> dict:
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png/size")
    assert r.status_code == 200
    return r.json()


def _wait_job(client, job_id, timeout=180.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "error", "cancelled", "interrupted"):
            return j
        time.sleep(0.1)
    raise AssertionError("archive job did not finish in time")


def test_a_wide_canvas_trimmed_under_the_cap_downloads_at_its_true_size(
        client, solved_library, pinned_trim):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, w=9000, h=120)
    pinned_trim[_fits_of(solved_library, safe, run_id)] = CROP_FITS
    assert _download(client, safe, run_id) == (7200, 120)
    # …and the menu can now say so instead of falling back to the canvas.
    got = _menu_size(client, safe, run_id)
    assert (got["width"], got["height"], got["trimmed"]) == (7200, 120, True)


def test_a_wide_canvas_trimmed_still_over_the_cap_downloads_at_the_cap(
        client, solved_library, pinned_trim):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, w=10000, h=120)
    pinned_trim[_fits_of(solved_library, safe, run_id)] = CROP_OVER
    got = _download(client, safe, run_id)
    assert got[0] == 8000
    menu = _menu_size(client, safe, run_id)
    assert (menu["width"], menu["height"]) == got and menu["trimmed"] is True


def test_the_archive_counts_a_trimmed_wide_canvas_by_its_real_file(
        client, solved_library, pinned_trim):
    """The v0.506.14 promise: "the same pictures again at their true size", and
    a note for any that are not. The 7200 px trim is true size; the 8500 px one
    is reduced *to the cap* and the note says so."""
    safes = [t["safe_name"] for t in client.get("/api/targets").json()]
    fit_id = _add_run(solved_library, safes[0], w=9000, h=120)
    over_id = _add_run(solved_library, safes[1], w=10000, h=120)
    pinned_trim[_fits_of(solved_library, safes[0], fit_id)] = CROP_FITS
    pinned_trim[_fits_of(solved_library, safes[1], over_id)] = CROP_OVER

    r = client.post("/api/gallery/pictures-archive")
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    z = client.get(f"/api/gallery/pictures-archive/{r.json()['job_id']}")
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    with Image.open(io.BytesIO(zf.read(f"{safes[0]}.png"))) as im:
        assert im.size == (7200, 120)
    with Image.open(io.BytesIO(zf.read(f"{safes[1]}.png"))) as im:
        assert im.size[0] == 8000
    result = job["result"]
    assert result["n_reduced"] == 1
    note = zf.read("_reduced_size.txt").decode()
    assert f"{safes[1]}.png" in note and f"{safes[0]}.png" not in note
    assert "8500 × 120" in note
