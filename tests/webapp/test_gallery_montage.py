"""GET /api/gallery/montage.jpg — "My deep-sky wall".

The gallery can only ever show one picture at a time, so nothing in the app says
*"look at everything I've captured"*. This renders that, on demand, from the
previews the library already keeps.
"""

from __future__ import annotations

import io
import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_picture(root, safe, *, w=200, h=150, exposure_s=3600.0,
                      basename="master", colour=(30, 50, 90),
                      timestamp_utc="2026-05-02T00:00:00Z") -> int:
    """Give ``safe`` a finished picture: a real PNG on disk, registered as a
    stack run so the library stamps ``last_stack_preview`` at that path.

    ``colour`` fills the preview so a test can tell two of a target's pictures
    apart in the rendered wall; the new run's id is returned so one can be
    pinned as the target's cover."""
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
                options_json=json.dumps({}), total_exposure_s=exposure_s,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()
    return run_id


def _shows_colour(jpeg_bytes, colour, *, tol=24) -> bool:
    """Whether the rendered wall contains a meaningful patch of ``colour``.

    The tiles are flat fills, so JPEG's chroma loss stays well inside ``tol``;
    a handful of matching pixels would be ringing at an edge, so a real tile is
    required to be at least a few hundred of them."""
    import numpy as np
    from PIL import Image

    arr = np.asarray(Image.open(io.BytesIO(jpeg_bytes)).convert("RGB"), dtype=np.int16)
    close = np.all(np.abs(arr - np.array(colour, dtype=np.int16)) <= tol, axis=2)
    return int(close.sum()) > 500


def _safes(client) -> list[str]:
    return [t["safe_name"] for t in client.get("/api/targets").json()]


def test_montage_renders_a_jpeg_of_every_finished_target(client, solved_library):
    from PIL import Image

    for safe in _safes(client):
        _register_picture(solved_library, safe)

    r = client.get("/api/gallery/montage.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert "my-deep-sky-wall.jpg" in r.headers["content-disposition"]
    img = Image.open(io.BytesIO(r.content))
    # Two pictures → one row of two, plus the title strip above them.
    assert img.size[0] > img.size[1]
    assert img.size[0] >= 800


def test_one_picture_is_not_a_wall(client, solved_library):
    """A library with a single finished target must not be offered a "montage"
    that is just the picture it already shows — the endpoint 404s so the button
    self-hides."""
    _register_picture(solved_library, _safes(client)[0])
    r = client.get("/api/gallery/montage.jpg")
    assert r.status_code == 404
    assert "two targets" in r.json()["detail"]


def test_montage_self_hides_on_a_library_with_no_pictures(client, solved_library):
    assert client.get("/api/gallery/montage.jpg").status_code == 404


def test_a_deleted_preview_is_skipped_not_a_500(client, solved_library):
    """The library row survives the file, so a preview deleted since the last
    stack must simply drop off the wall — and with only one left, the wall
    self-hides rather than half-rendering."""
    from pathlib import Path

    safes = _safes(client)
    for safe in safes:
        _register_picture(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        entry = lib.find_target(safes[0])
        Path(entry.last_stack_preview).unlink()
    finally:
        lib.close()

    r = client.get("/api/gallery/montage.jpg")
    assert r.status_code == 404  # one readable picture left — not a wall


def test_limit_is_clamped_to_a_sane_range(client, solved_library):
    """The cap keeps the wall enjoyable at social sizes; a caller can't ask for
    a one-picture wall or a contact sheet of hundreds."""
    for safe in _safes(client):
        _register_picture(solved_library, safe)
    assert client.get("/api/gallery/montage.jpg?limit=1").status_code == 200
    assert client.get("/api/gallery/montage.jpg?limit=9999").status_code == 200


_COVER = (200, 40, 40)     # the picture its owner pinned as "the good one"
_NEWEST = (40, 200, 40)    # a later, scrappier restack


def test_the_wall_shows_the_picture_its_owner_pinned_not_the_newest_stack(
        client, solved_library):
    """"Set as cover" is the user saying, in as many words, *which picture of
    this target is the good one*. A target whose newest run is a quick restack
    put that on the wall instead — the one thing the wall exists to show."""
    safes = _safes(client)
    cover_id = _register_picture(
        solved_library, safes[0], basename="good", colour=_COVER,
        timestamp_utc="2026-05-01T00:00:00Z")
    _register_picture(
        solved_library, safes[0], basename="restack", colour=_NEWEST,
        timestamp_utc="2026-06-01T00:00:00Z")
    for safe in safes[1:]:
        _register_picture(solved_library, safe)

    # Before pinning, the newest stack represents the target — that's the old
    # behaviour, and it must stay the fallback.
    r = client.get("/api/gallery/montage.jpg")
    assert r.status_code == 200
    assert _shows_colour(r.content, _NEWEST)
    assert not _shows_colour(r.content, _COVER)

    assert client.put(f"/api/targets/{safes[0]}/cover",
                      json={"run_id": cover_id}).status_code == 200

    r = client.get("/api/gallery/montage.jpg")
    assert r.status_code == 200
    assert _shows_colour(r.content, _COVER)
    assert not _shows_colour(r.content, _NEWEST)


def test_a_pinned_cover_whose_file_is_gone_falls_back_to_the_newest_picture(
        client, solved_library):
    """The cover row survives the file. A pruned or deleted cover must degrade
    to the newest stack rather than dropping the target off the wall."""
    from pathlib import Path

    safes = _safes(client)
    cover_id = _register_picture(
        solved_library, safes[0], basename="good", colour=_COVER,
        timestamp_utc="2026-05-01T00:00:00Z")
    _register_picture(
        solved_library, safes[0], basename="restack", colour=_NEWEST,
        timestamp_utc="2026-06-01T00:00:00Z")
    for safe in safes[1:]:
        _register_picture(solved_library, safe)
    assert client.put(f"/api/targets/{safes[0]}/cover",
                      json={"run_id": cover_id}).status_code == 200

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safes[0])
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == cover_id)
        finally:
            proj.close()
    finally:
        lib.close()
    Path(run.preview_path).unlink()

    r = client.get("/api/gallery/montage.jpg")
    assert r.status_code == 200
    assert _shows_colour(r.content, _NEWEST)


def test_montage_writes_nothing_to_the_library(client, solved_library):
    """A display-time render, exactly like the recap poster — downloading the
    wall must not add a file, a stack run, or a job to anyone's library."""
    for safe in _safes(client):
        _register_picture(solved_library, safe)
    before = sorted(p.name for p in (solved_library / "library").rglob("*"))

    assert client.get("/api/gallery/montage.jpg").status_code == 200

    after = sorted(p.name for p in (solved_library / "library").rglob("*"))
    assert before == after
