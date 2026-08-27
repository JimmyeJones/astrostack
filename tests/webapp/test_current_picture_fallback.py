"""One answer to "which picture is this target's", shared by every surface.

Three steps decide it: the run the owner pinned as the cover, then the library's
stamped newest-stack preview, then the newest run that still has a preview on
disk. The *pinned* half has always been shared (``targets._cover_preview_path``);
the third step was not — only ``/api/gallery/best`` walked the run list, while
the wall, the "download all" archive and the target thumbnail stopped at the
stamped path.

That gap is reachable: deleting a target's newest run removes its preview file
and leaves the stamp behind. ``best`` then quietly stepped back to the previous
run and still showed the target, while the other three saw one dead path and
dropped it — so the same library read as N pictures on one screen and N−1 on
another, with nothing on either to explain the difference.

These tests pin the agreement rather than any one endpoint: the same target,
with the same picture, everywhere.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import StackRunRow

_OLD = (200, 40, 40)     # the picture that survives on disk
_GONE = (40, 200, 40)    # the newest run, whose file has been deleted


def _register_picture(root, safe, *, w=200, h=150, basename="master",
                      colour=(30, 50, 90),
                      timestamp_utc="2026-05-02T00:00:00Z") -> int:
    """Give ``safe`` a finished picture on disk, registered as a stack run so the
    library stamps ``last_stack_preview`` at that path. Returns the run id."""
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
                options_json=json.dumps({}), total_exposure_s=3600.0,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()
    return run_id


def _safes(client) -> list[str]:
    return [t["safe_name"] for t in client.get("/api/targets").json()]


def _shows_colour(jpeg_bytes, colour, *, tol=24) -> bool:
    """Whether the rendered wall contains a real tile of ``colour``."""
    import numpy as np
    from PIL import Image

    arr = np.asarray(
        Image.open(io.BytesIO(jpeg_bytes)).convert("RGB"), dtype=np.int16)
    close = np.all(np.abs(arr - np.array(colour, dtype=np.int16)) <= tol, axis=2)
    return int(close.sum()) > 500


def _target_dir(root, safe) -> Path:
    lib = Library.open_or_create(root / "library")
    try:
        return lib.target_dir(lib.find_target(safe))
    finally:
        lib.close()


def _orphan_the_stamped_preview(root, safes) -> Path:
    """Set up the reachable case: ``safes[0]`` has an older picture that is still
    on disk and a newer one whose file has been deleted (as deleting that run
    does), with the library still stamped at the dead path. Returns the path of
    the picture that survives.

    Every other target gets one ordinary picture, so the wall has enough tiles
    to render at all.
    """
    _register_picture(root, safes[0], basename="kept", colour=_OLD,
                      timestamp_utc="2026-05-01T00:00:00Z")
    _register_picture(root, safes[0], basename="deleted", colour=_GONE,
                      timestamp_utc="2026-06-01T00:00:00Z")
    for safe in safes[1:]:
        _register_picture(root, safe)

    lib = Library.open_or_create(root / "library")
    try:
        entry = lib.find_target(safes[0])
        stamped = Path(entry.last_stack_preview)
        assert stamped.name.startswith("deleted"), "the newest run must be stamped"
    finally:
        lib.close()
    stamped.unlink()
    return _target_dir(root, safes[0]) / "kept_preview.png"


def test_every_surface_shows_the_same_picture_when_the_stamped_one_is_gone(
    client, solved_library,
):
    """The gap this closes. ``/api/gallery/best`` always stepped back to the
    surviving run; the wall, the archive and the thumbnail dropped the target or
    served a 404. All four now answer with the one picture that is really there.
    """
    safes = _safes(client)
    assert len(safes) >= 2
    kept = _orphan_the_stamped_preview(solved_library, safes)
    kept_bytes = kept.read_bytes()

    # The reference answer, unchanged: best already walked the run list.
    best = client.get("/api/gallery/best").json()["items"]
    assert safes[0] in [i["safe"] for i in best]

    # The archive holds it, and holds the *surviving* picture's bytes.
    r = client.get("/api/gallery/pictures.zip")
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert f"{safes[0]}.png" in zf.namelist()
    assert zf.read(f"{safes[0]}.png") == kept_bytes
    # …and the two screens now agree on how many pictures the library has.
    assert len(zf.namelist()) == len(best)

    # The wall shows it, and shows the surviving picture rather than nothing.
    wall = client.get("/api/gallery/montage.jpg")
    assert wall.status_code == 200, wall.text
    assert _shows_colour(wall.content, _OLD)
    assert not _shows_colour(wall.content, _GONE)

    # …and so does the target's own thumbnail, instead of a broken image.
    thumb = client.get(f"/api/targets/{safes[0]}/thumbnail")
    assert thumb.status_code == 200
    assert thumb.content == kept_bytes


def test_a_pinned_cover_still_wins_over_a_surviving_older_run(
    client, solved_library,
):
    """The new third step must not reorder the first two: what the owner pinned
    is still the target's picture, even when the stamped path is dead."""
    safes = _safes(client)
    cover_id = _register_picture(
        solved_library, safes[0], basename="chosen", colour=(9, 9, 200),
        timestamp_utc="2026-04-01T00:00:00Z")
    _orphan_the_stamped_preview(solved_library, safes)
    assert client.put(f"/api/targets/{safes[0]}/cover",
                      json={"run_id": cover_id}).status_code == 200

    chosen = (_target_dir(solved_library, safes[0]) / "chosen_preview.png"
              ).read_bytes()
    zf = zipfile.ZipFile(io.BytesIO(client.get("/api/gallery/pictures.zip").content))
    assert zf.read(f"{safes[0]}.png") == chosen
    assert client.get(f"/api/targets/{safes[0]}/thumbnail").content == chosen


def test_a_target_with_no_surviving_picture_at_all_still_drops_out(
    client, solved_library,
):
    """The fallback finds a picture; it must not invent one. With every run's
    preview gone the target has nothing to show, and each surface must say so
    exactly as it did before."""
    safes = _safes(client)
    _register_picture(solved_library, safes[0], basename="kept", colour=_OLD,
                      timestamp_utc="2026-05-01T00:00:00Z")
    _register_picture(solved_library, safes[0], basename="deleted", colour=_GONE,
                      timestamp_utc="2026-06-01T00:00:00Z")
    for safe in safes[1:]:
        _register_picture(solved_library, safe)
    for name in ("kept_preview.png", "deleted_preview.png"):
        (_target_dir(solved_library, safes[0]) / name).unlink()

    zf = zipfile.ZipFile(io.BytesIO(client.get("/api/gallery/pictures.zip").content))
    assert f"{safes[0]}.png" not in zf.namelist()
    assert client.get(f"/api/targets/{safes[0]}/thumbnail").status_code == 404
    best = client.get("/api/gallery/best").json()["items"]
    assert safes[0] not in [i["safe"] for i in best]


def test_a_healthy_library_never_opens_a_project_for_the_fallback(
    client, solved_library, monkeypatch,
):
    """What makes the third step affordable: it only runs when the stamped path
    is missing. On a library where every stamp is good, the archive must resolve
    every picture without opening a single project — the cost the montage's own
    comment budgets for, and the reason this is kept out of the list endpoints.
    """
    for safe in _safes(client):
        _register_picture(solved_library, safe)

    opens: list[str] = []
    real = Library.open_target

    def counted(self, safe_name, *args, **kwargs):
        opens.append(safe_name)
        return real(self, safe_name, *args, **kwargs)

    monkeypatch.setattr(Library, "open_target", counted)
    r = client.get("/api/gallery/pictures.zip")
    assert r.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert opens == []
