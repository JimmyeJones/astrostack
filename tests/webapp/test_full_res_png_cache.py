"""The Full-res PNG is cached beside its run (owner ⭐ 2026-10-28, "Speed").

He reported the download "takes a super long time". Measured: the render is
whole-canvas work — ~6 s for a 3494×2470 mosaic, ~25 s at 5000×7000 on the agent
container (the STF's medians and the PNG encode), slower on a NAS — and it was
paid again on every click, including the second click of a button that seemed to
do nothing, which started a *second* render beside the first. These pin that a
repeat download is served from ``<basename>_fullres.cache``, byte-for-byte the
render, that every input the render reads invalidates it, and that a click while
a render is running waits for it instead of rendering twice.
"""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp import pipeline


def _add_run(data_root, safe: str, *, w: int = 160, h: int = 120) -> tuple[int, Path]:
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = Path(tdir) / f"cached_{w}x{h}.fits"
        rng = np.random.default_rng(4)
        fits.PrimaryHDU(data=rng.random((3, h, w), dtype=np.float32) * 200.0).writeto(
            fits_path, overwrite=True)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="cached", fits_path=str(fits_path),
                tiff_path=None, preview_path=None, n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id, fits_path
    finally:
        lib.close()


def _count_renders(monkeypatch) -> list[int]:
    calls: list[int] = []
    real = pipeline.render_run_full_res_png

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(pipeline, "render_run_full_res_png", counting)
    return calls


def _run_row(fits_path: Path, **extra) -> StackRunRow:
    fields = {
        "id": 1, "timestamp_utc": "2026-05-01T00:00:00Z", "output_basename": "m",
        "fits_path": str(fits_path), "tiff_path": None, "preview_path": None,
        "n_frames_used": 5, "canvas_h": 40, "canvas_w": 50, "coverage_min": 1,
        "coverage_max": 5, "options_json": "{}",
    }
    return StackRunRow(**{**fields, **extra})


def _write_master(path: Path, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    fits.PrimaryHDU(data=rng.random((3, 40, 50), dtype=np.float32) * 100.0).writeto(
        path, overwrite=True)


def test_a_repeat_download_is_served_from_the_cache(client, solved_library, monkeypatch):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path = _add_run(solved_library, safe)
    calls = _count_renders(monkeypatch)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png"

    first = client.get(url)
    second = client.get(url)
    assert first.status_code == second.status_code == 200
    assert len(calls) == 1                       # the second click rendered nothing
    assert second.content == first.content       # …and is the very same picture
    with Image.open(io.BytesIO(second.content)) as im:
        assert im.size == (160, 120)
    assert fits_path.with_name("cached_160x120_fullres.cache").is_file()
    # The cached bytes are the render's own — what the uncached path hands over.
    assert first.content == pipeline.render_run_full_res_png(
        _run_row(fits_path), None, max_long_edge=8000, trim_border=True)


def test_a_new_master_or_a_north_up_ask_renders_afresh(client, solved_library, monkeypatch):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path = _add_run(solved_library, safe)
    calls = _count_renders(monkeypatch)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png"

    before = client.get(url).content
    client.get(f"{url}?north_up=true")
    assert len(calls) == 2                        # a different ask is a different picture
    # A re-stack writes a new master under the same name.
    rng = np.random.default_rng(99)
    fits.PrimaryHDU(data=rng.random((3, 120, 160), dtype=np.float32) * 50.0).writeto(
        fits_path, overwrite=True)
    after = client.get(url).content
    assert len(calls) == 3
    assert after != before


def test_switching_the_border_trim_renders_afresh(client, solved_library, monkeypatch):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _ = _add_run(solved_library, safe)
    calls = _count_renders(monkeypatch)
    url = f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png"
    client.get(url)
    assert client.put("/api/settings", json={"auto_crop_border": False}).status_code == 200
    client.get(url)
    assert len(calls) == 2


def test_the_signature_follows_every_input_the_render_reads(tmp_path, monkeypatch):
    from seestack.edit.proxy import frame_coverage_path_for

    master = tmp_path / "m.fits"
    _write_master(master)
    run = _run_row(master)
    kw = {"north_up": False, "max_long_edge": 8000, "trim_border": True}
    base = pipeline.full_res_png_signature(run, None, **kw)
    assert pipeline.full_res_png_signature(run, None, **kw) == base       # stable

    changed = [
        pipeline.full_res_png_signature(run, '{"ops": []}', **kw),
        pipeline.full_res_png_signature(run, None, **{**kw, "north_up": True}),
        pipeline.full_res_png_signature(run, None, **{**kw, "trim_border": False}),
        pipeline.full_res_png_signature(run, None, **{**kw, "max_long_edge": 4000}),
        pipeline.full_res_png_signature(_run_row(master, preview_stretch=0.4,
                                                 preview_black=0.3), None, **kw),
        pipeline.full_res_png_signature(_run_row(master, preview_north_up_deg=90.0),
                                        None, **kw),
    ]
    assert base not in changed
    # The trim is measured on the coverage maps, so one appearing is a new picture.
    fits.PrimaryHDU(data=np.ones((40, 50), np.float32)).writeto(
        frame_coverage_path_for(master))
    with_cov = pipeline.full_res_png_signature(run, None, **kw)
    assert with_cov != base
    # A stored preview rewritten (History's "Adjust", a North-up save).
    preview = tmp_path / "m_preview.png"
    Image.new("RGB", (8, 6)).save(preview)
    assert pipeline.full_res_png_signature(
        _run_row(master, preview_path=str(preview)), None, **kw) != with_cov
    # A new release's renderer never serves last release's pixels.
    monkeypatch.setattr(pipeline, "APP_VERSION", "0.0.0-test")
    assert pipeline.full_res_png_signature(run, None, **kw) != with_cov


def test_a_click_during_a_running_render_waits_for_it(tmp_path, monkeypatch):
    """Two requests for one picture at once render it once: the second waits for
    the first and is handed the cached bytes."""
    master = tmp_path / "m.fits"
    _write_master(master)
    run = _run_row(master)
    calls: list[int] = []
    gate = threading.Event()

    def slow(*_a, **_k):
        calls.append(1)
        gate.wait(5)
        return b"\x89PNG-slow"

    monkeypatch.setattr(pipeline, "render_run_full_res_png", slow)
    results: list[bytes] = []
    threads = [threading.Thread(target=lambda: results.append(
        pipeline.cached_run_full_res_png(run, None))) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in threads:
        t.join(10)
    assert results == [b"\x89PNG-slow", b"\x89PNG-slow"]
    assert len(calls) == 1


def test_the_archive_reads_the_cache_but_never_writes_one(tmp_path, monkeypatch):
    master = tmp_path / "m.fits"
    _write_master(master)
    run = _run_row(master)
    cache = pipeline.full_res_png_cache_path(run)
    assert cache == tmp_path / "m_fullres.cache"

    calls = _count_renders(monkeypatch)
    pipeline.cached_run_full_res_png(run, None, write=False)
    assert not cache.exists() and len(calls) == 1
    downloaded = pipeline.cached_run_full_res_png(run, None)       # the button
    assert cache.exists() and len(calls) == 2
    assert pipeline.cached_run_full_res_png(run, None, write=False) == downloaded
    assert len(calls) == 2


def test_a_stale_or_foreign_cache_file_is_never_served(tmp_path, monkeypatch):
    master = tmp_path / "m.fits"
    _write_master(master)
    run = _run_row(master)
    cache = pipeline.full_res_png_cache_path(run)
    cache.write_bytes(b"0" * 40 + b"\nnot this picture")
    calls = _count_renders(monkeypatch)
    png = pipeline.cached_run_full_res_png(run, None)
    assert len(calls) == 1 and png.startswith(b"\x89PNG")
    assert cache.read_bytes().endswith(png)                  # replaced, not appended


def test_an_unwritable_cache_still_hands_over_the_picture(tmp_path, monkeypatch):
    master = tmp_path / "m.fits"
    _write_master(master)
    run = _run_row(master)

    def refuse(self, *_a, **_k):
        raise OSError("read-only output folder")

    monkeypatch.setattr(Path, "replace", refuse)
    png = pipeline.cached_run_full_res_png(run, None)
    assert png.startswith(b"\x89PNG")
    assert not list(tmp_path.glob("*.tmp"))                    # no litter left behind


def test_the_cache_is_one_of_the_runs_files(tmp_path):
    """Named from the master's own stem, like every sibling. Registered, so deleting a run reclaims it and a re-stack archives it with
    the master it was rendered from."""
    from webapp.routers.storage import run_artifact_paths

    master = tmp_path / "m.fits"
    assert tmp_path / "m_fullres.cache" in run_artifact_paths(str(master))
