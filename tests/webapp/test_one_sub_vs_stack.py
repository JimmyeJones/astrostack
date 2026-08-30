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


# --- "Share your glow-up": the downloadable before/after -------------------
#
# The reveal above lives in the app; this is the portable artefact — the one
# picture a non-astro friend understands. It must be gated exactly as the reveal
# is, so the download button can never offer an unfair pairing.


def test_before_after_downloads_one_composed_jpeg(client, solved_library):
    from seestack.beforeafter import DEFAULT_WIDTH

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    # Saved, not shown inline, and named after the run so two downloads don't
    # overwrite each other.
    assert "attachment" in r.headers["content-disposition"]
    assert "master_before-after.jpg" in r.headers["content-disposition"]
    im = Image.open(BytesIO(r.content))
    assert im.width == DEFAULT_WIDTH
    # Two half-cells side by side plus a caption bar — wider than it is tall.
    assert im.height < im.width


def test_before_after_captions_itself_from_the_runs_own_provenance(
    client, solved_library, monkeypatch,
):
    # The picture is only shareable if it *says* what it shows: the target's
    # name, the comparison, and the integration — all read off the run, none of
    # it typed by the user.
    import seestack.beforeafter as ba

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)
    seen: dict = {}
    real = ba.build_before_after

    def capture(before, after, **kw):
        seen.update(kw)
        return real(before, after, **kw)

    monkeypatch.setattr(ba, "build_before_after", capture)

    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg").status_code == 200
    assert "42 frames stacked" in seen["caption"]      # n_frames_used
    assert "21m of light" in seen["caption"]           # total_exposure_s = 1260 s
    assert seen["labels"][1] == "42 frames stacked"
    # And it names the target rather than leading with the comparison.
    assert seen["caption"].split(" · ")[0] not in ("", "one frame")


def test_before_after_404_without_a_preview_to_compare(client, solved_library):
    # No stored picture → nothing to put beside the sub. A 404 (not a lopsided
    # image) is what lets the button self-hide, exactly as the card does.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=False)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg")
    assert r.status_code == 404


def test_before_after_404_for_a_display_space_export(client, solved_library):
    # An edited export's preview is a bespoke tone-mapped image a raw sub can't
    # be honestly matched to — the same gate the reveal itself uses. Without it
    # the download would sell a tone difference as what stacking bought you.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "edited_ba.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=True)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg")
    assert r.status_code == 404


def test_before_after_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get("/api/targets/%s/stack-runs/999999/before-after.jpg" % safe)
    assert r.status_code == 404


def test_before_after_is_not_swallowed_by_the_artifact_download_route(
    client, solved_library,
):
    # `/{kind}` is a catch-all registered later in the same router; if this
    # endpoint ever moves below it, "before-after.jpg" becomes an unknown
    # artifact kind and the feature silently 404s on a healthy run.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_before_after_honours_the_saved_custom_stretch(client, solved_library):
    # The sub half must be rendered through the run's *saved* curve, like the
    # in-app reveal: otherwise the downloaded picture shows a tone offset the
    # card doesn't, and the "only the noise changed" promise breaks on export.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "linear_ba.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(solved_library, safe, master)

    url = f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg"
    default_jpeg = client.get(url).content
    assert client.post(
        f"/api/targets/{safe}/stack-runs/{run_id}/preview",
        json={"stretch": 0.9, "black": 0.8}).status_code == 200
    custom_jpeg = client.get(url).content
    assert custom_jpeg != default_jpeg


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


def test_noise_ratio_reads_only_the_central_crop_of_the_master(
    client, solved_library, monkeypatch,
):
    """The measurement must not materialise the whole master to look at a patch.

    This endpoint is fetched **eagerly** — once per Target-page load and on every
    finished "Process target" card — and it used to do
    ``asarray(fits.getdata(path), dtype=float32)``. FITS is big-endian, so that
    cast is a full copy and byte-swap of the entire canvas: ~1.8 GB of transient
    allocation for a 150 MP mosaic master on the RAM-capped NAS, to measure a
    1024² patch. Pinning it by *breaking* the whole-file read: the endpoint must
    still produce its number with ``fits.getdata`` unavailable, which it can only
    do by slicing the memory-mapped HDU first (fails before this fix).
    """
    from astropy.io import fits

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "master_big.fits"
    finally:
        lib.close()
    _write_linear_master(master, sigma=2.0)
    run_id = _register_run_with_master(solved_library, safe, master)

    def _no_full_read(*a, **kw):  # pragma: no cover - only runs if the fix regresses
        raise AssertionError("read the whole master to measure a central crop")

    monkeypatch.setattr(fits, "getdata", _no_full_read)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise")
    assert r.status_code == 200
    assert r.json()["ratio"] is not None


def test_noise_ratio_is_unchanged_by_the_windowed_read(client, solved_library):
    """Same pixels, same number — the crop is the *same* patch it always was.

    A master larger than the 1024 px crop on one axis exercises the offset maths
    on the windowed read; the ratio must match the one computed from the naive
    whole-array path over the identical central crop.
    """
    import numpy as np
    from astropy.io import fits

    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw
    from seestack.qc.noise_ratio import noise_ratio
    from webapp.routers.stack import _NOISE_CROP_PX, _crop_origin, _measure_noise_ratio

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        frames = list(Library.open_or_create(solved_library / "library").open_target(safe)
                      .iter_frames(accepted_only=True))
    finally:
        lib.close()
    master = tdir / "master_wide.fits"
    _write_linear_master(master, sigma=2.0, shape=(1100, 1400), seed=7)
    sub_path = frames[0].source_path

    # Naive path: whole array in, then crop — what the code used to do.
    arr = np.asarray(fits.getdata(master), dtype=np.float32)
    y0, x0 = _crop_origin(arr.shape[1], arr.shape[2])
    want_stack = np.transpose(
        arr[:, y0:y0 + _NOISE_CROP_PX, x0:x0 + _NOISE_CROP_PX], (1, 2, 0))
    raw, info = load_seestar_raw(sub_path, debayer=False, out_dtype=np.float32)
    sub = bilinear_debayer(raw, pattern=(info.bayer_pattern or "RGGB"))
    sy, sx = _crop_origin(*sub.shape[:2])
    want = noise_ratio(sub[sy:sy + _NOISE_CROP_PX, sx:sx + _NOISE_CROP_PX], want_stack)

    got = _measure_noise_ratio(str(master), str(sub_path), info.bayer_pattern or "RGGB")
    assert got == want


# ---- the measurement is remembered, per run ------------------------------
#
# This endpoint is fetched eagerly — once per Target-page load, and on every
# finished "Process target" card — and each miss reloads the master's crop and
# debayers a full native-resolution sub for a number that is a pure function of
# two immutable things. The first measurement is stamped on the run; the tests
# below pin both halves: that a repeat view doesn't measure again, and that a
# stamp is never served once the thing it was measured from has changed.


def _count_measurements(monkeypatch):
    """Wrap ``_measure_noise_ratio`` with a call counter, keeping its behaviour."""
    from webapp.routers import stack as stack_router

    real = stack_router._measure_noise_ratio
    calls: list[int] = []

    def counted(*a, **kw):
        calls.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(stack_router, "_measure_noise_ratio", counted)
    return calls


def _master_for(solved_library, safe, name, **kw) -> Path:
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / name
    finally:
        lib.close()
    _write_linear_master(master, **kw)
    return master


def test_noise_ratio_is_measured_once_and_remembered(
    client, solved_library, monkeypatch,
):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_for(solved_library, safe, "master_cached.fits", sigma=2.0)
    run_id = _register_run_with_master(solved_library, safe, master)
    calls = _count_measurements(monkeypatch)

    url = f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise"
    first = client.get(url)
    second = client.get(url)

    assert first.status_code == second.status_code == 200
    assert first.json()["ratio"] is not None
    # Same number, and the second view never reopened the master or the sub.
    assert second.json()["ratio"] == first.json()["ratio"]
    assert len(calls) == 1


def test_noise_ratio_remembers_a_null_too(client, solved_library, monkeypatch):
    # A display-space export has no meaningful linear sigma. That "no number"
    # answer is as stable as a number is, and re-deriving it costs the same FITS
    # open — so it is cached as well.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_for(
        solved_library, safe, "edited_cached.fits", sigma=2.0, display_space=True)
    run_id = _register_run_with_master(solved_library, safe, master)
    calls = _count_measurements(monkeypatch)

    url = f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise"
    assert client.get(url).json()["ratio"] is None
    assert client.get(url).json()["ratio"] is None
    assert len(calls) == 1


def test_noise_ratio_is_re_measured_when_the_master_changes(
    client, solved_library, monkeypatch,
):
    # The run row is immutable, but the master is addressed by path. A stamp
    # must never outlive the pixels it was measured from.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_for(solved_library, safe, "master_rewritten.fits", sigma=2.0)
    run_id = _register_run_with_master(solved_library, safe, master)
    calls = _count_measurements(monkeypatch)

    url = f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise"
    before = client.get(url).json()["ratio"]
    # A different master at the same path: noisier, so a genuinely different
    # ratio — which a stale stamp would hide.
    _write_linear_master(master, sigma=20.0, seed=3)
    after = client.get(url).json()["ratio"]

    assert len(calls) == 2
    assert before is not None and after is not None
    assert after != before


def test_noise_ratio_is_re_measured_when_the_representative_sub_changes(
    client, solved_library, monkeypatch,
):
    # `_pick_reference_sub` picks the *sharpest accepted* frame, so rejecting it
    # changes which sub the comparison is against — and therefore the answer.
    from seestack.io.project import Project

    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_for(solved_library, safe, "master_refswap.fits", sigma=2.0)
    run_id = _register_run_with_master(solved_library, safe, master)
    calls = _count_measurements(monkeypatch)

    url = f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise"
    assert client.get(url).json()["ratio"] is not None
    assert len(calls) == 1

    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
    finally:
        lib.close()
    proj = Project.open(tdir)
    try:
        from webapp.routers.stack import _pick_reference_sub

        chosen = _pick_reference_sub(proj)
        assert chosen is not None
        proj.update_frame(chosen.id, accept=0, reject_reason="test")
    finally:
        proj.close()

    assert client.get(url).json()["ratio"] is not None
    assert len(calls) == 2


def test_deleting_a_run_takes_its_noise_stamp_with_it(client, solved_library):
    # The stamp is per-run; an orphan row nothing will ever read is exactly what
    # `webapp.run_meta` exists to prevent.
    from seestack.io.project import Project
    from webapp.routers.stack import NOISE_RATIO_META_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    master = _master_for(solved_library, safe, "master_purged.fits", sigma=2.0)
    run_id = _register_run_with_master(solved_library, safe, master)
    client.get(f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise")

    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
    finally:
        lib.close()
    proj = Project.open(tdir)
    try:
        assert proj.get_meta(f"{NOISE_RATIO_META_PREFIX}{run_id}") is not None
    finally:
        proj.close()

    assert client.delete(f"/api/targets/{safe}/stack-runs/{run_id}").status_code == 200

    proj = Project.open(tdir)
    try:
        assert proj.get_meta(f"{NOISE_RATIO_META_PREFIX}{run_id}") is None
    finally:
        proj.close()


# --- The one-click "Process target" path -------------------------------------
#
# `_auto_edit_process_run` rewrites the run's preview to the Auto recipe's
# tone-mapped result and stamps `preview_display_space` — which used to hide the
# reveal (and the before/after share built on it) from the *flagship* beginner
# journey, since a raw STF sub can't honestly be matched to a recipe-toned stack.
# It doesn't have to be hidden: that run keeps a linear FITS and stores the very
# recipe its preview shows, so the sub can be put through the same ops. These pin
# that the recipe path opens exactly those runs and nothing else.


def _mark_auto_edited(data_root, safe: str, run_id: int,
                      recipe_json: str | None) -> None:
    """Make a run look like an in-place "Process target" Auto edit: the
    `preview_display_space` marker plus (optionally) the recipe its preview shows."""
    from webapp.routers.editor import RECIPE_META_PREFIX

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_run_preview_display_space(run_id) is True
            if recipe_json is not None:
                proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", recipe_json)
        finally:
            proj.close()
    finally:
        lib.close()


def _auto_recipe_json() -> str:
    """A realistic Auto recipe — built by the same `presets.auto_recipe` the
    one-click path uses, so the tests exercise the real op list (gradient →
    colour calibrate → STF stretch → SCNR → saturation → curves), not a toy."""
    import numpy as np

    from seestack.edit.presets import auto_recipe

    rng = np.random.default_rng(7)
    rgb = np.clip(rng.normal(0.05, 0.01, size=(64, 96, 3)), 0.0, 1.0).astype(np.float32)
    return auto_recipe(rgb, median_fwhm=3.0).to_json()


def test_auto_edited_run_offers_the_reveal_through_its_own_recipe(
    client, solved_library,
):
    # Fail-before: an in-place Auto edit reported available=False, so the app's
    # most convincing moment was missing from the one button a beginner is
    # pointed at ("Process target").
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "autoedit_ok.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=False)
    _mark_auto_edited(solved_library, safe, run_id, _auto_recipe_json())

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack").json()
    assert body["available"] is True
    # ...and it says *how* the halves were matched, so the caption can be honest
    # about both sides carrying the same edit.
    assert body["matched_by"] == "recipe"


def test_a_plain_linear_run_still_reports_the_stretch_match(client, solved_library):
    # The additive field must not re-label the common case: a plain stack is
    # still matched by a shared tone curve, not by a recipe.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, with_preview=True)

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack").json()
    assert body["available"] is True
    assert body["matched_by"] == "stretch"


def test_auto_edited_reference_sub_is_rendered_through_the_recipe(
    client, solved_library,
):
    # The whole point of opening the gate: the "before" must carry the *same*
    # processing as the shown picture. Proven by the render differing from the
    # plain STF render of the same sub — if the recipe were ignored the two would
    # be byte-identical.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "autoedit_sub.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=False)

    plain = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/reference-sub")
    assert plain.status_code == 200

    _mark_auto_edited(solved_library, safe, run_id, _auto_recipe_json())
    through = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/reference-sub")
    assert through.status_code == 200
    assert through.headers["content-type"] == "image/png"
    im = Image.open(BytesIO(through.content))
    assert im.mode == "RGB" and im.width > 1 and im.height > 1
    assert through.content != plain.content


def test_auto_edited_run_downloads_the_before_after(client, solved_library):
    # The share button is gated on the same endpoint, so it must light up here
    # too — this is the run a beginner actually has to share.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "autoedit_ba.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=False)
    _mark_auto_edited(solved_library, safe, run_id, _auto_recipe_json())

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_a_display_space_export_stays_hidden_even_with_a_recipe(
    client, solved_library,
):
    # The gate is opened by the *in-place* marker on a linear FITS, never by a
    # recipe alone. A genuine export's FITS is itself tone-mapped, so there is no
    # linear picture behind it and a recipe on it describes a second-round edit —
    # rendering a raw sub through that would be exactly the unfair pairing this
    # feature must never show.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "export_recipe.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=True)
    _mark_auto_edited(solved_library, safe, run_id, _auto_recipe_json())

    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack",
    ).json()["available"] is False
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg").status_code == 404


def test_auto_edited_run_with_an_unreadable_recipe_stays_hidden(
    client, solved_library,
):
    # Without a recipe we can't know what the stored preview shows, so guessing
    # (an STF sub beside a recipe-toned stack) is worse than hiding. Garbage and
    # a recipe with no `ops` list are both "no recipe".
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        target_dir = Path(lib.target_dir(lib.find_target(safe)))
    finally:
        lib.close()
    for i, bad in enumerate(["not json at all", '{"version": 3}', "[]"]):
        run_id = _register_run_with_master_and_preview(
            solved_library, safe, target_dir / f"autoedit_bad{i}.fits",
            display_space=False)
        _mark_auto_edited(solved_library, safe, run_id, bad)
        assert client.get(
            f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack",
        ).json()["available"] is False, bad


def test_the_real_process_target_auto_edit_leaves_the_reveal_working(
    client, solved_library,
):
    """End-to-end on the *actual* one-click path, not a fabricated marker.

    This is the dogfood finding itself, in the suite: run `_auto_edit_process_run`
    — the function "Process target" calls — over a real linear master, then ask
    the app the same two questions the dogfood pass asked. Before this change both
    answered "no": `{"available": false}` and a 404 reading "This run's picture is
    an edited export…".
    """
    from webapp.pipeline import _auto_edit_process_run

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "processed.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=False)

    lib = Library.open_or_create(solved_library / "library")
    try:
        n_ops = _auto_edit_process_run(lib, safe, run_id)
    finally:
        lib.close()
    assert n_ops, "the auto-edit must actually have applied ops"

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack").json()
    assert body["available"] is True
    assert body["matched_by"] == "recipe"
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/reference-sub").status_code == 200
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg").status_code == 200


def test_a_re_edited_auto_run_hides_the_reveal_again(client, solved_library):
    """The stored recipe stops describing the stored preview the moment the user
    re-opens a "Process target" run, changes something and presses **Save** — the
    recipe is rewritten, the baked preview PNG is not.

    Without the baked-look stamp nothing could tell, so the reveal happily rendered
    the "before" through the *new* recipe against a preview showing the *old* one:
    the two halves would then differ by an edit as well as by frame count, which is
    the one thing this comparison must never show. With the stamp it stands down to
    hidden, exactly as it does when the recipe is missing entirely.
    """
    from webapp.pipeline import _auto_edit_process_run

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "redited.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=False)

    lib = Library.open_or_create(solved_library / "library")
    try:
        assert _auto_edit_process_run(lib, safe, run_id)
    finally:
        lib.close()

    # Straight off the auto-edit the two agree, so the reveal is offered.
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack",
    ).json()["available"] is True

    # Now the second-round edit: a different look, saved and never exported.
    r = client.put(
        f"/api/targets/{safe}/stack-runs/{run_id}/editor/recipe",
        json={"ops": [{"id": "tone.saturation", "params": {"amount": 1.9}}]})
    assert r.status_code == 200

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack").json()
    assert body["available"] is False
    # ...and the before/after share, gated on the same decision, goes with it.
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg",
    ).status_code == 404


def test_re_saving_the_same_look_keeps_the_reveal(client, solved_library):
    """The guard must fire on a *changed* picture, not on a Save. Re-saving the
    recipe the auto-edit already baked re-stamps its ``updated_utc`` and gives every
    op a fresh ``uid``; compared by look (as everywhere else), that is the same
    picture and the reveal stays open."""
    from webapp.pipeline import _auto_edit_process_run
    from webapp.routers.editor import RECIPE_META_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "resaved.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=False)

    lib = Library.open_or_create(solved_library / "library")
    try:
        assert _auto_edit_process_run(lib, safe, run_id)
        proj = lib.open_target(safe)
        try:
            baked = json.loads(proj.get_meta(f"{RECIPE_META_PREFIX}{run_id}"))
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.put(f"/api/targets/{safe}/stack-runs/{run_id}/editor/recipe",
                   json={"ops": baked["ops"]})
    assert r.status_code == 200

    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack",
    ).json()["available"] is True


def test_an_auto_edit_from_before_the_stamp_is_unchanged(client, solved_library):
    """Upgrade safety: a run auto-edited by an older build carries a recipe and the
    display-space marker but **no** baked-look stamp. "Can't tell" must read as
    "assume they agree" — the behaviour that shipped in v0.301.0 — so the reveal is
    still offered on every picture the owner already has."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        master = Path(lib.target_dir(lib.find_target(safe))) / "prestamp.fits"
    finally:
        lib.close()
    run_id = _register_run_with_master_and_preview(
        solved_library, safe, master, display_space=False)
    # _mark_auto_edited writes exactly what the old build wrote: marker + recipe.
    _mark_auto_edited(solved_library, safe, run_id, _auto_recipe_json())

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack").json()
    assert body["available"] is True
    assert body["matched_by"] == "recipe"
