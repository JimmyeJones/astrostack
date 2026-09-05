"""The full-size half of "Download all my pictures".

``/api/gallery/pictures.zip`` hands over each target's stored **preview** — the
picture at the size the app shows it, capped at 1024 px — which is right for a
phone album and wrong for printing, as the card that offers it says. These tests
cover the other answer: a job that renders every picture at native resolution
into one archive, and the download that hands it over.

What they pin is what makes it trustworthy: the pictures really are full size,
they are the *same* render the per-run "Full-res PNG" button produces (one
definition, not two), a picture that can't be rendered is still in the archive
and *says* it is the smaller one, and the whole thing writes nothing except the
archive itself.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_run(data_root, safe: str, *, w: int, h: int, with_fits: bool = True,
             with_preview: bool = True, basename: str = "master",
             timestamp_utc: str = "2026-05-01T00:00:00Z") -> int:
    """A finished run for ``safe``: a master FITS to render from and the small
    preview every screen shows. Returns the run id."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        tdir.mkdir(parents=True, exist_ok=True)
        fits_path = None
        if with_fits:
            fits_path = tdir / f"{basename}_{w}x{h}.fits"
            rng = np.random.default_rng(7)
            cube = (rng.random((3, h, w), dtype=np.float32) * 200.0)
            fits.PrimaryHDU(data=cube).writeto(fits_path, overwrite=True)
        preview_path = None
        if with_preview:
            preview_path = tdir / f"{basename}_preview.png"
            # The real preview is capped at 1024 px; a small one stands in.
            Image.new("RGB", (64, 48), (20, 40, 70)).save(preview_path)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=timestamp_utc,
                output_basename=basename,
                fits_path=str(fits_path) if fits_path else None,
                tiff_path=None,
                preview_path=str(preview_path) if preview_path else None,
                n_frames_used=5, canvas_h=h, canvas_w=w,
                coverage_min=1, coverage_max=5, options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _safes(client) -> list[str]:
    return [t["safe_name"] for t in client.get("/api/targets").json()]


def _wait_job(client, job_id, timeout=120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["state"] in ("done", "error", "cancelled", "interrupted"):
            return j
        time.sleep(0.1)
    raise AssertionError("archive job did not finish in time")


def _build(client) -> dict:
    r = client.post("/api/gallery/pictures-archive")
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    return {"job_id": r.json()["job_id"], "job": job}


def _archive(client, job_id) -> zipfile.ZipFile:
    r = client.get(f"/api/gallery/pictures-archive/{job_id}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(r.content))


def test_archive_holds_every_picture_at_full_resolution(client, solved_library):
    """One member per target, and each one is the *native* canvas — not the
    1024 px preview the streaming zip hands over."""
    safes = _safes(client)
    assert len(safes) >= 2
    for i, safe in enumerate(safes):
        _add_run(solved_library, safe, w=1400 + i, h=1100)

    built = _build(client)
    assert built["job"]["result"]["n_pictures"] == len(safes)
    assert built["job"]["result"]["n_full_res"] == len(safes)
    zf = _archive(client, built["job_id"])
    assert sorted(zf.namelist()) == sorted(f"{s}.png" for s in safes)
    for i, safe in enumerate(safes):
        with Image.open(io.BytesIO(zf.read(f"{safe}.png"))) as im:
            assert im.size == (1400 + i, 1100)


def test_archive_render_is_the_same_one_the_run_download_serves(
    client, solved_library,
):
    """The point of the shared `pipeline.render_run_full_res_png`: a picture in
    the archive is byte-for-byte the picture that target's own "Full-res PNG"
    button gives you. Two renders of one picture that disagreed would be a bug
    nobody would notice until they compared prints."""
    safe = _safes(client)[0]
    run_id = _add_run(solved_library, safe, w=900, h=700)

    built = _build(client)
    from_archive = _archive(client, built["job_id"]).read(f"{safe}.png")

    single = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert single.status_code == 200
    assert from_archive == single.content


def test_archive_renders_the_pinned_cover_not_just_the_newest(
    client, solved_library,
):
    """The archive holds the picture the app has been showing, which is the
    pinned cover when there is one — the same precedence as the Library tile,
    the montage and the streaming zip."""
    safe = _safes(client)[0]
    old = _add_run(solved_library, safe, w=800, h=600, basename="old",
                   timestamp_utc="2026-04-01T00:00:00Z")
    _add_run(solved_library, safe, w=1200, h=900, basename="new",
             timestamp_utc="2026-06-01T00:00:00Z")

    # Newest wins with nothing pinned…
    built = _build(client)
    with Image.open(io.BytesIO(_archive(client, built["job_id"]).read(f"{safe}.png"))) as im:
        assert im.size == (1200, 900)

    # …and the pin wins over it once one exists.
    r = client.put(f"/api/targets/{safe}/cover", json={"run_id": old})
    assert r.status_code == 200, r.text
    built = _build(client)
    with Image.open(io.BytesIO(_archive(client, built["job_id"]).read(f"{safe}.png"))) as im:
        assert im.size == (800, 600)


def test_a_run_with_no_master_falls_back_to_its_preview_and_says_so(
    client, solved_library,
):
    """A run whose FITS has been pruned can't be rendered at full size. Dropping
    it from a *backup* would be the worst answer, and slipping the small one in
    silently the second-worst: it goes in, and the archive names it."""
    safes = _safes(client)
    _add_run(solved_library, safes[0], w=1400, h=1100)
    _add_run(solved_library, safes[1], w=1400, h=1100, with_fits=False)

    built = _build(client)
    assert built["job"]["result"]["n_preview_only"] == 1
    assert built["job"]["result"]["n_full_res"] == 1
    zf = _archive(client, built["job_id"])
    assert f"{safes[1]}.png" in zf.namelist()
    with Image.open(io.BytesIO(zf.read(f"{safes[1]}.png"))) as im:
        assert im.size == (64, 48)  # the stored preview, standing in
    note = zf.read("_preview_size.txt").decode()
    assert f"{safes[1]}.png" in note
    assert f"{safes[0]}.png" not in note


def test_one_broken_picture_does_not_sink_the_archive(client, solved_library):
    """Same promise the streaming zip makes: the rest still arrives, and a
    `_skipped.txt` inside says what was missed so it never quietly claims to be
    complete."""
    safes = _safes(client)
    _add_run(solved_library, safes[0], w=900, h=700)
    _add_run(solved_library, safes[1], w=900, h=700)
    # Corrupt one master *after* it is registered: the run still points at a
    # file, so the pick is made and the render is what fails.
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safes[1]))
    finally:
        lib.close()
    (tdir / "master_900x700.fits").write_bytes(b"not a FITS file at all")

    built = _build(client)
    zf = _archive(client, built["job_id"])
    assert f"{safes[0]}.png" in zf.namelist()
    assert built["job"]["result"]["n_pictures"] == 1
    assert f"{safes[1]}.png" in zf.read("_skipped.txt").decode()


def test_moon_still_rides_along_verbatim(client, solved_library, data_root):
    """A finished Moon/Sun still is *already* written at native resolution, so it
    is copied rather than re-rendered — and it must not go missing from an
    archive that calls itself all my pictures."""
    from webapp import video

    _add_run(solved_library, _safes(client)[0], w=900, h=700)
    out = Path(data_root) / "video" / "Lunar_video"
    out.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1920, 1080), (200, 200, 190)).save(out / video.PNG_NAME)
    # The shape `_video_stack_body` leaves behind (mirrors the pictures.zip test).
    (out / "meta.json").write_text(json.dumps({
        "capture_id": "Lunar_video", "label": "Moon", "kind": "moon",
        "source_name": "Lunar_video.mp4", "created_utc": "2026-05-02T21:30:00Z",
        "width": 1920, "height": 1080, "keep_percent": 30.0,
        "n_graded": 100, "n_kept": 30, "n_stacked": 30, "n_align_failed": 0,
        "stride": 1, "aligned": True, "sharpness_best": 1.0,
        "sharpness_kept_median": 0.9, "sharpness_all_median": 0.5,
        "warnings": [],
    }), encoding="utf-8")

    built = _build(client)
    zf = _archive(client, built["job_id"])
    moon = [n for n in zf.namelist() if n.startswith("Moon")]
    assert moon, zf.namelist()
    assert zf.read(moon[0]) == (out / video.PNG_NAME).read_bytes()


def test_building_twice_keeps_one_archive_and_no_part_file(client, solved_library):
    """A NAS with a fixed disk allowance must not accumulate a copy of the season
    per press, and a `.part` left behind would be a half-archive that looks
    finished."""
    from webapp import picturesarchive

    _add_run(solved_library, _safes(client)[0], w=700, h=500)
    first = _build(client)
    second = _build(client)
    assert first["job_id"] != second["job_id"]

    exports = picturesarchive.archive_dir(
        type("S", (), {"data_root": str(solved_library)})())
    assert [p.name for p in sorted(exports.iterdir())] == [
        picturesarchive.ARCHIVE_FILENAME]


def test_the_archive_is_the_only_thing_written(client, solved_library):
    """No new run, no new preview, no export marker — and nothing at all inside
    `incoming/`, which is read-only for the whole app (AGENTS.md §10)."""
    safe = _safes(client)[0]
    _add_run(solved_library, safe, w=700, h=500)

    def _snapshot(root: Path) -> dict[str, int]:
        return {str(p.relative_to(root)): p.stat().st_size
                for p in sorted(root.rglob("*")) if p.is_file()}

    incoming_before = _snapshot(Path(solved_library) / "incoming")
    library_before = _snapshot(Path(solved_library) / "library")
    runs_before = client.get(f"/api/targets/{safe}/stack-runs").json()

    _build(client)

    assert _snapshot(Path(solved_library) / "incoming") == incoming_before
    assert _snapshot(Path(solved_library) / "library") == library_before
    assert client.get(f"/api/targets/{safe}/stack-runs").json() == runs_before


def test_download_endpoint_guards(client, solved_library):
    """404 for a job that isn't one of ours, 409 while it is still building."""
    assert client.get("/api/gallery/pictures-archive/nope").status_code == 404

    _add_run(solved_library, _safes(client)[0], w=700, h=500)
    r = client.post("/api/gallery/pictures-archive")
    job_id = r.json()["job_id"]
    # Whatever state it is in, only a *finished* job hands over a file.
    early = client.get(f"/api/gallery/pictures-archive/{job_id}")
    assert early.status_code in (200, 409)
    _wait_job(client, job_id)
    assert client.get(f"/api/gallery/pictures-archive/{job_id}").status_code == 200

    # A job of another kind is not an archive, however finished it is.
    other = client.post("/api/scan").json()["job_id"]
    _wait_job(client, other)
    assert client.get(f"/api/gallery/pictures-archive/{other}").status_code == 404


def test_no_pictures_at_all_fails_the_job_rather_than_writing_an_empty_zip(
    client, solved_library,
):
    """Nothing finished yet → the job errors with a sentence, instead of handing
    over an archive with nothing in it."""
    r = client.post("/api/gallery/pictures-archive")
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "error"
    assert "no finished pictures" in (job["error"] or "")


def test_storage_names_the_prepared_archive(client, solved_library):
    """A season of pictures at print size is gigabytes sitting outside the
    library, so the page whose whole job is "what is using my disk?" has to be
    able to account for it."""
    assert client.get("/api/storage").json()["exports_bytes"] == 0

    _add_run(solved_library, _safes(client)[0], w=900, h=700)
    _build(client)

    reported = client.get("/api/storage").json()["exports_bytes"]
    from webapp import picturesarchive
    on_disk = picturesarchive.archive_path(
        type("S", (), {"data_root": str(solved_library)})()).stat().st_size
    assert reported == on_disk > 0


def test_deleting_the_prepared_archive_frees_it_and_nothing_else(
    client, solved_library,
):
    """It is a cache: every byte can be made again from pictures that stay put.
    Deleting it must take that file and only that file."""
    safe = _safes(client)[0]
    _add_run(solved_library, safe, w=900, h=700)
    _build(client)

    def _snapshot(root: Path) -> set[str]:
        return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}

    library_before = _snapshot(Path(solved_library) / "library")
    incoming_before = _snapshot(Path(solved_library) / "incoming")

    r = client.delete("/api/gallery/pictures-archive")
    assert r.status_code == 200, r.text
    assert r.json()["removed"] is True
    assert r.json()["freed_bytes"] > 0
    assert client.get("/api/storage").json()["exports_bytes"] == 0
    assert _snapshot(Path(solved_library) / "library") == library_before
    assert _snapshot(Path(solved_library) / "incoming") == incoming_before

    # Idempotent: pressing it again is not an error, it just has nothing to do.
    again = client.delete("/api/gallery/pictures-archive")
    assert again.status_code == 200
    assert again.json() == {"removed": False, "freed_bytes": 0}


def test_a_deleted_archive_is_offered_again_rather_than_404ing_silently(
    client, solved_library,
):
    """The job that built it is still in the list, so its download link outlives
    the file. It has to say the archive is gone, and building again has to work."""
    _add_run(solved_library, _safes(client)[0], w=700, h=500)
    built = _build(client)
    client.delete("/api/gallery/pictures-archive")

    gone = client.get(f"/api/gallery/pictures-archive/{built['job_id']}")
    assert gone.status_code == 404
    assert "build it again" in gone.json()["detail"]

    rebuilt = _build(client)
    assert _archive(client, rebuilt["job_id"]).namelist()


def test_cancelling_leaves_no_archive(client, solved_library):
    """A half-built backup that looked complete would be worse than none: a
    cancelled build removes its part file and reports no path."""
    from webapp import picturesarchive

    safe = _safes(client)[0]
    _add_run(solved_library, safe, w=700, h=500)
    settings = type("S", (), {"data_root": str(solved_library)})()
    picks = picturesarchive.plan_full_size_pictures(
        type("S2", (), {"data_root": str(solved_library),
                        "resolved_library_root": Path(solved_library) / "library"})())
    assert picks

    report = picturesarchive.build_full_size_archive(
        settings, picks, should_stop=lambda: True)
    assert report.cancelled is True
    assert report.path == ""
    assert report.n_pictures == 0
    assert not picturesarchive.archive_path(settings).exists()
    assert not list(picturesarchive.archive_dir(settings).glob("*.part"))
