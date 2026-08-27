"""`GET /api/gallery/best.zip` — "Download all my pictures".

One tap that streams every finished target picture as a single archive, so a
season's work can be backed up or dropped into a phone album without visiting
each target in turn. The archive holds exactly what the *best pictures* wall
shows, from the same enumeration.
"""

from __future__ import annotations

import io
import json
import zipfile

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp.routers.gallery import zip_entry_name

# A tiny but genuinely valid PNG, so an archived member is real image bytes.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d763f8cf000001010100185dd06c0000000049454e44ae426082"
)


def _register_preview_run(
    data_root, safe: str, *, basename: str, n_frames: int,
    exposure_s: float | None, noise_sigma: float | None, coverage_max: int,
    body: bytes = PNG, timestamp: str = "2026-05-02T00:00:00Z",
) -> int:
    """Register a finished stack whose preview file exists on disk."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        tdir = lib.target_dir(lib.find_target(safe))
        preview = tdir / f"{basename}.png"
        preview.write_bytes(body)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=timestamp,
                output_basename=basename, fits_path=None, tiff_path=None,
                preview_path=str(preview), n_frames_used=n_frames,
                canvas_h=320, canvas_w=480, coverage_min=1,
                coverage_max=coverage_max,
                options_json=json.dumps({"sigma_clip": True}),
                total_exposure_s=exposure_s, noise_sigma=noise_sigma,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _two_finished_targets(client, data_root):
    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    _register_preview_run(data_root, a, basename="deep", n_frames=500,
                          exposure_s=15000, noise_sigma=0.01, coverage_max=500)
    _register_preview_run(data_root, b, basename="shallow", n_frames=20,
                          exposure_s=600, noise_sigma=0.09, coverage_max=20)
    names = {t["safe_name"]: t["name"] for t in targets}
    return names[a], names[b]


def _zip_of(response) -> zipfile.ZipFile:
    assert response.status_code == 200, response.status_code
    assert response.headers["content-type"] == "application/zip"
    assert "my-astrostack-pictures.zip" in response.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_download_all_streams_every_targets_picture(client, solved_library):
    """The whole point: one request, one archive, one picture per target — named
    after the target, and byte-for-byte the picture the wall showed."""
    name_a, name_b = _two_finished_targets(client, solved_library)

    zf = _zip_of(client.get("/api/gallery/best.zip"))
    assert zf.testzip() is None  # a structurally valid archive
    members = sorted(zf.namelist())
    assert members == sorted([f"{name_a}.png", f"{name_b}.png"]), members
    for member in members:
        assert zf.read(member) == PNG
    # Read-only: nothing was written into the library alongside the previews.
    assert not list((solved_library / "library").rglob("*.zip"))


def test_download_all_self_hides_exactly_like_the_wall(client, solved_library):
    """A library too young for the wall gets a 404 with a plain-language reason,
    rather than an archive of one picture."""
    r = client.get("/api/gallery/best.zip")
    assert r.status_code == 404
    assert "two targets" in r.json()["detail"]

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_preview_run(solved_library, safe, basename="only", n_frames=50,
                          exposure_s=1500, noise_sigma=0.05, coverage_max=50)
    assert client.get("/api/gallery/best.zip").status_code == 404


def test_download_all_matches_the_wall_and_honours_its_limit(client, solved_library):
    """One definition of "this target's picture": the archive's members are the
    wall's items, in the wall's order, capped by the same `limit`."""
    _two_finished_targets(client, solved_library)

    items = client.get("/api/gallery/best").json()["items"]
    zf = _zip_of(client.get("/api/gallery/best.zip"))
    assert zf.namelist() == [f"{it['target_name']}.png" for it in items]

    zf = _zip_of(client.get("/api/gallery/best.zip?limit=1"))
    assert zf.namelist() == [f"{items[0]['target_name']}.png"]


def test_one_unreadable_picture_is_skipped_not_fatal(client, solved_library,
                                                     monkeypatch):
    """A preview that vanished between the enumeration and the read must not sink
    the whole archive — the rest still download, and the archive says what went
    missing."""
    name_a, _ = _two_finished_targets(client, solved_library)

    real_open = open

    def flaky_open(path, *args, **kwargs):
        if str(path).endswith("shallow.png"):
            raise OSError("gone")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", flaky_open)
    zf = _zip_of(client.get("/api/gallery/best.zip"))
    monkeypatch.undo()

    assert zf.testzip() is None
    assert f"{name_a}.png" in zf.namelist()
    assert "_skipped.txt" in zf.namelist()
    note = zf.read("_skipped.txt").decode()
    assert "couldn't be read" in note


def test_a_big_picture_survives_the_chunked_stream(client, solved_library):
    """The archive is streamed a chunk at a time rather than built in memory, so
    a member larger than one read buffer has to come back intact."""
    targets = client.get("/api/targets").json()
    a, b = targets[0]["safe_name"], targets[1]["safe_name"]
    big = PNG + bytes(range(256)) * 4096  # ~1 MB, several read chunks
    _register_preview_run(solved_library, a, basename="big", n_frames=500,
                          exposure_s=15000, noise_sigma=0.01, coverage_max=500,
                          body=big)
    _register_preview_run(solved_library, b, basename="small", n_frames=20,
                          exposure_s=600, noise_sigma=0.09, coverage_max=20)

    zf = _zip_of(client.get("/api/gallery/best.zip"))
    assert zf.testzip() is None
    assert zf.read(zf.namelist()[0]) == big


# --------------------------------------------------------------------------
# The member-naming rule, on its own.
# --------------------------------------------------------------------------

def test_zip_entry_name_is_safe_friendly_and_unique():
    taken: set[str] = set()
    # Friendly: named for the target, spaces and catalogue punctuation kept.
    assert zip_entry_name("M 42", ".png", taken) == "M 42.png"
    # Safe: a separator or traversal segment can never escape the unzip folder.
    assert zip_entry_name("M 42 / Orion", ".png", taken) == "M 42 _ Orion.png"
    assert "/" not in zip_entry_name("../../etc/passwd", ".png", taken)
    assert "\\" not in zip_entry_name("C:\\stuff", ".png", taken)
    # A name that sanitises to nothing still gets a filename.
    assert zip_entry_name("...", ".png", taken) == "picture.png"
    assert zip_entry_name("", ".png", taken) == "picture (2).png"
    # Unique: two targets that sanitise alike don't overwrite each other.
    fresh: set[str] = set()
    assert zip_entry_name("M 42?", ".png", fresh) == "M 42_.png"
    assert zip_entry_name("M 42*", ".png", fresh) == "M 42_ (2).png"
    # ...case-insensitively, since Windows and macOS unzip onto such filesystems.
    assert zip_entry_name("m 42_", ".png", fresh) == "m 42_ (3).png"
