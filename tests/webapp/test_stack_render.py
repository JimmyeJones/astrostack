"""Adjustable stretch rendering for stack history (render + save-preview)."""

from __future__ import annotations

import numpy as np
from astropy.io import fits

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

    low = render_stack_png(fp, target_bg=0.05, sigma_factor=-2.5, max_width=32)
    high = render_stack_png(fp, target_bg=0.40, sigma_factor=-2.5, max_width=32)
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

    png = render_stack_png(fp, target_bg=0.2, sigma_factor=-2.5, max_width=80)
    from io import BytesIO

    from PIL import Image
    arr = np.asarray(Image.open(BytesIO(png)))
    assert arr.max() > 0          # not all black
    assert arr.mean() > 1.0       # the blob/sky actually rendered


def test_render_endpoint_returns_png(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render",
                   params={"stretch": 0.3, "black": -2.0, "size": 128})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_preview_overwrites_file(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    preview_path, run_id = _make_run_with_fits(solved_library, safe)
    from pathlib import Path
    before = Path(preview_path).read_bytes()

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"stretch": 0.25, "black": -2.0})
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
