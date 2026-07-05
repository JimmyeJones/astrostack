"""Editor API: op schema, recipe round-trip, proxy preview, histogram,
auto-process, presets, full-res export + batch (non-destructive)."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _make_run(data_root, safe, basename="master", h=80, w=100,
              coverage_min=1, coverage_max=5, is_mosaic=None,
              ts="2026-05-02T00:00:00Z"):
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            outdir = Path(proj.project_dir) / "output"
            outdir.mkdir(parents=True, exist_ok=True)
            rng = np.random.default_rng(0)
            cube = (rng.random((3, h, w)) * 0.1).astype("float32")
            # a bright blob so the stretch has something to reveal
            yy, xx = np.mgrid[0:h, 0:w]
            cube += 0.4 * np.exp(-(((xx - w / 2) / 8) ** 2 + ((yy - h / 2) / 8) ** 2))
            fp = outdir / f"{basename}.fits"
            fits.writeto(fp, cube, overwrite=True)
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename=basename,
                fits_path=str(fp), tiff_path=None, preview_path=None, n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=coverage_min,
                coverage_max=coverage_max, options_json="{}", is_mosaic=is_mosaic,
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _write_coverage(data_root, safe, cov, basename="master"):
    """Write a ``{basename}_coverage.fits`` sibling next to a run's output FITS."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            fp = Path(proj.project_dir) / "output" / f"{basename}_coverage.fits"
            fits.writeto(fp, np.asarray(cov, dtype="float32"), overwrite=True)
        finally:
            proj.close()
    finally:
        lib.close()


def _enc(recipe: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(recipe).encode()).decode()


def test_proxy_coverage_loads_and_strides_the_sibling(tmp_path):
    """The preview/histogram paths feed EditContext.coverage via _proxy_coverage so
    the Coverage-leveling op works on the proxy and matches the full-res export."""
    from webapp.routers.editor import _proxy_coverage

    cov = np.arange(40 * 32, dtype=np.float32).reshape(40, 32)
    fp = tmp_path / "master.fits"
    fits.writeto(fp.with_name("master_coverage.fits"), cov)

    full = _proxy_coverage(str(fp), scale=1.0)
    assert full is not None and np.array_equal(full, cov)
    # A 2x proxy strides the coverage to match the decimated image.
    strided = _proxy_coverage(str(fp), scale=2.0)
    assert np.array_equal(strided, cov[::2, ::2])


def test_proxy_coverage_none_without_sibling(tmp_path):
    from webapp.routers.editor import _proxy_coverage

    assert _proxy_coverage(str(tmp_path / "master.fits"), scale=1.0) is None


def _wait_job(client, job_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "error", "cancelled", "interrupted"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish in time")


def _set_fwhm(data_root, safe, values):
    """Set fwhm_px on the target's frames (in id order) and mark them accepted."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            frames = list(proj.iter_frames())
            for f, v in zip(frames, values):
                proj.update_frame(f.id, fwhm_px=v, accept=True)
        finally:
            proj.close()
    finally:
        lib.close()


def test_psf_suggestion_from_median_fwhm(client, built_library, data_root):
    import math

    _set_fwhm(data_root, "M_42", [2.0, 3.0, 4.0])
    r = client.get("/api/targets/M_42/editor/psf-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["fwhm_px"] == 3.0  # median of 2, 3, 4
    expected_sigma = 3.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    assert abs(body["psf_sigma"] - round(expected_sigma, 2)) < 0.01


def test_psf_suggestion_none_without_fwhm(client, built_library):
    # No frame carries an FWHM → both fields null (button won't be offered).
    r = client.get("/api/targets/M_42/editor/psf-suggestion")
    assert r.status_code == 200
    assert r.json() == {"fwhm_px": None, "psf_sigma": None}


def test_psf_suggestion_clamps_to_op_range(client, built_library, data_root):
    # A huge FWHM would map to σ well above the op's 5.0 ceiling; it's clamped.
    _set_fwhm(data_root, "M_42", [30.0, 30.0, 30.0])
    body = client.get("/api/targets/M_42/editor/psf-suggestion").json()
    assert body["psf_sigma"] == 5.0


def test_sharpen_suggestion_from_median_fwhm(client, built_library, data_root):
    import math

    _set_fwhm(data_root, "M_42", [2.0, 3.0, 4.0])
    r = client.get("/api/targets/M_42/editor/sharpen-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["fwhm_px"] == 3.0  # median of 2, 3, 4
    # radius ≈ the star's Gaussian σ, rounded to the op's 0.5 step, in [0.5, 10].
    expected = 3.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    expected = round(round(expected / 0.5) * 0.5, 2)
    assert body["radius"] == expected


def test_sharpen_suggestion_none_without_fwhm(client, built_library):
    r = client.get("/api/targets/M_42/editor/sharpen-suggestion")
    assert r.status_code == 200
    assert r.json() == {"fwhm_px": None, "radius": None}


def test_sharpen_suggestion_clamps_to_op_range(client, built_library, data_root):
    # A tiny FWHM would map below the op's 0.5 floor; a huge one above its 10 ceiling.
    _set_fwhm(data_root, "M_42", [0.5, 0.5, 0.5])
    assert client.get("/api/targets/M_42/editor/sharpen-suggestion").json()["radius"] == 0.5
    _set_fwhm(data_root, "M_42", [40.0, 40.0, 40.0])
    assert client.get("/api/targets/M_42/editor/sharpen-suggestion").json()["radius"] == 10.0


def test_star_size_suggestion_from_median_fwhm(client, built_library, data_root):
    _set_fwhm(data_root, "M_42", [2.0, 3.0, 4.0])
    r = client.get("/api/targets/M_42/editor/star-size-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["fwhm_px"] == 3.0  # median of 2, 3, 4
    assert body["size"] == 3  # round(3.0), an int in [1, 8]


def test_star_size_suggestion_none_without_fwhm(client, built_library):
    r = client.get("/api/targets/M_42/editor/star-size-suggestion")
    assert r.status_code == 200
    assert r.json() == {"fwhm_px": None, "size": None}


def test_star_size_suggestion_clamps_to_op_range(client, built_library, data_root):
    # A tiny FWHM floors at the op's min of 1; a huge one caps at its max of 8.
    _set_fwhm(data_root, "M_42", [0.2, 0.2, 0.2])
    assert client.get("/api/targets/M_42/editor/star-size-suggestion").json()["size"] == 1
    _set_fwhm(data_root, "M_42", [40.0, 40.0, 40.0])
    assert client.get("/api/targets/M_42/editor/star-size-suggestion").json()["size"] == 8


def test_denoise_suggestion_from_image_noise(client, solved_library):
    # The run's proxy has a bright blob on a noisy sky (see _make_run), so the
    # endpoint returns a measurable noise σ and a usable in-range strength.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="denoise_src")
    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/denoise-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["noise_sigma"] is not None and body["noise_sigma"] > 0
    assert 0.1 <= body["strength"] <= 1.0


def test_levels_suggestion_from_image(client, solved_library):
    # A stretch places the image into display space; the Levels suggestion then
    # measures black/white from the image *entering* the Levels op (the stretch
    # applied), so it returns a usable in-range pair with white > black.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="levels_src")
    recipe = {"ops": [
        {"id": "tone.stretch", "uid": "s1", "params": {"stretch": 0.6, "black": 0.35}},
        {"id": "tone.levels", "uid": "lv1", "params": {}},
    ]}
    q = _enc(recipe)
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/levels-suggestion?recipe={q}&uid=lv1")
    assert r.status_code == 200
    body = r.json()
    assert body["black"] is not None and body["white"] is not None
    assert 0.0 <= body["black"] < body["white"] <= 1.0
    # The payload carries the optional midtone gamma field (a float lift or null).
    assert "gamma" in body
    assert body["gamma"] is None or (0.1 <= body["gamma"] <= 5.0)
    # gamma_target names the goal the lift solves for; present iff a gamma is
    # suggested, and it's the engine's target grey (0..1).
    if body["gamma"] is None:
        assert body["gamma_target"] is None
    else:
        from seestack.edit.levels import GAMMA_TARGET
        assert body["gamma_target"] == GAMMA_TARGET


def test_levels_suggestion_unknown_uid_falls_back(client, solved_library):
    # An absent uid drops the tone.levels op(s) and measures the rest, so a stale
    # uid still yields a sensible (non-self-referential) suggestion rather than 404.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="levels_fb")
    recipe = {"ops": [
        {"id": "tone.stretch", "uid": "s1", "params": {"stretch": 0.6, "black": 0.35}},
        {"id": "tone.levels", "uid": "lv1", "params": {}},
    ]}
    q = _enc(recipe)
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/levels-suggestion?recipe={q}&uid=zzz")
    assert r.status_code == 200
    body = r.json()
    assert body["black"] is not None and body["white"] is not None
    assert body["white"] > body["black"]


def test_stretch_suggestion_from_image(client, solved_library):
    # The Stretch op receives the run's *linear* proxy; the suggestion measures it
    # (no stretch in the sub-recipe) and returns an in-range asinh strength/black
    # plus the target grey it solves the sky median to.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="stretch_src")
    recipe = {"ops": [
        {"id": "tone.stretch", "uid": "s1", "params": {"stretch": 0.5, "black": 0.35}},
    ]}
    q = _enc(recipe)
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/stretch-suggestion?recipe={q}&uid=s1")
    assert r.status_code == 200
    body = r.json()
    assert body["stretch"] is not None and body["black"] is not None
    assert 0.0 <= body["stretch"] <= 1.0
    assert 0.0 <= body["black"] <= 1.0
    # target_bg names the goal the strength solves for; it's the engine's target.
    from seestack.edit.stretch import STRETCH_TARGET_BG
    assert body["target_bg"] == STRETCH_TARGET_BG


def test_stretch_suggestion_unknown_uid_falls_back(client, solved_library):
    # An absent uid drops the tone.stretch op(s) and measures the linear proxy, so
    # a stale uid still yields a sensible suggestion (never the stretch's own
    # output) rather than a 404.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="stretch_fb")
    recipe = {"ops": [
        {"id": "tone.stretch", "uid": "s1", "params": {"stretch": 0.5, "black": 0.35}},
    ]}
    q = _enc(recipe)
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/stretch-suggestion?recipe={q}&uid=zzz")
    assert r.status_code == 200
    body = r.json()
    assert body["stretch"] is not None and body["black"] is not None


def test_curve_suggestion_from_image(client, solved_library):
    # A stretch places the image into display space; the Curve suggestion then
    # measures the histogram *entering* the Curves op and returns a gentle,
    # strictly-monotone starting curve (endpoints pinned, midtone lifted).
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="curve_src")
    recipe = {"ops": [
        {"id": "tone.stretch", "uid": "s1", "params": {"stretch": 0.7, "black": 0.3}},
        {"id": "tone.curves", "uid": "cv1", "params": {}},
    ]}
    q = _enc(recipe)
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/curve-suggestion?recipe={q}&uid=cv1")
    assert r.status_code == 200
    body = r.json()
    pts = body["points"]
    assert pts is not None, "a stretched Seestar stack should yield a starting curve"
    # Endpoints pinned; strictly monotone in both axes (never inverts/posterises).
    assert pts[0] == [0.0, 0.0] and pts[-1] == [1.0, 1.0]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert all(b > a for a, b in zip(xs, xs[1:]))
    assert all(b > a for a, b in zip(ys, ys[1:]))
    # target_bg names the goal the lift solves for; it's the engine's target grey.
    from seestack.edit.curve import CURVE_TARGET_BG
    assert body["target_bg"] == CURVE_TARGET_BG


def test_curve_suggestion_unknown_uid_falls_back(client, solved_library):
    # An absent uid drops the tone.curves op(s) and measures the rest, so a stale
    # uid still yields a sensible suggestion (200, not 404).
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="curve_fb")
    recipe = {"ops": [
        {"id": "tone.stretch", "uid": "s1", "params": {"stretch": 0.7, "black": 0.3}},
        {"id": "tone.curves", "uid": "cv1", "params": {}},
    ]}
    q = _enc(recipe)
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/curve-suggestion?recipe={q}&uid=zzz")
    assert r.status_code == 200
    # points may be a valid curve or null on degenerate data, but never an error.
    assert "points" in r.json()


def test_ops_schema(client):
    r = client.get("/api/editor/ops/schema")
    assert r.status_code == 200
    ops = r.json()
    ids = {o["id"] for o in ops}
    assert {"tone.stretch", "tone.curves", "detail.denoise", "stars.reduce",
            "geometry.crop", "background.final_gradient"} <= ids
    stretch = next(o for o in ops if o["id"] == "tone.stretch")
    assert stretch["is_stretch"] is True
    assert any(p["key"] == "stretch" for p in stretch["params"])
    # the curve param surfaces with the new "curve" type
    curves = next(o for o in ops if o["id"] == "tone.curves")
    assert curves["params"][0]["type"] == "curve"
    # the `heavy` hint (drives the editor's adaptive preview debounce) is exposed:
    # the iterative/restoration ops are heavy, the cheap tone ops are not.
    heavy = {o["id"] for o in ops if o.get("heavy")}
    assert {"detail.denoise", "detail.deconvolve"} <= heavy
    assert "tone.saturation" not in heavy
    assert "tone.stretch" not in heavy


def test_recipe_round_trip_and_validation(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    assert client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe").json()["ops"] == []

    recipe = {"ops": [
        {"id": "tone.stretch", "params": {"stretch": 0.6, "black": 0.4}},
        {"id": "bogus.op", "params": {}},            # dropped by validation
        {"id": "tone.saturation", "params": {"amount": 1.4}},
    ]}
    put = client.put(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe", json=recipe)
    assert put.status_code == 200
    saved = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/recipe").json()
    assert [o["id"] for o in saved["ops"]] == ["tone.stretch", "tone.saturation"]
    assert saved["base_run_id"] == rid


def test_previous_recipe_carry_over(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # An older run the user edited...
    old = _make_run(solved_library, safe, basename="run_old",
                    ts="2026-05-01T00:00:00Z")
    client.put(f"/api/targets/{safe}/stack-runs/{old}/editor/recipe",
               json={"ops": [{"id": "tone.stretch", "params": {"stretch": 0.7}},
                             {"id": "tone.saturation", "params": {"amount": 1.3}}]})
    # ...and a newer run with no saved edit yet.
    new = _make_run(solved_library, safe, basename="run_new",
                    ts="2026-05-03T00:00:00Z")

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{new}/editor/previous-recipe").json()
    assert body["run_id"] == old
    assert body["count"] == 2
    assert [o["id"] for o in body["ops"]] == ["tone.stretch", "tone.saturation"]
    # The ops are validated on load (each param clamped/filled), so they're safe to
    # apply straight into the working recipe.
    assert body["ops"][0]["params"]["stretch"] == 0.7

    # Asked from the *only* edited run, there's no other edited run → None.
    none = client.get(
        f"/api/targets/{safe}/stack-runs/{old}/editor/previous-recipe").json()
    assert none["run_id"] is None
    assert none["ops"] == [] and none["count"] == 0


def test_previous_recipe_prefers_the_newest_edited_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    a = _make_run(solved_library, safe, basename="run_a", ts="2026-05-01T00:00:00Z")
    b = _make_run(solved_library, safe, basename="run_b", ts="2026-05-02T00:00:00Z")
    client.put(f"/api/targets/{safe}/stack-runs/{a}/editor/recipe",
               json={"ops": [{"id": "tone.stretch", "params": {"stretch": 0.5}}]})
    client.put(f"/api/targets/{safe}/stack-runs/{b}/editor/recipe",
               json={"ops": [{"id": "tone.curves", "params": {}},
                             {"id": "tone.saturation", "params": {"amount": 1.2}}]})
    # A brand-new run gets the *most recent* edited run (b), not the oldest.
    new = _make_run(solved_library, safe, basename="run_c", ts="2026-05-03T00:00:00Z")
    body = client.get(
        f"/api/targets/{safe}/stack-runs/{new}/editor/previous-recipe").json()
    assert body["run_id"] == b
    assert [o["id"] for o in body["ops"]] == ["tone.curves", "tone.saturation"]


def test_previous_recipe_none_when_no_edits(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r1 = _make_run(solved_library, safe, basename="run1", ts="2026-05-01T00:00:00Z")
    _make_run(solved_library, safe, basename="run2", ts="2026-05-02T00:00:00Z")
    # Neither run has a saved recipe → nothing to carry over.
    body = client.get(
        f"/api/targets/{safe}/stack-runs/{r1}/editor/previous-recipe").json()
    assert body["run_id"] is None and body["ops"] == []


def test_default_recipe_unset_is_empty(client, built_library):
    # No default saved yet → the editor is told there's nothing to offer.
    body = client.get("/api/editor/default-recipe").json()
    assert body["ops"] == [] and body["count"] == 0


def test_default_recipe_set_get_and_clear(client, built_library):
    # Saving the current edit as the default validates the ops (drops unknown ops)
    # and stores it library-wide.
    put = client.put("/api/editor/default-recipe", json={"ops": [
        {"id": "tone.stretch", "params": {"stretch": 0.65}},
        {"id": "bogus.op", "params": {}},                 # dropped by validation
        {"id": "tone.saturation", "params": {"amount": 1.3}},
    ]})
    assert put.status_code == 200
    assert [o["id"] for o in put.json()["ops"]] == ["tone.stretch", "tone.saturation"]
    assert put.json()["count"] == 2

    # A later GET returns the same validated recipe (params clamped/filled).
    got = client.get("/api/editor/default-recipe").json()
    assert [o["id"] for o in got["ops"]] == ["tone.stretch", "tone.saturation"]
    assert got["ops"][0]["params"]["stretch"] == 0.65
    assert got["count"] == 2

    # DELETE clears it → back to "no default".
    deleted = client.delete("/api/editor/default-recipe").json()
    assert deleted["ops"] == [] and deleted["count"] == 0
    assert client.get("/api/editor/default-recipe").json()["count"] == 0


def test_default_recipe_empty_put_clears(client, built_library):
    client.put("/api/editor/default-recipe",
               json={"ops": [{"id": "tone.stretch", "params": {"stretch": 0.5}}]})
    assert client.get("/api/editor/default-recipe").json()["count"] == 1
    # Putting an empty op list is an explicit "clear", same as DELETE.
    client.put("/api/editor/default-recipe", json={"ops": []})
    assert client.get("/api/editor/default-recipe").json()["count"] == 0


def test_edit_preview_and_histogram(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, is_mosaic=True)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6, "black": 0.35}},
                      {"id": "tone.curves", "params": {"points": [[0, 0], [0.5, 0.6], [1, 1]]}}]}
    q = _enc(recipe)

    img = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/preview?recipe={q}")
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/png")
    assert len(img.content) > 100

    hist = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={q}").json()
    assert len(hist["r"]) == hist["bins"] and len(hist["g"]) == hist["bins"]
    assert sum(hist["r"]) > 0
    # Proxy geometry is surfaced so the editor can warn "preview is downscaled".
    assert hist["proxy_scale"] >= 1.0
    assert hist["proxy_width"] > 0 and hist["proxy_height"] > 0
    # This run is a mosaic (persisted is_mosaic flag), so the editor can enable the
    # Coverage-leveling op instead of warning it's a no-op.
    assert hist["is_mosaic"] is True
    # With no reshaping geometry op the rendered dims equal the raw proxy dims.
    assert hist["render_width"] == hist["proxy_width"]
    assert hist["render_height"] == hist["proxy_height"]


def test_histogram_reports_rendered_dims_after_crop(client, solved_library):
    """Regression: a recipe with a reshaping geometry op (crop) must report the
    *rendered* dims (``render_width``/``render_height``), matching the preview PNG,
    so the editor sizes its image box to the cropped image instead of letterboxing
    it inside the un-cropped aspect (which mis-aligns the Split divider / trim
    rectangle). The raw ``proxy_width``/``height`` stay the un-cropped source dims
    (for the "downscaled" caption)."""
    from io import BytesIO

    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)  # 100x80 proxy, scale 1
    # Crop to the central half-width, full height → the rendered frame is ~half as
    # wide as the source proxy but the same height.
    recipe = {"ops": [
        {"id": "tone.stretch", "params": {"mode": "stf"}},
        {"id": "geometry.crop", "params": {"x0": 0.25, "y0": 0.0, "x1": 0.75, "y1": 1.0}},
    ]}
    q = _enc(recipe)

    img = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/preview?recipe={q}")
    assert img.status_code == 200
    png = np.asarray(Image.open(BytesIO(img.content)))
    png_h, png_w = png.shape[:2]

    hist = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={q}").json()
    # Rendered dims track the crop and match the actual preview PNG exactly.
    assert hist["render_width"] == png_w
    assert hist["render_height"] == png_h
    # The crop halves the width, so the rendered frame is narrower than the raw
    # proxy while the height is unchanged.
    assert hist["render_width"] < hist["proxy_width"]
    assert hist["render_height"] == hist["proxy_height"]


def test_preview_survives_thin_crop_plus_downscale(client, solved_library):
    """A thin crop (a 2px strip on the proxy) followed by a downscale used to
    collapse an axis to 0 px, producing an empty image that crashed the PNG render
    with an unhandled 500. The preview must now return a valid PNG instead."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)  # 80x100, proxy_scale 1
    recipe = {"ops": [
        {"id": "tone.stretch", "params": {"mode": "stf"}},
        # rows 40..42 → a 2px-tall strip that survives the crop's >=2px guard
        {"id": "geometry.crop", "params": {"x0": 0.0, "y0": 0.5, "x1": 1.0, "y1": 0.525}},
        {"id": "geometry.resize", "params": {"scale": 0.1}},
    ]}
    q = _enc(recipe)

    img = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/preview?recipe={q}")
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/png")
    # A valid (if tiny) PNG — the collapse produced a 1px-tall strip, not an empty
    # image; anything with the PNG signature and an IEND chunk is well-formed.
    assert img.content.startswith(b"\x89PNG") and img.content.endswith(b"IEND\xaeB`\x82")
    # The histogram endpoint (same proxy render) must also survive.
    hist = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={q}")
    assert hist.status_code == 200


def test_histogram_flags_deconv_preview_understatement(client, solved_library):
    """When the preview proxy is decimated enough that an enabled Deconvolution
    op's PSF collapses to the floor, the histogram reports
    ``deconv_preview_understates`` so the editor can honestly caption that the
    preview shows less than the export applies. A PSF that survives the proxy,
    or a disabled deconv op, must not raise the flag."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # A wide master (1700 px) → proxy_scale 2, so psf_sigma 0.5 collapses
    # (0.5 / 2 = 0.25 < the 0.4 floor) while psf_sigma 2.0 survives (2.0/2 = 1.0).
    rid = _make_run(solved_library, safe, basename="wide", h=120, w=1700)

    def hist_for(recipe):
        q = _enc(recipe)
        return client.get(
            f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={q}").json()

    weak = hist_for({"ops": [{"id": "detail.deconvolve",
                              "params": {"iterations": 5, "psf_sigma": 0.5}}]})
    assert weak["proxy_scale"] >= 2.0
    assert weak["deconv_preview_understates"] is True

    # A wide PSF is representable on the same proxy → no understatement.
    strong = hist_for({"ops": [{"id": "detail.deconvolve",
                                "params": {"iterations": 5, "psf_sigma": 2.0}}]})
    assert strong["deconv_preview_understates"] is False

    # A disabled deconv op doesn't count.
    disabled = hist_for({"ops": [{"id": "detail.deconvolve", "enabled": False,
                                  "params": {"iterations": 5, "psf_sigma": 0.5}}]})
    assert disabled["deconv_preview_understates"] is False

    # A recipe with no deconv op is never flagged.
    none = hist_for({"ops": [{"id": "tone.stretch", "params": {}}]})
    assert none["deconv_preview_understates"] is False


def test_trim_suggestion_mosaic(client, solved_library):
    """On a mosaic, the trim endpoint returns a fractional crop to the largest
    well-covered rectangle, excluding the ragged low-coverage border."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=True)  # mosaic
    cov = np.full((80, 100), 1.0, dtype=np.float32)      # thin single-frame fringe
    cov[15:65, 20:80] = 5.0                              # well-covered interior
    _write_coverage(solved_library, safe, cov)

    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/trim-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["is_mosaic"] is True
    assert body["crop"] is not None
    c = body["crop"]
    assert 0.0 <= c["x0"] < c["x1"] <= 1.0
    assert 0.0 <= c["y0"] < c["y1"] <= 1.0
    # It should land on the interior block, not the full frame.
    assert abs(c["x0"] - 0.20) < 0.02 and abs(c["y0"] - 15 / 80) < 0.02


def test_trim_suggestion_single_field_is_noop(client, solved_library):
    """A single-field stack (uniform coverage) is not a mosaic → no crop offered."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="single", is_mosaic=False)
    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/trim-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["is_mosaic"] is False
    assert body["crop"] is None


def test_histogram_single_field_legacy_run_is_not_mosaic(client, solved_library):
    """Regression: a *legacy* single-field run (no persisted is_mosaic flag) whose
    coverage sibling is one interior plateau + a thin uncovered border must be
    classified single-field. The old ``coverage_max > coverage_min`` heuristic said
    mosaic (min is 0 at the uncovered border, max is the frame count), wrongly
    enabling the mosaic tools + a spurious Auto crop on the primary user's every
    single-field stack."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # is_mosaic=None → forces the coverage-distribution fallback; a real
    # single-field stack stores coverage_min=0 (uncovered border), max=frames.
    rid = _make_run(solved_library, safe, h=120, w=160,
                    coverage_min=0, coverage_max=6, is_mosaic=None)
    cov = np.zeros((120, 160), dtype=np.float32)
    cov[2:-2, 2:-2] = 6.0            # interior: all frames
    cov[1, :] = cov[-2, :] = 3.0     # thin reprojection-border ramp
    cov[:, 1] = cov[:, -2] = 3.0
    _write_coverage(solved_library, safe, cov)

    hist = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram").json()
    assert hist["is_mosaic"] is False


def test_histogram_legacy_mosaic_run_from_coverage_distribution(client, solved_library):
    """A legacy mosaic run (no persisted flag) is still recognised as a mosaic via
    its coverage distribution — two large plateaus at distinct levels."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=120, w=160,
                    coverage_min=0, coverage_max=8, is_mosaic=None)
    cov = np.zeros((120, 160), dtype=np.float32)
    cov[:, :80] = 4.0
    cov[:, 80:] = 8.0
    _write_coverage(solved_library, safe, cov)

    hist = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram").json()
    assert hist["is_mosaic"] is True


def test_trim_suggestion_mosaic_without_coverage_sibling(client, solved_library):
    """A mosaic run whose coverage sibling is missing yields no crop, not an error."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="nocov", is_mosaic=True)  # mosaic, no sibling
    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/trim-suggestion")
    assert r.status_code == 200
    body = r.json()
    assert body["is_mosaic"] is True and body["crop"] is None


def test_coverage_map_png(client, solved_library):
    """The coverage-map overlay renders the run's coverage sibling as a PNG."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100)
    cov = np.full((80, 100), 1.0, dtype=np.float32)
    cov[20:60, 25:75] = 5.0
    _write_coverage(solved_library, safe, cov)

    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/coverage-map")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_coverage_map_follows_recipe_geometry(client, solved_library):
    """With a crop op in the recipe, the coverage overlay is reshaped to match the
    cropped preview (smaller PNG), not the raw full frame — so it stays aligned."""
    import io as _io

    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100)
    cov = np.full((80, 100), 1.0, dtype=np.float32)
    cov[20:60, 25:75] = 5.0
    _write_coverage(solved_library, safe, cov)

    base = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/coverage-map")
    assert base.status_code == 200
    base_size = Image.open(_io.BytesIO(base.content)).size  # (w, h)

    recipe = {"ops": [{"id": "geometry.crop", "enabled": True,
                       "params": {"x0": 0.25, "y0": 0.25, "x1": 0.75, "y1": 0.75}}]}
    enc = base64.urlsafe_b64encode(json.dumps(recipe).encode()).decode()
    cropped = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/coverage-map?recipe={enc}")
    assert cropped.status_code == 200
    assert cropped.content[:8] == b"\x89PNG\r\n\x1a\n"
    crop_size = Image.open(_io.BytesIO(cropped.content)).size
    # The central 50%×50% crop yields a strictly smaller coverage map.
    assert crop_size[0] < base_size[0] and crop_size[1] < base_size[1]


def test_coverage_map_404_without_sibling(client, solved_library):
    """A run with no coverage sibling (single-field) has no coverage map → 404."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="nocovmap")
    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/coverage-map")
    assert r.status_code == 404


def test_star_mask_preview(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)

    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/star-mask")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # A custom star size is accepted and still renders.
    r2 = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/star-mask", params={"size_px": 6}
    )
    assert r2.status_code == 200
    assert r2.content[:8] == b"\x89PNG\r\n\x1a\n"


# Faint stars live in the bottom band (rows ≥ this); the two bright stars sit in
# the top corners. Measuring the mask only in the bottom band isolates the
# faint-star signal from the bright stars (whose mask saturates either way).
_FAINT_BAND_Y0 = 50


def _write_star_field_run(data_root, safe, basename="starfield", h=80, w=100):
    """A run whose master has two bright stars (top corners) and several faint ones
    (bottom band) on a low background — so the linear image buries the faint stars
    near the noise floor but a stretch reveals them (exactly the case the mask
    overlay must reflect)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            outdir = Path(proj.project_dir) / "output"
            outdir.mkdir(parents=True, exist_ok=True)
            rng = np.random.default_rng(1)
            cube = (rng.random((3, h, w)) * 0.008).astype("float32")  # dim sky
            yy, xx = np.mgrid[0:h, 0:w]

            def add_star(cx, cy, amp):
                blob = amp * np.exp(-(((xx - cx) / 1.2) ** 2 + ((yy - cy) / 1.2) ** 2))
                for c in range(3):
                    cube[c] += blob

            add_star(20, 20, 0.7)   # bright (top-left)
            add_star(85, 15, 0.6)   # bright (top-right)
            for cx, cy in [(40, 55), (55, 60), (30, 68), (65, 58), (48, 72), (70, 68)]:
                add_star(cx, cy, 0.09)  # faint — buried in linear noise, lifted by stretch
            fp = outdir / f"{basename}.fits"
            fits.writeto(fp, cube, overwrite=True)
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z", output_basename=basename,
                fits_path=str(fp), tiff_path=None, preview_path=None, n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=1,
                options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _faint_band_mask_weight(png_bytes):
    """Total mask weight (0..1 per px) in the faint-star band of the mask PNG."""
    import io as _io

    from PIL import Image
    arr = np.asarray(Image.open(_io.BytesIO(png_bytes)).convert("L")).astype(np.float32)
    return float(arr[_FAINT_BAND_Y0:].sum()) / 255.0


def test_star_mask_display_space_reveals_more_than_linear(client, solved_library):
    """Regression: the overlay must mask the display-space image the star ops gate
    on, not the raw linear proxy — where faint stars sit in the noise floor and are
    drastically under-represented. Passing a recipe (a stretch) must mark
    meaningfully more faint-star area than the recipe-less (linear) render."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _write_star_field_run(solved_library, safe)
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor/star-mask"

    linear = client.get(base)
    assert linear.status_code == 200
    # An empty recipe still triggers the display-space path: apply_recipe auto-adds
    # the default asinh stretch, so this is the post-stretch image the ops see.
    display = client.get(base, params={"recipe": _enc({"ops": [], "base_run_id": rid})})
    assert display.status_code == 200

    w_lin = _faint_band_mask_weight(linear.content)
    w_disp = _faint_band_mask_weight(display.content)
    # The stretch lifts the faint stars out of the noise, so the display-space mask
    # carries materially more weight over them than the linear one.
    assert w_disp > w_lin * 2.5


def test_star_mask_recipe_stops_before_selected_star_op(client, solved_library):
    """When a star op is selected (its uid passed), the mask is computed on the
    image *entering* that op — so a boost_nebula op after the stretch doesn't feed
    back into its own gate. The endpoint accepts recipe+uid and still renders."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _write_star_field_run(solved_library, safe)
    recipe = {"ops": [
        {"id": "tone.stretch", "params": {}, "enabled": True},
        {"id": "stars.boost_nebula", "uid": "star1", "params": {"size": 4}, "enabled": True},
    ], "base_run_id": rid}
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/star-mask",
        params={"recipe": _enc(recipe), "uid": "star1", "size_px": 4},
    )
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_star_mask_follows_recipe_crop(client, solved_library):
    """The star-mask overlay must be reshaped by the recipe's geometry ops (like
    the coverage overlay), so it lands in the same cropped frame as the edited
    preview / image box. Otherwise, shown in the cropped box, a full-frame mask
    squishes and its stars no longer line up with the edit."""
    from io import BytesIO

    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _write_star_field_run(solved_library, safe)  # 100x80
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor/star-mask"

    full = client.get(base, params={"recipe": _enc({"ops": [
        {"id": "tone.stretch", "params": {"mode": "stf"}, "enabled": True},
    ], "base_run_id": rid})})
    cropped = client.get(base, params={"recipe": _enc({"ops": [
        {"id": "tone.stretch", "params": {"mode": "stf"}, "enabled": True},
        {"id": "geometry.crop",
         "params": {"x0": 0.25, "y0": 0.0, "x1": 0.75, "y1": 1.0}, "enabled": True},
    ], "base_run_id": rid})})
    assert full.status_code == 200 and cropped.status_code == 200

    w_full = np.asarray(Image.open(BytesIO(full.content))).shape[1]
    w_crop = np.asarray(Image.open(BytesIO(cropped.content))).shape[1]
    # The half-width crop halves the mask's width so it tracks the cropped preview.
    assert w_crop < w_full


def test_auto_process(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, is_mosaic=True)
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/auto")
    assert r.status_code == 200
    op_objs = r.json()["ops"]
    ops = [o["id"] for o in op_objs]
    assert "tone.stretch" in ops
    # This run is a mosaic (persisted is_mosaic flag), so Auto prepends a
    # coverage-leveling pass before the gradient fit to flatten the panel steps.
    assert "background.level_coverage" in ops
    assert ops.index("background.level_coverage") < ops.index("tone.stretch")
    # No coverage sibling written here → no meaningful trim → no crop appended.
    assert "geometry.crop" not in ops
    # Auto carries a gentle contrast curve (auto-derived at apply time) after the
    # saturation boost, matching the built-in presets.
    assert "tone.curves" in ops
    assert ops.index("tone.saturation") < ops.index("tone.curves")
    curve = next(o for o in op_objs if o["id"] == "tone.curves")
    assert curve["params"]["auto"] is True


def test_auto_process_trims_ragged_mosaic_border(client, solved_library):
    """On a mosaic whose coverage sibling has a ragged low-coverage border, Auto
    appends a final geometry.crop to the well-covered interior so the one-click
    result is cleanly framed (reusing the Trim-border machinery)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=True)  # mosaic
    cov = np.full((80, 100), 1.0, dtype=np.float32)
    cov[15:65, 20:80] = 5.0  # a well-covered interior inside a low-coverage border
    _write_coverage(solved_library, safe, cov)

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/auto")
    assert r.status_code == 200
    ops = r.json()["ops"]
    ids = [o["id"] for o in ops]
    assert ids[-1] == "geometry.crop"  # trim runs last
    # The coverage-leveling op still runs before the crop (on the uncropped frame).
    assert ids.index("background.level_coverage") < ids.index("geometry.crop")
    crop = ops[-1]["params"]
    # The crop tightens onto the interior (strictly inside the full 0..1 frame).
    assert crop["x0"] > 0.0 and crop["y0"] > 0.0
    assert crop["x1"] < 1.0 and crop["y1"] < 1.0


def test_auto_process_single_field_not_cropped(client, solved_library):
    """A single-field stack (uniform coverage) is never trimmed by Auto."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100, is_mosaic=False)
    cov = np.full((80, 100), 3.0, dtype=np.float32)
    _write_coverage(solved_library, safe, cov)

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/auto")
    assert r.status_code == 200
    assert "geometry.crop" not in [o["id"] for o in r.json()["ops"]]


def test_export_creates_new_run_non_destructive(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}},
                      {"id": "tone.saturation", "params": {"amount": 1.2}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "edited1"})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    names = {x["output_basename"] for x in runs}
    assert "edited1" in names               # new edited run exists
    assert any(x["id"] == rid for x in runs)  # original run untouched
    edited = next(x for x in runs if x["output_basename"] == "edited1")
    assert edited["has_fits"] and edited["notes"] == "edited"


def test_export_marks_run_display_space(client, solved_library):
    """An editor export is a tone-mapped display-space image, so the new run is
    marked both in its options_json (display_space) and in its FITS (SSDISPLY) —
    so re-opening it doesn't double-stretch and external tools know it's not
    linear ADU. Regression for the re-edit double-stretch / dishonest-FITS bug."""
    from seestack.stack.output import fits_is_display_space

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="disp_src")
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "disp_edit"})
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "disp_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            opts = json.loads(new_run.options_json)
            assert opts["display_space"] is True
            assert fits_is_display_space(new_run.fits_path) is True
            # The source (linear) run is unaffected.
            src = next(r for r in proj.iter_stack_runs() if r.id == rid)
            assert fits_is_display_space(src.fits_path) is False
        finally:
            proj.close()
    finally:
        lib.close()


def _register_display_space_run(data_root, safe, basename, options_json):
    """Write a mid-grey [0,1] display-space FITS and register a run pointing at it
    with the given options_json (so the editor's display-space handling can be
    exercised without a real export)."""
    from seestack.stack.output import write_stack_outputs

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            ramp = np.clip(np.linspace(0.0, 1.0, 100, dtype=np.float32), 0, 1)
            rgb = np.repeat(np.tile(ramp, (80, 1))[..., None], 3, axis=2)  # mean ~0.5
            cov = np.ones(rgb.shape[:2], dtype=np.float32)
            paths = write_stack_outputs(Path(proj.project_dir), rgb, cov, wcs_text=None,
                                        out_basename=basename, already_display=True)
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z", output_basename=basename,
                fits_path=str(paths["fits"]), tiff_path=None, preview_path=None,
                n_frames_used=5, canvas_h=80, canvas_w=100, coverage_min=1,
                coverage_max=1, options_json=options_json,
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def test_reopening_display_space_run_does_not_double_stretch(client, solved_library):
    """The editor preview of a display-space run with an empty recipe renders it
    verbatim (mean ~0.5 grey), not double-stretched. The SAME data registered
    WITHOUT the display_space flag falls back to the default asinh (a materially
    different look) — proving the flag drives the fix, and old runs are
    unaffected."""
    from io import BytesIO

    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    disp_id = _register_display_space_run(solved_library, safe, "dd_disp",
                                          json.dumps({"display_space": True}))
    lin_id = _register_display_space_run(solved_library, safe, "dd_lin",
                                         json.dumps({}))

    empty = _enc({"ops": []})
    disp_png = client.get(
        f"/api/targets/{safe}/stack-runs/{disp_id}/editor/preview?recipe={empty}").content
    lin_png = client.get(
        f"/api/targets/{safe}/stack-runs/{lin_id}/editor/preview?recipe={empty}").content

    disp_mean = np.asarray(Image.open(BytesIO(disp_png)).convert("RGB")).mean()
    lin_mean = np.asarray(Image.open(BytesIO(lin_png)).convert("RGB")).mean()
    assert abs(disp_mean - 127) <= 8            # verbatim ~0.5 ramp, not re-stretched
    assert abs(lin_mean - disp_mean) > 20       # the fallback asinh changes the look


def test_export_reports_failed_ops_in_result(client, solved_library, monkeypatch):
    """An op that raises on the full-res data is dropped best-effort, but its
    failure is threaded into the export job result (op_errors) so the editor can
    warn the user the exported look changed silently — not just logged away."""
    from seestack.edit.registry import get_op

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)

    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(get_op("tone.saturation"), "apply", boom)
    recipe = {"ops": [{"id": "tone.stretch", "params": {}},
                      {"id": "tone.saturation", "params": {"amount": 1.2}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "with_failure"})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job                 # bad op didn't sink the export
    errs = job["result"]["op_errors"]
    assert any("kaboom" in e for e in errs), errs


def test_export_clean_recipe_has_no_op_errors(client, solved_library):
    """A recipe whose ops all succeed reports an empty op_errors list."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    recipe = {"ops": [{"id": "tone.stretch", "params": {}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "clean"})
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done"
    assert job["result"]["op_errors"] == []


def test_export_carries_provenance_headers(client, solved_library):
    """The derived master.fits keeps the source integration provenance
    (OBJECT/NFRAMES/EXPTOTAL) and records how it was produced (STACKMTD/EDITFROM)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="prov_src")
    # Stamp provenance cards onto the source FITS, as a real stack would.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == rid)
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header["OBJECT"] = "M42"
                hdul[0].header["NFRAMES"] = 840
                hdul[0].header["EXPTOTAL"] = 2520.0
                hdul[0].header["STACKER"] = "sigma-clip"
        finally:
            proj.close()
    finally:
        lib.close()

    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "prov_edit"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "prov_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            hdr = fits.getheader(new_run.fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    # Integration provenance carried forward…
    assert hdr["OBJECT"] == "M42"
    assert int(hdr["NFRAMES"]) == 840
    assert float(hdr["EXPTOTAL"]) == 2520.0
    # …and the derivation is recorded.
    assert "editor recipe" in str(hdr["STACKMTD"])
    assert int(hdr["EDITFROM"]) == rid


def test_export_records_deconvolution_psf_header(client, solved_library):
    """An editor recipe with a deconvolution op stamps the PSF sigma actually
    used into the derived master.fits (DECONPSF), self-documenting the sharpen."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="deconv_src")
    recipe = {"ops": [
        {"id": "tone.stretch", "params": {"stretch": 0.6}},
        {"id": "detail.deconvolve", "params": {"psf_sigma": 2.3}},
    ]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "deconv_edit"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "deconv_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            hdr = fits.getheader(new_run.fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    assert float(hdr["DECONPSF"]) == 2.3
    # …and the Info endpoint surfaces it as a provenance card.
    info = client.get(f"/api/targets/{safe}/stack-runs/{edited['id']}/info").json()
    assert any(c["key"] == "DECONPSF" for c in info["cards"])


def test_export_no_deconvolution_omits_psf_header(client, solved_library):
    """A recipe without a deconvolution op leaves no DECONPSF card."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="nodeconv_src")
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "nodeconv_edit"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "nodeconv_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            hdr = fits.getheader(new_run.fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    assert "DECONPSF" not in hdr


def test_export_records_recipe_history(client, solved_library):
    """The derived master.fits records each enabled editor op as a FITS HISTORY
    card, so an edited export self-documents its full processing chain."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="hist_src")
    recipe = {"ops": [
        {"id": "tone.stretch", "params": {"stretch": 0.6}},
        {"id": "detail.denoise", "params": {"method": "tv", "strength": 0.4},
         "enabled": False},  # disabled ops are not recorded
        {"id": "detail.sharpen", "params": {"amount": 1.2}},
    ]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "hist_edit"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    edited = next(x for x in runs if x["output_basename"] == "hist_edit")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_run = next(r for r in proj.iter_stack_runs() if r.id == edited["id"])
            hdr = fits.getheader(new_run.fits_path)
        finally:
            proj.close()
    finally:
        lib.close()
    history = "\n".join(str(c) for c in hdr["HISTORY"])
    assert "tone.stretch" in history
    assert "detail.sharpen" in history
    assert "detail.denoise" not in history  # disabled op omitted

    # The Info endpoint surfaces the same chain as a friendly, ordered list so
    # the History panel can show "Processing: Stretch → Sharpen".
    info = client.get(f"/api/targets/{safe}/stack-runs/{edited['id']}/info").json()
    chain = info["processing"]
    assert [s["op"] for s in chain] == ["tone.stretch", "detail.sharpen"]
    assert [s["label"] for s in chain] == ["Stretch", "Sharpen"]


def test_info_processing_chain_empty_for_plain_stack(client, solved_library):
    """A plain (non-edited) stack has no AstroStack HISTORY cards, so the Info
    endpoint reports an empty processing chain rather than erroring."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, basename="plain_src")
    info = client.get(f"/api/targets/{safe}/stack-runs/{rid}/info").json()
    assert info["processing"] == []


def test_export_sanitizes_path_traversal_output_name(client, solved_library, tmp_path):
    # output_name is free text from the client and is spliced into a
    # filename under <project>/output/; a path-separator payload must not
    # be able to write outside the project (write_stack_outputs sanitizes
    # it rather than failing the job outright).
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": recipe, "output_name": "../../../../tmp/pwned"})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert not (Path("/tmp") / "pwned.fits").exists()


def test_presets_crud(client):
    base = client.get("/api/editor/presets").json()
    assert any(p["id"] == "nebula_broadband" for p in base["builtin"])
    assert base["user"] == []

    created = client.post("/api/editor/presets", json={
        "label": "My Look", "ops": [{"id": "tone.stretch", "params": {"stretch": 0.7}}],
    }).json()
    assert created["label"] == "My Look"
    after = client.get("/api/editor/presets").json()
    assert any(p["id"] == created["id"] for p in after["user"])

    client.delete(f"/api/editor/presets/{created['id']}")
    assert client.get("/api/editor/presets").json()["user"] == []


def test_batch_apply(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r1 = _make_run(solved_library, safe, basename="a")
    r2 = _make_run(solved_library, safe, basename="b")
    body = {
        "items": [{"safe": safe, "run_id": r1}, {"safe": safe, "run_id": r2}],
        "preset_id": "galaxy_broadband",
        "output_name": "batchout",
    }
    r = client.post("/api/editor/batch", json=body)
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert len(job["result"]["exported"]) == 2


def test_export_png_full_res_download(client, solved_library):
    import io

    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, h=80, w=100)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}

    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export-png",
                    json={"recipe": recipe})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job

    dl = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/png/{r.json()['job_id']}")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("image/png")
    assert "attachment" in dl.headers.get("content-disposition", "")
    # Full resolution: PNG matches the native canvas (w=100, h=80).
    img = Image.open(io.BytesIO(dl.content))
    assert img.size == (100, 80)


def test_export_png_reports_failed_ops_in_result(client, solved_library, monkeypatch):
    """The full-res PNG render (the download path) threads a dropped op's failure
    into its job result (op_errors) too, so the editor can warn on download."""
    from seestack.edit.registry import get_op

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)

    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(get_op("tone.saturation"), "apply", boom)
    recipe = {"ops": [{"id": "tone.stretch", "params": {}},
                      {"id": "tone.saturation", "params": {"amount": 1.2}}]}
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export-png",
                    json={"recipe": recipe})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    assert any("kaboom" in e for e in job["result"]["op_errors"])


def test_histogram_reports_op_errors(client, solved_library, monkeypatch):
    from seestack.edit.registry import get_op

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)

    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(get_op("tone.saturation"), "apply", boom)
    recipe = {"ops": [{"id": "tone.stretch", "params": {}},
                      {"id": "tone.saturation", "params": {"amount": 1.2}}]}
    h = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={_enc(recipe)}").json()
    assert any("kaboom" in e for e in h["errors"])


def test_stf_stretch_renders_non_black(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    recipe = {"ops": [{"id": "tone.stretch", "params": {"mode": "stf", "target_bg": 0.2}}]}
    h = client.get(
        f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram?recipe={_enc(recipe)}").json()
    assert h["empty"] is False
    assert sum(h["r"]) > 0 and h["errors"] == []


def test_histogram_flags_empty_stack(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]

    # A normal stack is not empty.
    rid = _make_run(solved_library, safe)
    h = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/histogram").json()
    assert h["empty"] is False

    # An all-NaN stack (failed solve/stack) is flagged empty, not a 500.
    nan_id = _make_run(solved_library, safe, basename="blank")
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == nan_id)
            cube = np.full((3, 80, 100), np.nan, dtype="float32")
            fits.writeto(run.fits_path, cube, overwrite=True)
        finally:
            proj.close()
    finally:
        lib.close()
    hb = client.get(f"/api/targets/{safe}/stack-runs/{nan_id}/editor/histogram")
    assert hb.status_code == 200
    assert hb.json()["empty"] is True
