"""GET /api/recap and /api/recap.jpg — the shareable "your sky, so far" recap."""

from __future__ import annotations

import io
import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def test_recap_self_hides_on_an_empty_library(client):
    """Nothing captured yet → the card hides rather than offering a blank
    poster, and the caption is empty instead of a string of zeros."""
    b = client.get("/api/recap").json()
    assert b["has_anything"] is False
    assert b["caption"] == ""
    assert b["stats"] == []
    assert b["n_targets"] == 0 and b["n_subs_kept"] == 0


def test_recap_reports_the_library_and_a_copyable_caption(client, solved_library):
    b = client.get("/api/recap").json()
    assert b["has_anything"] is True
    # The fixture ingests two targets with accepted light.
    assert b["n_targets"] == 2
    assert b["n_subs_kept"] > 0
    assert b["total_integration_s"] > 0.0
    assert b["top_target_name"]
    # The caption is the copy-paste blurb, not a dump of raw fields.
    assert "of light" in b["caption"]
    assert "biggest project" in b["caption"]
    # Stats are (value, label) pairs ready to render.
    labels = [s["label"] for s in b["stats"]]
    assert "of light collected" in labels
    assert all(s["value"] for s in b["stats"])


def test_recap_window_is_clamped_to_a_sane_range(client, solved_library):
    assert client.get("/api/recap?months=0").json()["window_months"] == 1
    assert client.get("/api/recap?months=999").json()["window_months"] == 24


def test_recap_poster_renders_a_square_jpeg(client, solved_library):
    from PIL import Image

    r = client.get("/api/recap.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert "my-sky-so-far.jpg" in r.headers["content-disposition"]
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.size[0] == img.size[1]
        assert img.size[0] >= 512


def test_recap_poster_renders_on_an_empty_library_rather_than_erroring(client):
    """The endpoint is reachable before anything is captured (a bookmark, a
    direct link) — it must produce a plain poster, never a 500."""
    from PIL import Image

    r = client.get("/api/recap.jpg")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.size[0] == img.size[1]


def _register_preview(root, safe, image_bytes: bytes | None = None):
    """Register a stack run whose preview is a real readable PNG on disk, so the
    poster has a hero backdrop to composite."""
    from PIL import Image

    lib = Library.open_or_create(root / "library")
    try:
        entry = lib.find_target(safe)
        target_dir = lib.target_dir(entry)
        preview_path = target_dir / "master_preview.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        if image_bytes is None:
            buf = io.BytesIO()
            Image.new("RGB", (64, 32), (255, 255, 255)).save(buf, format="PNG")
            image_bytes = buf.getvalue()
        preview_path.write_bytes(image_bytes)
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
                options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()
    return preview_path


def test_recap_poster_uses_a_finished_picture_as_its_backdrop(client, solved_library):
    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_preview(solved_library, safe)

    r = client.get("/api/recap.jpg")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as img:
        # A white hero, veiled: clearly lighter than the plain deep-space
        # background but not so bright that the poster text disappears.
        corner = img.convert("RGB").getpixel((2, img.size[1] - 2))
    assert all(60 < c < 210 for c in corner), corner


def test_recap_poster_survives_an_unreadable_preview(client, solved_library):
    """A deleted or corrupt preview must fall back to the plain backdrop, not
    500 the download — previews are regenerated artifacts, not user data."""
    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_preview(solved_library, safe, image_bytes=b"not really a png")

    r = client.get("/api/recap.jpg")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.size[0] == img.size[1]


def test_recap_names_the_other_targets_you_shot(client, solved_library):
    """The recap says *what* you pointed at, not only how much — and never
    repeats the biggest project, which has its own line."""
    b = client.get("/api/recap").json()
    names = [t["name"] for t in client.get("/api/targets").json()]
    assert b["n_targets"] == 2
    line = b["also_shot"]
    assert line.startswith("Also shot: ")
    # The one target that isn't the biggest project — named, and only that one.
    others = [n for n in names if n != b["top_target_name"]]
    assert len(others) == 1
    assert line == f"Also shot: {others[0]}"
    assert b["top_target_name"] not in line
    # …and the caption carries it too, after the biggest project.
    assert b["caption"].endswith(f"also shot: {others[0]}")


def test_recap_also_shot_is_empty_on_a_library_with_nothing_else(client):
    """An untouched library has nothing else to name, so the line self-hides
    rather than reading "Also shot:" with a dangling colon."""
    assert client.get("/api/recap").json()["also_shot"] == ""
