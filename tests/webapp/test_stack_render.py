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


def test_load_stack_rgb_shapes_and_preserves_nan(tmp_path):
    """The shared loader returns an (H, W, 3) array with the display-space flag
    and preserves NaN (uncovered) pixels through the striding decimation."""
    from seestack.render.thumbnail import load_stack_rgb

    h, w = 40, 200
    chan = np.full((h, w), 0.1, dtype=np.float32)
    chan[:, :20] = np.nan                       # uncovered strip
    cube = np.stack([chan, chan * 0.7, chan * 0.5]).astype(np.float32)
    fp = tmp_path / "m.fits"
    fits.PrimaryHDU(data=cube).writeto(fp)

    rgb, display_space = load_stack_rgb(fp, max_width=50)
    assert display_space is False
    assert rgb.ndim == 3 and rgb.shape[2] == 3
    assert rgb.shape[1] <= 50                    # decimated to <= max_width
    assert np.isnan(rgb[:, 0]).all()            # the uncovered strip stayed NaN
    assert np.isfinite(rgb[:, -1]).all()        # covered pixels are finite


def test_render_display_space_fits_is_verbatim(tmp_path):
    """An editor-export FITS is already tone-mapped display space, so render is
    verbatim: the stretch/black sliders don't apply (identical bytes at any
    setting) and a mid-grey ramp renders as mid-grey (no second stretch)."""
    from seestack.stack.output import write_stack_outputs

    ramp = np.clip(np.linspace(0.0, 1.0, 64, dtype=np.float32), 0, 1)
    rgb = np.repeat(np.tile(ramp, (16, 1))[..., None], 3, axis=2)
    cov = np.ones(rgb.shape[:2], dtype=np.float32)
    paths = write_stack_outputs(tmp_path, rgb, cov, wcs_text=None,
                                out_basename="edit", already_display=True)

    a = render_stack_png(paths["fits"], stretch=0.15, black=0.35, max_width=64)
    b = render_stack_png(paths["fits"], stretch=0.85, black=0.9, max_width=64)
    assert a == b                                   # sliders are a no-op on display data

    from io import BytesIO

    from PIL import Image
    mean = np.asarray(Image.open(BytesIO(a))).mean()
    assert abs(mean - 127) <= 4                     # ~0.5 ramp, not re-stretched

    # The identical data written as a *linear* stack renders differently (asinh).
    lin = write_stack_outputs(tmp_path, rgb, cov, wcs_text=None,
                              out_basename="lin", already_display=False)
    lin_mean = np.asarray(Image.open(BytesIO(
        render_stack_png(lin["fits"], stretch=0.5, black=0.35, max_width=64)))).mean()
    assert abs(lin_mean - mean) > 20


def test_render_endpoint_returns_png(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render",
                   params={"stretch": 0.6, "black": 0.35, "size": 128})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_suggestion_anchors_sliders_to_the_data(client, solved_library):
    """The History render-suggestion endpoint returns data-driven asinh
    stretch/black (so opening Adjust matches the STF thumbnail, not a fixed
    0.5/0.35)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["stretch"], float) and 0.0 <= body["stretch"] <= 1.0
    assert isinstance(body["black"], float) and 0.0 <= body["black"] <= 1.0
    assert body["target_bg"] == 0.10


def test_render_suggestion_null_for_display_space_run(client, solved_library):
    """A display-space editor export renders verbatim (sliders are a no-op), so
    there's nothing to anchor — the suggestion is null and the frontend keeps the
    fixed defaults."""
    from seestack.io.library import Library
    from seestack.io.project import StackRunRow
    from seestack.stack.output import write_stack_outputs

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        ramp = np.clip(np.linspace(0.0, 1.0, 64, dtype=np.float32), 0, 1)
        rgb = np.repeat(np.tile(ramp, (16, 1))[..., None], 3, axis=2)
        cov = np.ones(rgb.shape[:2], dtype=np.float32)
        paths = write_stack_outputs(tdir, rgb, cov, wcs_text=None,
                                    out_basename="edit", already_display=True)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="edit", fits_path=str(paths["fits"]), tiff_path=None,
                preview_path=None, n_frames_used=1, canvas_h=16, canvas_w=64,
                coverage_min=1, coverage_max=1, options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/render-suggestion").json()
    assert body["stretch"] is None and body["black"] is None


def test_render_suggestion_404_without_fits(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/99999/render-suggestion")
    assert r.status_code == 404


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


def test_jpeg_download_transcodes_the_preview(client, solved_library):
    """A run's finished picture can be downloaded as a share-friendly JPEG, served
    as an on-the-fly transcode of the stored preview PNG (no separate file)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    # Render a real preview PNG (the placeholder is just the magic bytes).
    assert client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                       json={"stretch": 0.5, "black": 0.35}).status_code == 200

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content[:2] == b"\xff\xd8"                       # JPEG SOI marker
    assert 'filename="master.jpg"' in r.headers.get("content-disposition", "")


def test_jpeg_download_404_when_no_preview(client, solved_library):
    """No preview PNG on disk → a clear 404 rather than a 500 transcode error."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)  # placeholder preview only
    from pathlib import Path
    # Point the run's preview at a missing file to simulate a run with no preview.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            Path(run.preview_path).unlink()
        finally:
            proj.close()
    finally:
        lib.close()
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert r.status_code == 404


def test_jpeg_download_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/99999/jpeg")
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


def test_stack_info_surfaces_quality_weighting_summary(client, solved_library):
    """A quality-weighted stack stamps WGT* cards; the info endpoint parses them
    into a friendly weighting summary the panel can show."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["WGTMODE"] = "quality"
                hdul[0].header["WGTNDOWN"] = 7
                hdul[0].header["WGTMIN"] = 0.31
                hdul[0].header["WGTMAX"] = 1.0
                hdul[0].header["WGTMED"] = 0.72
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    w = body["weighting"]
    assert w is not None
    assert w["mode"] == "quality"
    assert w["n_downweighted"] == 7
    assert w["min"] == 0.31
    assert w["max"] == 1.0
    assert w["median"] == 0.72


def test_stack_info_weighting_absent_for_unweighted_stack(client, solved_library):
    """A plain (unweighted) stack has no WGT* cards, so weighting is None."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert body["weighting"] is None


def test_stack_info_surfaces_photometric_normalization_summary(client, solved_library):
    """A photometrically-normalized stack stamps PHOTNORM/PHOTN* cards; the info
    endpoint parses them into a friendly summary the panel can show."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["PHOTNORM"] = "transparency"
                hdul[0].header["PHOTNADJ"] = 4
                hdul[0].header["PHOTMIN"] = 0.62
                hdul[0].header["PHOTMAX"] = 2.0
                hdul[0].header["PHOTMED"] = 1.03
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    p = body["photometric"]
    assert p is not None
    assert p["mode"] == "transparency"
    assert p["n_adjusted"] == 4
    assert p["min"] == 0.62
    assert p["max"] == 2.0
    assert p["median"] == 1.03


def test_stack_info_photometric_absent_for_unnormalized_stack(client, solved_library):
    """A plain stack has no PHOTNORM cards, so photometric is None."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert body["photometric"] is None


def test_stack_info_surfaces_dark_scaling_summary(client, solved_library):
    """A stack that scaled its dark to the subs' exposure stamps DARKSCAL/DARK*EXP
    cards; the info endpoint parses them into a friendly summary the panel shows."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["DARKSCAL"] = "exposure"
                hdul[0].header["DARKDEXP"] = 30.0
                hdul[0].header["DARKLEXP"] = 10.0
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    d = body["dark_scaling"]
    assert d is not None
    assert d["mode"] == "exposure"
    assert d["dark_exposure"] == 30.0
    assert d["light_exposure"] == 10.0


def test_stack_info_dark_scaling_absent_for_unscaled_stack(client, solved_library):
    """A plain stack has no DARKSCAL cards, so dark_scaling is None."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert body["dark_scaling"] is None


def test_stack_info_surfaces_rejection_summary(client, solved_library):
    """A κ-σ stack stamps REJMODE/REJFRAC/REJN* cards; the info endpoint parses
    them into a friendly summary the History panel shows as a trust line."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["REJMODE"] = "sigma-clip"
                hdul[0].header["REJFRAC"] = 0.004
                hdul[0].header["REJNREJ"] = 40
                hdul[0].header["REJNTOT"] = 10000
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    rej = body["rejection"]
    assert rej is not None
    assert rej["mode"] == "sigma-clip"
    assert rej["fraction"] == 0.004
    assert rej["n_rejected"] == 40
    assert rej["n_contributed"] == 10000


def test_stack_info_rejection_absent_for_unclipped_stack(client, solved_library):
    """A plain stack has no REJMODE cards, so rejection is None."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert body["rejection"] is None


def test_stack_info_surfaces_frame_accounting(client, solved_library):
    """A stack stamps NOFFERED/NALIGNFL cards; the info endpoint parses them into
    a frame_accounting summary so the History panel can honestly report how many
    subs made it in and flag any that couldn't be aligned."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["NOFFERED"] = 2000
                hdul[0].header["NALIGNFL"] = 150
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    fa = body["frame_accounting"]
    assert fa is not None
    assert fa["n_offered"] == 2000
    assert fa["n_align_failed"] == 150


def test_stack_info_frame_accounting_absent_on_older_master(client, solved_library):
    """A master recorded before frame accounting existed has no NOFFERED card, so
    frame_accounting is None (older masters degrade gracefully)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert body["frame_accounting"] is None


def test_transparency_ratio_surfaces_on_runs_and_gallery(client, solved_library):
    """A run's persisted transparency verdict rides along on both the runs list
    and the gallery so the frontend can badge a hazy night at a glance."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="hazy_master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=5, canvas_h=32, canvas_w=32,
                coverage_min=1, coverage_max=5, options_json="{}",
                transparency_ratio=0.44,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    run = next(r for r in runs if r["id"] == run_id)
    assert run["transparency_ratio"] == 0.44

    gal = client.get("/api/gallery").json()["items"]
    item = next(i for i in gal if i["run_id"] == run_id)
    assert item["transparency_ratio"] == 0.44


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


def test_update_stack_run_notes(client, solved_library):
    """PATCH sets, trims, clears and 404s a run's free-text label."""
    import json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run_with_options(solved_library, safe, json.dumps({"sigma_clip": True}))
    url = f"/api/targets/{safe}/stack-runs/{run_id}"

    # Set (with surrounding whitespace, which is trimmed).
    r = client.patch(url, json={"notes": "  best RGB v2  "})
    assert r.status_code == 200 and r.json()["notes"] == "best RGB v2"
    got = next(x for x in client.get(f"/api/targets/{safe}/stack-runs").json() if x["id"] == run_id)
    assert got["notes"] == "best RGB v2"

    # Empty string clears the note back to null.
    r = client.patch(url, json={"notes": "   "})
    assert r.status_code == 200 and r.json()["notes"] is None

    # Missing field and bad type are rejected.
    assert client.patch(url, json={}).status_code == 422
    assert client.patch(url, json={"notes": 5}).status_code == 422

    # Unknown run → 404.
    assert client.patch(f"/api/targets/{safe}/stack-runs/999999",
                        json={"notes": "x"}).status_code == 404


def test_update_stack_run_notes_caps_length(client, solved_library):
    import json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run_with_options(solved_library, safe, json.dumps({"sigma_clip": True}))
    r = client.patch(f"/api/targets/{safe}/stack-runs/{run_id}", json={"notes": "z" * 800})
    assert r.status_code == 200
    assert len(r.json()["notes"]) == 500


def test_stack_runs_expose_integration_time(client, solved_library):
    """The stack-runs list carries total_exposure_s so History can show it inline."""
    import json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run_with_options(
        solved_library, safe, json.dumps({"sigma_clip": True}),
        total_exposure_s=2520.0)
    runs = {r["id"]: r for r in client.get(f"/api/targets/{safe}/stack-runs").json()}
    assert runs[run_id]["total_exposure_s"] == 2520.0


def test_stack_info_advises_a_bias_when_only_a_mismatched_dark_exists(
        client, solved_library):
    """A stack that carries provenance but is uncalibrated, whose library holds a
    gain-matching dark at the wrong exposure and no bias, surfaces the specific
    "build a master bias and the dark is reused automatically" advice (the subs
    are 10 s / gain 80 from synth; the dark is 30 s / gain 80)."""
    from webapp import calibration

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    # Give the run provenance cards but no CALSTAT (= uncalibrated with provenance).
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["STACKER"] = "sigma-clip"
        finally:
            proj.close()
    finally:
        lib.close()

    calibration.register_master(
        solved_library / "library", name="Mismatched dark",
        array=np.full((4, 4), 1.0, dtype=np.float32),
        meta=MasterMeta("dark", 5, 4, 4, "median", exposure_s=30.0, gain=80.0))

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    advice = body["calibration_advice"]
    assert advice is not None
    assert "master bias" in advice
    assert "30s" in advice and "10s" in advice


def _write_reel_beside(fits_path: str, n: int = 5, suffix: str = "_progress.webp"):
    """Write a tiny animated reel next to a run's FITS (sibling pattern)."""
    from pathlib import Path

    from PIL import Image
    frames = [Image.fromarray(
        (np.random.default_rng(i).random((16, 24, 3)) * 255).astype(np.uint8), "RGB")
        for i in range(n)]
    fp = Path(fits_path)
    stem = fp.name[:-len(fp.suffix)] if fp.suffix else fp.name
    out = fp.with_name(f"{stem}{suffix}")
    fmt = "WEBP" if suffix.endswith(".webp") else "PNG"
    frames[0].save(out, format=fmt, save_all=True, append_images=frames[1:],
                   duration=300, loop=0)
    return out


def test_progress_info_reports_available_reel(client, solved_library):
    """A run with a reel sibling reports available + its frame count."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            _write_reel_beside(run.fits_path, n=6)
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/progress-info").json()
    assert body["available"] is True
    assert body["frames"] == 6


def test_progress_info_unavailable_without_reel(client, solved_library):
    """The common case (stacked without save_progress): available=false, not 404."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/progress-info").json()
    assert body == {"available": False, "frames": 0}


def test_progress_reel_serves_the_animation(client, solved_library):
    """The reel endpoint streams the WEBP animation with the right media type."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            _write_reel_beside(run.fits_path, n=5)
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/progress")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.content[:4] == b"RIFF"                     # WEBP container magic


def test_progress_reel_404_without_reel(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/progress").status_code == 404


def test_progress_reel_apng_fallback_is_served(client, solved_library):
    """When only an APNG reel exists (a Pillow build without WEBP), it's served
    as image/png — the browser still animates it in an <img>."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            _write_reel_beside(run.fits_path, n=4, suffix="_progress.png")
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/progress")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_stack_info_no_calibration_advice_without_a_near_miss_master(
        client, solved_library):
    """With no library master that's a fixable near-miss, the advice field is
    None and the frontend falls back to the generic "build or pick a master" copy."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["STACKER"] = "sigma-clip"
        finally:
            proj.close()
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert body["calibration_advice"] is None
