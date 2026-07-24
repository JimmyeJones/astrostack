"""`GET …/stack-runs/{id}/full-res-png` — download the finished picture at full
output resolution (the direct answer to the "my downloaded picture is low-res"
owner report)."""

from __future__ import annotations

import io

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_run(data_root, safe: str, *, w: int, h: int, with_fits: bool = True) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = None
        if with_fits:
            fits_path = tdir / f"master_{w}x{h}.fits"
            rng = np.random.default_rng(1)
            cube = (rng.random((3, h, w), dtype=np.float32) * 200.0)
            fits.PrimaryHDU(data=cube).writeto(fits_path, overwrite=True)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path) if fits_path else None,
                tiff_path=None, preview_path=None, n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_full_res_png_serves_native_resolution(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # Wider than the 1024 px preview cap so "full-res" is visibly different.
    w, h = 1600, 1200
    run_id = _add_run(solved_library, safe, w=w, h=h)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "master_fullres.png" in r.headers.get("content-disposition", "")
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.size == (w, h)  # native output resolution, not the 1024 cap


def test_full_res_png_404_when_run_has_no_fits(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, w=100, h=80, with_fits=False)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 404


def test_full_res_png_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/full-res-png")
    assert r.status_code == 404
