"""An unedited mosaic's *stored preview* is trimmed too (owner ⭐ 2026-10-28, the
rest of slice (1)).

v0.503.23 trimmed the ragged, colour-confetti border off an unedited mosaic's
Full-res PNG and archive picture, but the share JPEG and the wallpaper serve the
stored preview — or a native render that must match it — so they still handed the
whole fringe over. Now a fresh stack's stored preview is cut to the rectangle the
editor's Auto would trim (``pipeline.trim_unedited_stored_preview``), the crop is
recorded in ``stack_runs.preview_crop_json`` so every surface that lines up with
the preview composes it, and the native share/wallpaper render reproduces that
recorded crop instead of declining it.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _ragged_frame_counts(h: int, w: int) -> np.ndarray:
    """A 2×2 mosaic's frame-count map: four panels of 25 dithered, slightly
    rotated subs, so the canvas edge is stepped and ramps over a few subs — NaN
    where none reached. (The shape ``test_full_res_png`` measures the trim on.)"""
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    count = np.zeros((h, w), np.float32)
    ph, pw = 0.5 * h, 0.5 * w
    for pcy, pcx in ((0.26 * h, 0.26 * w), (0.26 * h, 0.74 * w),
                     (0.74 * h, 0.26 * w), (0.74 * h, 0.74 * w)):
        for _ in range(25):
            cy = pcy + rng.uniform(-16, 16)
            cx = pcx + rng.uniform(-16, 16)
            t = np.deg2rad(rng.uniform(-2.0, 2.0))
            u = (xx - cx) * np.cos(t) + (yy - cy) * np.sin(t)
            v = -(xx - cx) * np.sin(t) + (yy - cy) * np.cos(t)
            count += ((np.abs(u) < pw / 2) & (np.abs(v) < ph / 2))
    count[count == 0] = np.nan
    return count


_seq = 0


def _add_mosaic_run(data_root, safe: str, *, w: int = 2400, h: int = 1800,
                    is_mosaic: bool = True, options: dict | None = None
                    ) -> tuple[int, str]:
    """An unedited mosaic run exactly as a stack leaves one: a linear master whose
    fringe is per-pixel colour speckle (NaN where nothing landed), its frame-count
    sibling, and the stored preview the stacker writes — the STF render of the
    whole canvas, capped at 1024 px. Returns ``(run_id, preview_path)``."""
    global _seq
    _seq += 1
    from seestack.edit.proxy import frame_coverage_path_for
    from seestack.stack.output import _write_preview_png

    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        base = f"mosaic{_seq}"
        fits_path = tdir / f"{base}.fits"
        counts = _ragged_frame_counts(h, w)
        rng = np.random.default_rng(3)
        cube = (np.full((3, h, w), 50.0, np.float32)
                + rng.normal(0, 1, (3, h, w)).astype(np.float32))
        thin = ~np.isfinite(counts) | (counts < 12)
        cube[:, thin] = rng.random((3, int(thin.sum())), dtype=np.float32) * 400.0
        cube[:, ~np.isfinite(counts)] = np.nan
        fits.PrimaryHDU(data=cube).writeto(fits_path, overwrite=True)
        fits.PrimaryHDU(data=counts).writeto(frame_coverage_path_for(fits_path),
                                             overwrite=True)
        preview_path = tdir / f"{base}_preview.png"
        _write_preview_png(preview_path, np.moveaxis(cube, 0, -1))
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename=base, fits_path=str(fits_path),
                tiff_path=None, preview_path=str(preview_path), n_frames_used=100,
                canvas_h=h, canvas_w=w, coverage_min=0, coverage_max=100,
                options_json=json.dumps(options or {}), is_mosaic=is_mosaic,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id, str(preview_path)
    finally:
        lib.close()


def _trim(data_root, safe: str, run_id: int, *, enabled: bool = True) -> bool:
    from webapp.pipeline import trim_unedited_stored_preview

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return trim_unedited_stored_preview(proj, run_id, enabled=enabled)
        finally:
            proj.close()
    finally:
        lib.close()


def _row(data_root, safe: str, run_id: int):  # noqa: ANN202
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()


def _size(content: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(content)) as im:
        return im.size


def _speckle(content: bytes) -> int:
    """Pixels of the bright, multi-coloured fringe — the flat interior renders as
    an even dark sky, so anything over mid-grey is the band."""
    with Image.open(io.BytesIO(content)) as im:
        arr = np.asarray(im.convert("RGB"), dtype=np.float32)
    return int((arr.max(axis=2) > 128).sum())


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


def _rect(fits_path: str) -> tuple[float, float, float, float]:
    from webapp.routers.editor import _trim_rect_for_run

    rect = _trim_rect_for_run(SimpleNamespace(fits_path=fits_path, is_mosaic=True))
    assert rect is not None
    return rect


# ---------------------------------------------------------------------------
# The stored preview itself


def test_an_unedited_mosaic_preview_is_cut_to_autos_rectangle(client, solved_library):
    """The stored bytes become exactly Auto's rectangle of themselves — a crop, not
    a re-render, so the tone is the preview's own — and the crop is recorded."""
    from seestack.edit.ops.geometry import crop_bounds
    from seestack.previewcrop import PreviewCrop, parse_preview_crop

    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe)
    before = Path(preview_path).read_bytes()
    assert _speckle(before) > 1000              # the fixture does carry the band
    pw, ph = _size(before)
    rect = _rect(_row(solved_library, safe, run_id).fits_path)

    assert _trim(solved_library, safe, run_id) is True

    after = Path(preview_path).read_bytes()
    cx0, cx1, cy0, cy1 = crop_bounds(ph, pw, dict(zip(("x0", "y0", "x1", "y1"),
                                                      rect, strict=True)))
    assert _size(after) == (cx1 - cx0, cy1 - cy0)
    # A border trim, not a collapse (AGENTS.md §1: > ~15 % would be a bug).
    assert (cx1 - cx0) * (cy1 - cy0) > 0.85 * pw * ph
    with Image.open(io.BytesIO(before)) as im:
        want = np.asarray(im.convert("RGB"))[cy0:cy1, cx0:cx1]
    with Image.open(io.BytesIO(after)) as im:
        np.testing.assert_array_equal(np.asarray(im.convert("RGB")), want)
    assert _speckle(after) < 0.01 * _speckle(before)

    crop = parse_preview_crop(_row(solved_library, safe, run_id).preview_crop_json)
    assert isinstance(crop, PreviewCrop)
    assert crop.as_tuple() == tuple(rect)


def test_the_trim_is_done_once(client, solved_library):
    """A second pass finds the crop recorded and leaves the bytes alone — cutting
    an already-trimmed picture again would eat into the sky."""
    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe)
    assert _trim(solved_library, safe, run_id) is True
    once = Path(preview_path).read_bytes()
    assert _trim(solved_library, safe, run_id) is False
    assert Path(preview_path).read_bytes() == once


def test_switched_off_the_preview_keeps_the_whole_canvas(client, solved_library):
    """``auto_crop_border`` off is the owner keeping his full frame."""
    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe)
    before = Path(preview_path).read_bytes()
    assert _trim(solved_library, safe, run_id, enabled=False) is False
    assert Path(preview_path).read_bytes() == before
    assert _row(solved_library, safe, run_id).preview_crop_json is None


def test_a_single_field_preview_is_never_trimmed(client, solved_library):
    """The same rule as Auto: only a mosaic's border is trimmed."""
    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe, is_mosaic=False)
    before = Path(preview_path).read_bytes()
    assert _trim(solved_library, safe, run_id) is False
    assert Path(preview_path).read_bytes() == before


def test_a_processed_preview_is_left_to_its_recipe(client, solved_library):
    """A display-space preview is a finished edit whose framing is its own."""
    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(
        solved_library, safe, options={"preview_display_space": True})
    before = Path(preview_path).read_bytes()
    assert _trim(solved_library, safe, run_id) is False
    assert Path(preview_path).read_bytes() == before


# ---------------------------------------------------------------------------
# What the owner downloads and shares


def test_the_share_jpeg_of_an_unedited_mosaic_is_trimmed_and_full_size(
        client, solved_library):
    """The share JPEG is Auto's rectangle at the master's resolution — not the
    ragged canvas (before), and not a re-encode of the 1024 px trimmed preview
    (which a native render that declined the crop would have given)."""
    safe = _safe(client)
    run_id, _ = _add_mosaic_run(solved_library, safe)
    whole = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg").content
    assert _size(whole) == (2400, 1800)          # the fringe and all, before
    assert _trim(solved_library, safe, run_id) is True

    fullres = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert fullres.status_code == 200
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert r.status_code == 200
    # The same picture as the Full-res PNG download (v0.503.23's trim).
    assert _size(r.content) == _size(fullres.content)
    assert max(_size(r.content)) > 1024
    assert _speckle(r.content) < 0.01 * _speckle(whole)


def test_the_wallpaper_of_an_unedited_mosaic_has_no_fringe(client, solved_library):
    safe = _safe(client)
    run_id, _ = _add_mosaic_run(solved_library, safe)
    before = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=desktop").content
    assert _trim(solved_library, safe, run_id) is True
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=desktop")
    assert r.status_code == 200
    assert _speckle(before) > 1000
    assert _speckle(r.content) < 0.01 * _speckle(before)


def test_the_run_listing_reports_the_trim(client, solved_library):
    """Every surface that lines up with the stored preview reads this field."""
    safe = _safe(client)
    run_id, _ = _add_mosaic_run(solved_library, safe)
    assert _trim(solved_library, safe, run_id) is True
    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    got = next(r for r in runs if r["id"] == run_id)
    assert got["preview_crop"] is not None
    assert got["preview_crop"]["x0"] > 0


# ---------------------------------------------------------------------------
# Wired into the stack job


def _wait_job(client, job_id, timeout=120):  # noqa: ANN001, ANN202
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled", "interrupted"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def _stack(client) -> dict:
    r = client.post("/api/targets/M_42/stack", json={})
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body
    return client.get("/api/targets/M_42/stack-runs").json()[0]


def test_a_finished_stack_trims_its_stored_preview(client, solved_library, monkeypatch):
    """The stack job itself applies the trim, so a fresh mosaic lands trimmed with
    nobody pressing anything. (The fixture's stack is a single field, so the
    mosaic rule is stood in for; the rule itself is pinned above.)"""
    from webapp import pipeline

    monkeypatch.setattr(pipeline, "unedited_border_trim",
                        lambda run: (0.1, 0.1, 0.9, 0.9))
    from seestack.edit.ops.geometry import crop_bounds
    from seestack.render.thumbnail import preview_grid_size

    run = _stack(client)
    assert run["preview_crop"] == {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}
    pw, ph = preview_grid_size(run["canvas_w"], run["canvas_h"])
    cx0, cx1, cy0, cy1 = crop_bounds(ph, pw, run["preview_crop"])
    with Image.open(_row(solved_library, "M_42", run["id"]).preview_path) as im:
        assert im.size == (cx1 - cx0, cy1 - cy0)


def test_an_ordinary_single_field_stack_is_untouched(client, solved_library):
    run = _stack(client)
    assert run["preview_crop"] is None


# ---------------------------------------------------------------------------
# Pictures stacked before v0.504.2: the boot-time backfill


def _backfill(data_root) -> dict:
    from webapp.pipeline import backfill_unedited_preview_trims, scan_unedited_trim_backfill

    lib = Library.open_or_create(data_root / "library")
    try:
        return backfill_unedited_preview_trims(lib, scan_unedited_trim_backfill(lib))
    finally:
        lib.close()


def _scan(data_root) -> list[str]:
    from webapp.pipeline import scan_unedited_trim_backfill

    lib = Library.open_or_create(data_root / "library")
    try:
        return scan_unedited_trim_backfill(lib)
    finally:
        lib.close()


def test_an_older_untrimmed_preview_is_backfilled_once(client, solved_library):
    """A run whose stored preview predates the trim gets exactly the crop a fresh
    stack would have, recorded; the target is then stamped and never rescanned."""
    from seestack.previewcrop import PreviewCrop, parse_preview_crop

    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe)
    before = Path(preview_path).read_bytes()
    assert _scan(solved_library) == [safe]

    out = _backfill(solved_library)

    assert out["trimmed_targets"] == [safe] and not out["failed"]
    after = Path(preview_path).read_bytes()
    assert _size(after) != _size(before)
    assert _speckle(after) < 0.01 * _speckle(before)
    crop = parse_preview_crop(_row(solved_library, safe, run_id).preview_crop_json)
    assert isinstance(crop, PreviewCrop)
    assert crop.as_tuple() == tuple(_rect(_row(solved_library, safe, run_id).fits_path))
    assert _scan(solved_library) == []
    assert _backfill(solved_library)["trimmed_targets"] == []
    assert Path(preview_path).read_bytes() == after


def test_the_backfill_leaves_single_fields_and_edited_previews_alone(client, solved_library):
    safe = _safe(client)
    _, single = _add_mosaic_run(solved_library, safe, is_mosaic=False)
    _, edited = _add_mosaic_run(solved_library, safe,
                                options={"preview_display_space": True})
    before = {p: Path(p).read_bytes() for p in (single, edited)}
    _backfill(solved_library)
    for p, b in before.items():
        assert Path(p).read_bytes() == b


def test_a_displaced_older_row_does_not_cut_the_shared_preview_twice(client, solved_library):
    """A pre-v0.81.8 pair names one preview file; it is the later run's picture,
    so it is cut once and the crop is recorded on that run alone."""
    from seestack.edit.ops.geometry import crop_bounds

    safe = _safe(client)
    old_id, preview_path = _add_mosaic_run(solved_library, safe)
    old = _row(solved_library, safe, old_id)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            new_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename=old.output_basename, fits_path=old.fits_path,
                tiff_path=None, preview_path=old.preview_path, n_frames_used=100,
                canvas_h=old.canvas_h, canvas_w=old.canvas_w, coverage_min=0,
                coverage_max=100, options_json="{}", is_mosaic=True,
            ))
        finally:
            proj.close()
    finally:
        lib.close()
    pw, ph = _size(Path(preview_path).read_bytes())

    _backfill(solved_library)

    rect = _rect(old.fits_path)
    cx0, cx1, cy0, cy1 = crop_bounds(ph, pw, dict(zip(("x0", "y0", "x1", "y1"),
                                                      rect, strict=True)))
    assert _size(Path(preview_path).read_bytes()) == (cx1 - cx0, cy1 - cy0)
    assert _row(solved_library, safe, new_id).preview_crop_json
    assert not _row(solved_library, safe, old_id).preview_crop_json


def test_with_the_trim_switched_off_nothing_is_queued(client, solved_library):
    from webapp import deps
    from webapp.pipeline import submit_unedited_preview_trim_backfill

    safe = _safe(client)
    _, preview_path = _add_mosaic_run(solved_library, safe)
    before = Path(preview_path).read_bytes()
    assert client.put("/api/settings", json={"auto_crop_border": False}).status_code == 200
    app = client.app
    settings = deps.get_settings(SimpleNamespace(app=app))
    assert submit_unedited_preview_trim_backfill(settings, app.state.job_manager) is None
    assert Path(preview_path).read_bytes() == before
    assert _scan(solved_library) == [safe]          # still owed, if he turns it on


def test_booting_the_app_trims_an_older_preview(solved_library, monkeypatch):
    """End to end: an install upgraded in place, with a picture stacked before
    v0.504.2 on disk, comes up and queues the trim with nobody pressing anything."""
    from fastapi.testclient import TestClient

    from tests.webapp_boot import disable_watcher_before_boot
    from webapp.main import create_app

    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
    finally:
        lib.close()
    run_id, preview_path = _add_mosaic_run(solved_library, safe)
    before = _size(Path(preview_path).read_bytes())
    monkeypatch.setenv("ASTROSTACK_DATA", str(solved_library))
    monkeypatch.setenv("ASTROSTACK_LOG_LEVEL", "WARNING")
    disable_watcher_before_boot(solved_library)
    with TestClient(create_app()) as c:
        jobs = [j for j in c.get("/api/jobs").json()
                if j["kind"] == "unedited_preview_trim"]
        assert len(jobs) == 1
        assert _wait_job(c, jobs[0]["id"])["state"] == "done"
    assert _size(Path(preview_path).read_bytes()) != before
    assert _row(solved_library, safe, run_id).preview_crop_json
