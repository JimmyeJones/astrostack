"""GET /api/gallery/pictures.zip — "Download all my pictures".

Bulk *upload* has been there since v0.229.0; the symmetric bulk *download* was
the gap. Someone with a season of targets who wanted to back the results up, or
put them all in a phone album, had to open each target and download one at a
time — so the pictures stayed in the app. This is the one tap that gets them
out, and these tests pin the three things that make it trustworthy: it holds
*every* target's current picture, byte-for-byte; the picture it picks is the one
the app has been showing; and one unreadable file can't sink the archive.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_picture(root, safe, *, w=32, h=24, basename="master",
                      colour=(30, 50, 90),
                      timestamp_utc="2026-05-02T00:00:00Z") -> int:
    """Give ``safe`` a finished picture on disk, registered as a stack run so the
    library stamps ``last_stack_preview`` at that path. Returns the run id, so a
    test can pin one as the target's cover."""
    from PIL import Image

    lib = Library.open_or_create(root / "library")
    try:
        entry = lib.find_target(safe)
        preview_path = lib.target_dir(entry) / f"{basename}_preview.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), colour).save(preview_path)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=timestamp_utc,
                output_basename=basename, fits_path=None, tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=3,
                options_json=json.dumps({}), total_exposure_s=600.0,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()
    return run_id


def _safes(client) -> list[str]:
    return [t["safe_name"] for t in client.get("/api/targets").json()]


def _open_zip(response) -> zipfile.ZipFile:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "my-astrostack-pictures.zip" in response.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_zip_holds_every_targets_picture_byte_for_byte(client, solved_library):
    """One entry per target, named for the target, and the bytes are the file the
    gallery already serves — nothing re-rendered."""
    safes = _safes(client)
    assert len(safes) >= 2
    for i, safe in enumerate(safes):
        _register_picture(solved_library, safe, colour=(10 * i, 20, 30))

    zf = _open_zip(client.get("/api/gallery/pictures.zip"))
    assert sorted(zf.namelist()) == sorted(f"{s}.png" for s in safes)

    # Byte-for-byte against what's on disk: this is a copy, not a re-encode.
    lib = Library.open_or_create(solved_library / "library")
    try:
        for safe in safes:
            entry = lib.find_target(safe)
            on_disk = (lib.target_dir(entry) / "master_preview.png").read_bytes()
            assert zf.read(f"{safe}.png") == on_disk
    finally:
        lib.close()


def test_zip_is_a_valid_streamed_archive(client, solved_library):
    """The archive is built without ever seeking, so the one thing that could
    silently break is the central directory. Make ``zipfile`` verify it."""
    for safe in _safes(client):
        _register_picture(solved_library, safe)

    zf = _open_zip(client.get("/api/gallery/pictures.zip"))
    assert zf.testzip() is None  # every member's CRC checks out
    assert zf.namelist()


def test_zip_uses_the_pinned_cover_not_the_newest_stack(client, solved_library):
    """"Set as cover" is the user saying which picture of a target *is* the
    picture. The archive must hold that one, exactly as the Library tile, the
    best-pictures wall and the montage do — not silently the newest restack."""
    safes = _safes(client)
    for safe in safes:
        _register_picture(solved_library, safe)
    cover_id = _register_picture(
        solved_library, safes[0], basename="chosen", colour=(200, 40, 40))
    # …and a *newer* stack after it, which must lose to the pin.
    _register_picture(solved_library, safes[0], basename="newest",
                      colour=(9, 9, 9), timestamp_utc="2026-06-09T00:00:00Z")
    assert client.put(f"/api/targets/{safes[0]}/cover",
                      json={"run_id": cover_id}).status_code == 200

    zf = _open_zip(client.get("/api/gallery/pictures.zip"))
    lib = Library.open_or_create(solved_library / "library")
    try:
        entry = lib.find_target(safes[0])
        chosen = (lib.target_dir(entry) / "chosen_preview.png").read_bytes()
    finally:
        lib.close()
    assert zf.read(f"{safes[0]}.png") == chosen


def test_a_deleted_picture_just_drops_that_target(client, solved_library):
    """A target whose preview file is gone is simply not in the archive — the
    same "no finished picture" it already reads as everywhere else — and the
    other targets still arrive."""
    safes = _safes(client)
    for safe in safes:
        _register_picture(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        (lib.target_dir(lib.find_target(safes[0])) / "master_preview.png").unlink()
    finally:
        lib.close()

    zf = _open_zip(client.get("/api/gallery/pictures.zip"))
    assert f"{safes[0]}.png" not in zf.namelist()
    for safe in safes[1:]:
        assert f"{safe}.png" in zf.namelist()


def test_a_file_lost_mid_stream_is_named_not_silently_dropped(
        client, solved_library, monkeypatch):
    """The race the pre-check can't cover: a picture that vanishes *between* the
    enumeration and its turn in the stream. The rest of the archive must still
    arrive intact, and ``_skipped.txt`` must name what was missed — an archive
    that quietly came up short would look like a complete backup."""
    from webapp.routers import gallery

    safes = _safes(client)
    for safe in safes:
        _register_picture(solved_library, safe)

    real = gallery._library_pictures

    def _with_a_ghost(request):
        picks = real(request)
        picks.insert(0, ("ghost.png", solved_library / "library" / "not-here.png"))
        return picks

    monkeypatch.setattr(gallery, "_library_pictures", _with_a_ghost)

    zf = _open_zip(client.get("/api/gallery/pictures.zip"))
    assert zf.testzip() is None
    for safe in safes:
        assert f"{safe}.png" in zf.namelist()
    assert "_skipped.txt" in zf.namelist()
    assert "ghost.png" in zf.read("_skipped.txt").decode()


def test_no_finished_pictures_self_hides_with_404(client, built_library):
    """A library with nothing finished gets a clean 404, so the button can hide
    rather than handing someone an empty zip."""
    r = client.get("/api/gallery/pictures.zip")
    assert r.status_code == 404
    assert "finished pictures" in r.json()["detail"]


def test_download_never_writes_into_the_library(client, solved_library):
    """Read-only by contract: streaming the archive must not create, move or
    delete a single file (§10 — and the montage's same promise)."""
    for safe in _safes(client):
        _register_picture(solved_library, safe)

    before = sorted(str(p) for p in (solved_library / "library").rglob("*"))
    assert client.get("/api/gallery/pictures.zip").status_code == 200
    after = sorted(str(p) for p in (solved_library / "library").rglob("*"))
    assert before == after


# --- the two promises the archive makes that nothing above pins ---------------

def test_a_big_picture_is_copied_a_chunk_at_a_time_not_held_whole(
        client, solved_library, monkeypatch):
    """"All" is honest because memory is bounded — so pin the thing that bounds it.

    Every test above checks the *finished* archive, which a version that built
    the whole zip in memory and handed it over in one go would pass identically.
    The guarantee is the drain-after-every-chunk loop, and it only shows on a
    picture bigger than one chunk: a deep-sky preview is megabytes and a library
    is many of them, so a refactor that quietly lost this would only be
    discovered on a real library. Watching the buffer's own high-water mark tests
    the claim directly rather than by proxy.
    """
    import numpy as np
    from PIL import Image

    from webapp.routers import gallery

    safes = _safes(client)
    for safe in safes:
        _register_picture(solved_library, safe)
    # Random noise, so PNG can't compress it away and the file really is several
    # chunks long. Replaces one target's picture in place, path unchanged.
    lib = Library.open_or_create(solved_library / "library")
    try:
        big = Path(lib.find_target(safes[0]).last_stack_preview)
    finally:
        lib.close()
    rng = np.random.default_rng(7)
    Image.fromarray(rng.integers(0, 256, (1200, 1200, 3), dtype=np.uint8)).save(big)
    assert big.stat().st_size > 3 * gallery._ZIP_CHUNK, "the picture must span chunks"

    peak = 0
    real_write = gallery._ZipStreamBuffer.write

    def watched_write(self, b):
        nonlocal peak
        n = real_write(self, b)
        peak = max(peak, len(self._buf))
        return n

    monkeypatch.setattr(gallery._ZipStreamBuffer, "write", watched_write)
    body = client.get("/api/gallery/pictures.zip").content
    monkeypatch.undo()

    # The buffer never held the big picture, let alone the whole archive.
    assert peak <= 2 * gallery._ZIP_CHUNK
    assert peak < big.stat().st_size
    assert len(body) > big.stat().st_size  # it really did all arrive
    zf = zipfile.ZipFile(io.BytesIO(body))
    assert zf.testzip() is None
    assert zf.read(f"{safes[0]}.png") == big.read_bytes()


def test_downloading_writes_nothing_anywhere_in_the_data_root(client, solved_library):
    """The read-only promise this makes is about ``incoming/`` above all (§10).

    The sibling test above snapshots ``library/`` only, so a write into
    ``incoming/`` — the one directory in the app that has no backup and no second
    copy — would slip straight past it. This walks the *whole* data root and
    compares size and mtime as well as the file list, so a rewrite in place is
    caught alongside a create or a delete.
    """
    for safe in _safes(client):
        _register_picture(solved_library, safe)
    incoming = Path(solved_library) / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "a-precious-sub.fit").write_bytes(b"the only copy there is")

    def snapshot() -> dict[str, tuple[int, float]]:
        return {
            str(p.relative_to(solved_library)): (p.stat().st_size, p.stat().st_mtime)
            for p in sorted(Path(solved_library).rglob("*")) if p.is_file()
        }

    before = snapshot()
    assert _open_zip(client.get("/api/gallery/pictures.zip")).testzip() is None
    assert snapshot() == before


def _register_still(root: Path, capture_id: str, *, label: str, kind: str = "moon",
                    created_utc: str = "2026-05-02T21:30:00Z",
                    colour=(200, 200, 180)) -> Path:
    """Write a finished Moon/Sun still into the video results store, the same
    shape ``_video_stack_body`` leaves behind. Returns the PNG's path."""
    from PIL import Image

    out = root / "video" / capture_id
    out.mkdir(parents=True, exist_ok=True)
    png = out / "stack.png"
    Image.new("RGB", (40, 30), colour).save(png)
    (out / "meta.json").write_text(json.dumps({
        "capture_id": capture_id, "label": label, "kind": kind,
        "source_name": f"{capture_id}.mp4", "created_utc": created_utc,
        "width": 40, "height": 30, "keep_percent": 30.0,
        "n_graded": 100, "n_kept": 30, "n_stacked": 30, "n_align_failed": 0,
        "stride": 1, "aligned": True, "sharpness_best": 1.0,
        "sharpness_kept_median": 0.9, "sharpness_all_median": 0.5,
        "warnings": [],
    }), encoding="utf-8")
    return png


def test_zip_includes_finished_moon_and_sun_stills(client, solved_library):
    """A lunar/solar still is not a library target — it lives in its own results
    store with no project DB — so walking ``list_targets()`` missed every one of
    them and the archive quietly left out what is very often a beginner's *first*
    good picture.

    Regression: the button says "all my pictures" and the Gallery shows the
    stills, but the zip held deep-sky targets only.
    """
    safes = _safes(client)
    for safe in safes:
        _register_picture(solved_library, safe)
    moon = _register_still(solved_library, "Lunar_video", label="Moon")
    sun = _register_still(solved_library, "Solar_video", label="Sun", kind="sun",
                          created_utc="2026-06-11T10:00:00Z")

    zf = _open_zip(client.get("/api/gallery/pictures.zip"))
    names = zf.namelist()
    # Named for the object and the night it was caught, so a folder of them
    # reads as pictures rather than capture ids.
    assert "Moon_2026-05-02.png" in names
    assert "Sun_2026-06-11.png" in names
    # …alongside, not instead of, the deep-sky targets.
    for safe in safes:
        assert f"{safe}.png" in names
    # Copied verbatim — the still is never re-rendered for the archive.
    assert zf.read("Moon_2026-05-02.png") == moon.read_bytes()
    assert zf.read("Sun_2026-06-11.png") == sun.read_bytes()


def test_a_still_whose_name_collides_with_a_target_gets_its_own_entry(
        client, solved_library):
    """Two sources, one namespace: a still must never overwrite a target's entry
    (or another still's). The ``-2`` suffix the target side already used now spans
    both."""
    safes = _safes(client)
    for safe in safes:
        _register_picture(solved_library, safe)
    # A still whose sanitised name is exactly a target's entry name.
    _register_still(solved_library, "clash_video", label=safes[0],
                    created_utc="")

    zf = _open_zip(client.get("/api/gallery/pictures.zip"))
    names = zf.namelist()
    assert len(names) == len(set(names)), "an entry was silently overwritten"
    assert f"{safes[0]}.png" in names
    assert f"{safes[0]}-2.png" in names


def test_a_library_of_only_stills_still_downloads(client, data_root):
    """Someone whose only pictures so far are Moon stills — a very common Seestar
    first week — gets an archive instead of the "no finished pictures" 404."""
    _register_still(data_root, "Lunar_video", label="Moon")

    zf = _open_zip(client.get("/api/gallery/pictures.zip"))
    assert zf.namelist() == ["Moon_2026-05-02.png"]


def test_library_summary_counts_finished_stills(client, solved_library):
    """The count the "Download all N pictures" button shows has to know about
    stills, or it promises fewer files than the archive holds."""
    assert client.get("/api/library/summary").json()["n_finished_stills"] == 0
    _register_still(solved_library, "Lunar_video", label="Moon")
    _register_still(solved_library, "Solar_video", label="Sun", kind="sun")
    assert client.get("/api/library/summary").json()["n_finished_stills"] == 2


def test_unique_entry_name_reserves_generated_names_not_just_bases():
    """A generated ``-N`` name must itself be reserved, or a later real stem that
    equals it collides and silently overwrites it in the archive.

    Regression for the Scout 2026-09-02 finding: ``used`` recorded only the base
    name, so a stem that happened to equal an earlier generated name was emitted
    unchanged — ``["pic","pic","pic-2"]`` produced ``pic-2.png`` twice, and
    ``zipfile`` accepts the duplicate while every unzip tool overwrites, dropping
    one picture from a "download all" backup.
    """
    from webapp.routers.gallery import _unique_entry_name

    used: dict[str, int] = {}
    got = [_unique_entry_name(stem, ".png", used)
           for stem in ("pic", "pic", "pic-2")]
    assert got == ["pic.png", "pic-2.png", "pic-2-2.png"]
    assert len(got) == len(set(got)), "a generated name was reused"

    # Plain repeats are unchanged: pic, pic-2, pic-3 (no regression).
    used = {}
    plain = [_unique_entry_name("frame", ".jpg", used) for _ in range(3)]
    assert plain == ["frame.jpg", "frame-2.jpg", "frame-3.jpg"]

    # Still de-duplicated case-insensitively (a Mac/Windows unzip safety).
    used = {}
    ci = [_unique_entry_name(s, ".png", used) for s in ("Pic", "pic")]
    assert len({n.lower() for n in ci}) == 2, "case-only variants collided"
