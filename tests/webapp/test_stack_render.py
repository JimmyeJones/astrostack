"""Adjustable stretch rendering for stack history (render + save-preview)."""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from seestack.calibrate.masters import MasterMeta
from seestack.io.library import Library
from seestack.io.project import StackRunRow
from seestack.render.thumbnail import render_stack_png


def _make_run_with_fits(data_root, safe: str) -> tuple[str, str]:
    """Create a 3-channel FITS cube + a placeholder preview; register a run."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        # Synthetic RGB cube (C, H, W) with a bright central blob on dim sky.
        h = w = 64
        yy, xx = np.mgrid[0:h, 0:w]
        blob = np.exp(-(((xx - 32) ** 2 + (yy - 32) ** 2) / 60.0)).astype(np.float32)
        sky = 0.02 + 0.005 * np.random.default_rng(0).standard_normal((h, w)).astype(np.float32)
        cube = np.stack([sky + blob, sky + 0.6 * blob, sky + 0.3 * blob]).astype(np.float32)
        fits_path = tdir / "master.fits"
        fits.PrimaryHDU(data=cube).writeto(fits_path, overwrite=True)
        preview_path = tdir / "master_preview.png"
        preview_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # placeholder, to be overwritten

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return str(preview_path), str(run_id)
    finally:
        lib.close()


def test_render_stack_png_helper(tmp_path):
    # 3-channel cube → valid PNG bytes, with a higher stretch giving a brighter
    # mean (more faint signal pulled up).
    h = w = 48
    rng = np.random.default_rng(1)
    # Noisy sky (non-zero spread so the stretch midtones have something to move)
    # plus a faint extended glow and a bright core.
    sky = np.clip(0.10 + 0.03 * rng.standard_normal((h, w)), 0, None).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    glow = (0.15 * np.exp(-(((xx - 24) ** 2 + (yy - 24) ** 2) / 200.0))).astype(np.float32)
    chan = sky + glow
    chan[20:28, 20:28] = 0.9  # bright core
    cube = np.stack([chan, chan, chan]).astype(np.float32)
    fp = tmp_path / "m.fits"
    fits.PrimaryHDU(data=cube).writeto(fp)

    low = render_stack_png(fp, stretch=0.15, black=0.35, max_width=32)
    high = render_stack_png(fp, stretch=0.85, black=0.35, max_width=32)
    assert low[:8] == b"\x89PNG\r\n\x1a\n"
    assert high[:8] == b"\x89PNG\r\n\x1a\n"

    from io import BytesIO

    from PIL import Image
    lo_mean = np.asarray(Image.open(BytesIO(low))).mean()
    hi_mean = np.asarray(Image.open(BytesIO(high))).mean()
    assert hi_mean > lo_mean  # stronger stretch reveals more


def test_render_with_nan_borders_is_not_blank(tmp_path):
    # Stacks carry NaN in uncovered/mosaic-gap regions. The render must exclude
    # those (not let them blank the whole frame) — regression for the "preview
    # goes blank after Adjust" bug.
    h, w = 120, 240
    yy, xx = np.mgrid[0:h, 0:w]
    blob = np.exp(-(((xx - 160) ** 2 + (yy - 70) ** 2) / 1500.0)).astype(np.float32)
    chan = (0.05 + blob).astype(np.float32)
    cube = np.stack([chan, chan * 0.7, chan * 0.5]).astype(np.float32)
    cube[:, :15, :] = np.nan   # uncovered top
    cube[:, :, :25] = np.nan   # uncovered left
    fp = tmp_path / "mosaic.fits"
    fits.PrimaryHDU(data=cube).writeto(fp)

    png = render_stack_png(fp, stretch=0.6, black=0.35, max_width=80)
    from io import BytesIO

    from PIL import Image
    arr = np.asarray(Image.open(BytesIO(png)))
    assert arr.max() > 0          # not all black
    assert arr.mean() > 1.0       # the blob/sky actually rendered


def test_render_endpoint_returns_png(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render",
                   params={"stretch": 0.6, "black": 0.35, "size": 128})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_preview_overwrites_file(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    preview_path, run_id = _make_run_with_fits(solved_library, safe)
    from pathlib import Path
    before = Path(preview_path).read_bytes()

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"stretch": 0.5, "black": 0.35})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    after = Path(preview_path).read_bytes()
    assert after != before              # the placeholder was replaced
    assert after[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(after) > len(before)     # a real rendered PNG


def test_render_404_without_fits(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/99999/render")
    assert r.status_code == 404


def test_stack_info_reads_provenance_cards(client, solved_library):
    """The info endpoint surfaces the provenance header cards (integration time,
    frame count, method) from the run's master FITS."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    # Stamp provenance onto the FITS header as a real stack would.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["OBJECT"] = "M31"
                hdul[0].header["NFRAMES"] = 840
                hdul[0].header["EXPTOTAL"] = 2520.0
                hdul[0].header["STACKER"] = "sigma-clip"
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info")
    assert r.status_code == 200
    body = r.json()
    assert body["integration_s"] == 2520.0
    assert body["n_frames"] == 840
    keys = {c["key"]: c["value"] for c in body["cards"]}
    assert keys["OBJECT"] == "M31"
    assert keys["STACKER"] == "sigma-clip"
    # cards carry a comment field (may be empty) and preserve display order
    order = [c["key"] for c in body["cards"]]
    assert order.index("OBJECT") < order.index("EXPTOTAL") < order.index("STACKER")


def test_stack_info_404_without_fits(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/99999/info")
    assert r.status_code == 404


def _add_run_with_options(data_root, safe: str, options_json: str,
                          total_exposure_s: float | None = None) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=3, canvas_h=8, canvas_w=8,
                coverage_min=1, coverage_max=3, options_json=options_json,
                total_exposure_s=total_exposure_s,
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def test_stack_run_options_reuse(client, solved_library):
    """The options endpoint returns a form-ready payload: knobs preserved,
    output_name dropped, and calibration paths reverse-mapped to master ids."""
    import json

    from webapp import calibration

    safe = client.get("/api/targets").json()[0]["safe_name"]
    root = solved_library / "library"
    dark = calibration.register_master(
        root, name="Dark", array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0))
    dark_path = str(calibration.calibration_dir(root) / dark["filename"])
    run_id = _add_run_with_options(solved_library, safe, json.dumps({
        "sigma_clip": True, "sigma_kappa": 2.5, "drizzle": True,
        "output_name": "my_special_run", "dark_path": dark_path,
    }))

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/options")
    assert r.status_code == 200
    opts = r.json()["options"]
    assert opts["sigma_clip"] is True and opts["sigma_kappa"] == 2.5
    assert opts["drizzle"] is True
    assert "output_name" not in opts            # a fresh run gets a fresh name
    assert "dark_path" not in opts              # never expose raw paths
    assert opts["dark_master_id"] == dark["id"] # reverse-mapped for the form


def test_stack_run_options_rejects_non_stack_run(client, solved_library):
    import json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run_with_options(
        solved_library, safe, json.dumps({"channel_combine": [], "weights": {}}))
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/options")
    assert r.status_code == 400


def test_stack_runs_reusable_flag(client, solved_library):
    """The stack-runs list marks which runs can pre-fill the Stack form."""
    import json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    stack_id = _add_run_with_options(
        solved_library, safe, json.dumps({"sigma_clip": True}))
    combine_id = _add_run_with_options(
        solved_library, safe, json.dumps({"channel_combine": []}))
    runs = {r["id"]: r for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs[stack_id]["reusable"] is True
    assert runs[combine_id]["reusable"] is False


def test_stack_runs_expose_integration_time(client, solved_library):
    """The stack-runs list carries total_exposure_s so History can show it inline."""
    import json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run_with_options(
        solved_library, safe, json.dumps({"sigma_clip": True}),
        total_exposure_s=2520.0)
    runs = {r["id"]: r for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs[run_id]["total_exposure_s"] == 2520.0
