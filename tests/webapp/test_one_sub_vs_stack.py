"""'One frame vs your stack' reveal — info endpoint + rendered reference sub.

A beginner drops hundreds of subs in and gets one clean picture but never sees
the *before*. These read-only endpoints power a card that puts a single raw sub
next to the finished stack, stretched identically so the only visible difference
is the noise/detail stacking bought.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, *, with_preview: bool,
                  ts: str = "2026-05-01T00:00:00Z") -> int:
    """Add a stack run to ``safe`` (optionally with a real preview PNG on disk)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            preview_path = None
            if with_preview:
                preview = Path(lib.target_dir(lib.find_target(safe))) / f"prev_{ts[:10]}.png"
                Image.new("RGB", (4, 4), (10, 20, 30)).save(preview)
                preview_path = str(preview)
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts,
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=preview_path, n_frames_used=42,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=42,
                options_json=json.dumps({"output_name": "m42"}),
                total_exposure_s=1260.0,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_info_available_carries_the_caption_fields(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    # Caption fields come from the run's own provenance (best-effort, may be null
    # for sub_exposure_s if a frame carries no exposure).
    assert body["n_frames"] == 42
    assert body["integration_s"] == 1260.0
    assert "sub_exposure_s" in body


def test_info_unavailable_without_a_preview_to_compare(client, solved_library):
    # A run with no stored preview has nothing to compare against → available
    # false (the card self-hides), not a 404.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=False)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_info_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/one-sub-vs-stack")
    assert r.status_code == 404


def test_reference_sub_renders_a_real_png(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/reference-sub")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    im = Image.open(BytesIO(r.content))
    # A genuine debayered sub, not a 1×1 placeholder: decodes and has real extent.
    assert im.mode == "RGB"
    assert im.width > 1 and im.height > 1


def test_reference_sub_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/reference-sub")
    assert r.status_code == 404


def _register_run_with_master_and_preview(
    data_root, safe: str, master_path: Path, *, display_space: bool = False,
) -> int:
    """Register a run with a real master FITS *and* a real preview PNG on disk —
    what ``save_stack_preview`` (the History "Adjust" save) needs to overwrite."""
    _write_linear_master(master_path, sigma=2.0, display_space=display_space)
    lib = Library.open_or_create(data_root / "library")
    try:
        preview = master_path.with_suffix(".png")
        Image.new("RGB", (4, 4), (10, 20, 30)).save(preview)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(master_path), tiff_path=None,
                preview_path=str(preview), n_frames_used=42,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=42,
                options_json="{}", total_exposure_s=1260.0,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_info_unavailable_for_a_display_space_export(client, solved_library):
    # An edited / display-space export's preview is a bespoke tone-mapped image a
    # raw sub can't be honestly matched to (the reveal would show two different
    # tone curves), so the card self-hides — matching the noise-ratio endpoint,
    # which already bails on the same runs. Fail-before: available was gated only
    # on has_preview, so a display-space run wrongly offered the reveal.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "edited.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=True)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_info_unavailable_for_an_in_place_auto_edited_run(client, solved_library):
    # An in-place "Process target" Auto edit rewrites only the preview PNG to the
    # recipe's tone-mapped result; its FITS stays linear, so fits_is_display_space
    # is False. The run instead carries a `preview_display_space` marker, and the
    # reveal must self-hide on it just like a display-space export — otherwise it
    # shows a raw STF sub beside the recipe-toned stack. Fail-before: with a linear
    # FITS and no FITS-header stamp, the reveal wrongly reported available.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "autoedited.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=False)
    # Mark the run's preview as a tone-mapped Auto edit (what _auto_edit_process_run
    # does after rewriting the preview PNG).
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_run_preview_display_space(run_id) is True
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack")
    assert r.status_code == 200
    assert r.json()["available"] is False

    # And the Adjust stretch suggestion anchors nothing (its curve can't match a
    # recipe result) — self-hiding to Adjust's neutral defaults.
    sug = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render-suggestion")
    assert sug.status_code == 200
    assert sug.json()["stretch"] is None and sug.json()["black"] is None


def test_saved_custom_stretch_re_renders_the_reference_sub_to_match(client, solved_library):
    # After the History "Adjust" panel saves a custom asinh stretch, the reveal's
    # sub half must render through the *same* curve so the two halves differ only
    # in noise/detail — not a brightness/tone offset (the feature's honesty
    # promise). Fail-before: reference-sub was hard-coded to STF and ignored the
    # saved stretch, so its bytes were identical to the default render.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "linear.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(solved_library, safe, master)

    default_png = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/reference-sub").content

    # Save a strong custom stretch (History "Adjust").
    saved = client.post(
        f"/api/targets/{safe}/stack-runs/{run_id}/preview",
        json={"stretch": 0.9, "black": 0.8})
    assert saved.status_code == 200

    custom_png = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/reference-sub").content
    # The sub is now rendered through the saved asinh curve, so its pixels differ
    # from the default STF render of the same frame.
    assert custom_png != default_png

    # And the run persisted the saved stretch so the render is reproducible.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    assert run.preview_stretch == 0.9
    assert run.preview_black == 0.8


def test_saved_stretch_on_a_display_space_run_stays_null(client, solved_library):
    # A display-space export ignores the sliders (rendered verbatim), so saving a
    # "stretch" must not record a curve the reveal would then wrongly apply to a
    # raw sub — the columns stay NULL and the card self-hides anyway.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "edited2.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=True)

    saved = client.post(
        f"/api/targets/{safe}/stack-runs/{run_id}/preview",
        json={"stretch": 0.9, "black": 0.8})
    assert saved.status_code == 200

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    assert run.preview_stretch is None and run.preview_black is None


# --- "stacking cut your noise ~N×" number -----------------------------------

def _register_run_with_master(data_root, safe: str, master_path: Path) -> int:
    """Register a run whose master FITS is the file at ``master_path``."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(master_path), tiff_path=None,
                preview_path=None, n_frames_used=42,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=42,
                options_json="{}", total_exposure_s=1260.0,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _write_linear_master(path: Path, sigma: float, *, display_space: bool = False,
                         shape=(320, 480), seed: int = 0) -> None:
    """Write a 3-channel linear (or, if flagged, display-space) master FITS."""
    import numpy as np
    from astropy.io import fits

    from seestack.stack.output import DISPLAY_SPACE_CARD

    rng = np.random.default_rng(seed)
    cube = rng.normal(0.0, sigma, size=(3, *shape)).astype(np.float32)
    hdu = fits.PrimaryHDU(cube)
    if display_space:
        hdu.header[DISPLAY_SPACE_CARD] = True
    hdu.writeto(path, overwrite=True)


def test_noise_ratio_measured_from_a_real_master(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "master.fits"
    finally:
        lib.close()
    _write_linear_master(master, sigma=2.0)   # far quieter than a raw sub (σ≈50)
    run_id = _register_run_with_master(solved_library, safe, master)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise")
    assert r.status_code == 200
    ratio = r.json()["ratio"]
    # A real noisy sub over a near-silent master → a large, finite reduction.
    assert ratio is not None and ratio > 1.0


def test_noise_ratio_null_for_a_display_space_export(client, solved_library):
    # An edited / display-space export has no meaningful linear σ → null, so the
    # badge omits the number rather than printing a bogus ratio.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "edited.fits"
    finally:
        lib.close()
    _write_linear_master(master, sigma=2.0, display_space=True)
    run_id = _register_run_with_master(solved_library, safe, master)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise")
    assert r.status_code == 200
    assert r.json()["ratio"] is None


def test_noise_ratio_null_without_a_master_on_disk(client, solved_library):
    # A run with no master FITS (older/edited run) → null, not an error.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)  # fits_path=None
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise")
    assert r.status_code == 200
    assert r.json()["ratio"] is None


def test_noise_ratio_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/one-sub-vs-stack/noise")
    assert r.status_code == 404
