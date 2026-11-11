"""The editor's Download PNG / Share / Print files are reclaimed (Scout
2026-11-11, QA rotation sweep (4)).

Each click wrote a timestamped file into the target's ``output/`` only so the
job's download GET could hand it over — ~43 MB per mosaic PNG — and neither a
run's Delete nor "Prune old stacks" ever removed one. Now a newer click of the
same button replaces the older file, and deleting the run removes them all.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from seestack.stack.output import editor_download_kind, editor_download_paths

RECIPE = {"ops": [{"id": "tone.stretch", "params": {"stretch": 0.6}}]}
OLD = "20200101_000000"


def _make_run(data_root, safe, basename, *, ts="2026-05-02T00:00:00Z",
              h=80, w=100) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            outdir = Path(proj.project_dir) / "output"
            outdir.mkdir(parents=True, exist_ok=True)
            fp = outdir / f"{basename}.fits"
            rng = np.random.default_rng(0)
            fits.writeto(fp, (rng.random((3, h, w)) * 0.1).astype("float32"),
                         overwrite=True)
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename=basename,
                fits_path=str(fp), tiff_path=None, preview_path=None,
                n_frames_used=5, canvas_h=h, canvas_w=w, coverage_min=1,
                coverage_max=5, options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _outdir(data_root, safe) -> Path:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return Path(proj.project_dir) / "output"
        finally:
            proj.close()
    finally:
        lib.close()


def _plant(outdir: Path, name: str) -> Path:
    p = outdir / name
    p.write_bytes(b"an old download")
    return p


def _wait_job(client, job_id, timeout=120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "error", "cancelled", "interrupted"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish in time")


def _export(client, safe, rid, kind: str) -> dict:
    route = {"png": "export-png", "share": "share"}[kind]
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/{route}",
                    json={"recipe": RECIPE})
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    return job


def test_deleting_a_run_removes_its_editor_downloads(client, solved_library):
    """The Scout's repro: two runs, downloads on one, delete it — every
    download it made is gone, and the other run's files are untouched."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, "alpha")
    other = _make_run(solved_library, safe, "beta")
    out = _outdir(solved_library, safe)
    png = Path(_export(client, safe, rid, "png")["result"]["png_path"])
    share = Path(_export(client, safe, rid, "share")["result"]["jpeg_path"])
    old_print = _plant(out, f"alpha_print_A4_{OLD}.jpg")
    beta_dl = _plant(out, f"beta_edit_{OLD}.png")
    assert png.exists() and share.exists()

    r = client.delete(f"/api/targets/{safe}/stack-runs/{rid}")
    assert r.status_code == 200, r.text
    assert not png.exists() and not share.exists() and not old_print.exists()
    assert beta_dl.exists()
    assert (out / "beta.fits").exists()
    assert other in [run["id"] for run in
                     client.get(f"/api/targets/{safe}/stack-runs").json()]


def test_prune_old_stacks_reclaims_their_editor_downloads(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _make_run(solved_library, safe, "older", ts="2026-01-01T00:00:00Z")
    _make_run(solved_library, safe, "newer", ts="2026-12-01T00:00:00Z")
    out = _outdir(solved_library, safe)
    gone = _plant(out, f"older_share_{OLD}.jpg")
    kept = _plant(out, f"newer_share_{OLD}.jpg")
    r = client.post(f"/api/targets/{safe}/stack-runs/prune", json={"keep": 1})
    assert r.status_code == 200, r.text
    assert not gone.exists()
    assert kept.exists()


def test_a_new_download_replaces_the_older_one_of_the_same_kind(
        client, solved_library):
    """Repeat clicks of one button keep one file; the other buttons' files
    (and another paper size) are left alone."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, "alpha")
    out = _outdir(solved_library, safe)
    old_png = _plant(out, f"alpha_edit_{OLD}.png")
    share = _plant(out, f"alpha_share_{OLD}.jpg")
    a4 = _plant(out, f"alpha_print_A4_{OLD}.jpg")
    new_png = Path(_export(client, safe, rid, "png")["result"]["png_path"])
    assert new_png.exists() and not old_png.exists()
    assert share.exists() and a4.exists()
    assert editor_download_paths(out, "alpha", kind="edit") == [new_png]


def test_a_replaced_download_link_says_so_plainly(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe, "alpha")
    job = _export(client, safe, rid, "png")
    Path(job["result"]["png_path"]).unlink()      # what a newer click does
    r = client.get(f"/api/targets/{safe}/stack-runs/{rid}/editor/png/{job['id']}")
    assert r.status_code == 404
    assert "Export it again" in r.json()["detail"]


def test_a_basename_another_row_still_carries_keeps_its_downloads(
        client, solved_library):
    """Two rows under one basename (the pre-guard shared shape): the downloads
    are keyed by that name, so deleting one row must not take the other's."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    first = _make_run(solved_library, safe, "shared", ts="2026-01-01T00:00:00Z")
    _make_run(solved_library, safe, "shared", ts="2026-02-01T00:00:00Z")
    dl = _plant(_outdir(solved_library, safe), f"shared_edit_{OLD}.png")
    assert client.delete(f"/api/targets/{safe}/stack-runs/{first}").status_code == 200
    assert dl.exists()


def test_the_match_is_exact_to_the_run_and_the_kind():
    assert editor_download_kind(f"M_42_edit_{OLD}.png", "M_42") == "edit"
    assert editor_download_kind(f"M_42_share_{OLD}.jpg", "M_42") == "share"
    assert editor_download_kind(f"M_42_print_10x8in_{OLD}.jpg", "M_42") == "print_10x8in"
    # Another run whose name merely starts the same, run artefacts, wrong type:
    assert editor_download_kind(f"M_42b_edit_{OLD}.png", "M_42") is None
    assert editor_download_kind("M_42_share.png", "M_42") is None
    assert editor_download_kind("M_42_preview.png", "M_42") is None
    assert editor_download_kind("M_42.fits", "M_42") is None
    assert editor_download_kind(f"M_42_edit_{OLD}.jpg", "M_42") is None
