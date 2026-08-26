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
                      basename="master") -> None:
    """Give ``safe`` a finished picture: a real PNG on disk, registered as a
    stack run so the library stamps ``last_stack_preview`` at that path."""
    from PIL import Image

    lib = Library.open_or_create(root / "library")
    try:
        entry = lib.find_target(safe)
        preview_path = lib.target_dir(entry) / f"{basename}_preview.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), (30, 50, 90)).save(preview_path)
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
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


def test_montage_writes_nothing_to_the_library(client, solved_library):
    """A display-time render, exactly like the recap poster — downloading the
    wall must not add a file, a stack run, or a job to anyone's library."""
    for safe in _safes(client):
        _register_picture(solved_library, safe)
    before = sorted(p.name for p in (solved_library / "library").rglob("*"))

    assert client.get("/api/gallery/montage.jpg").status_code == 200

    after = sorted(p.name for p in (solved_library / "library").rglob("*"))
    assert before == after
