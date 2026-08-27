"""List endpoints degrade per item instead of 500-ing the whole page.

A ``meta.json``/``grade.json`` on disk can be JSON-valid but wrong-*typed* — a
hand-edited file, or one written by a foreign/older version on an in-place
upgraded install (§9). ``read_meta``/``read_grade`` only filter by field *name*
(a plain dataclass does no type checking), so the bad value survives the
dataclass build and blows up later, in the Pydantic response model. Before this,
that one bad capture took the entire ``/api/videos`` list — and the Gallery's
stills strip — down with it.

The rule these pin is the house one the stats roll-ups already follow: one
unreadable item costs the owner that item, never the page.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from seestack.io.library import Library
from seestack.io.project import StackRunRow

from webapp import video
from webapp.config import Settings


def _write_still(data_root: Path, capture_id: str, *, meta_overrides: dict | None = None,
                 grade: dict | None = None) -> Settings:
    """A finished still on disk (``stack.png`` + ``meta.json``), no ffmpeg needed.

    ``meta_overrides`` is applied to the JSON *after* serialisation, so a test can
    write a value the dataclass would never produce — which is the whole point.
    """
    settings = Settings(data_root=str(data_root))
    h, w = 24, 32
    display = np.full((h, w, 3), 0.4, dtype=np.float32)

    incoming = Path(data_root) / "incoming" / capture_id
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "clip.mp4").write_bytes(b"not really a video")

    out_dir = video.result_dir(settings, capture_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    from seestack.stack.output import write_full_res_png

    write_full_res_png(out_dir / video.PNG_NAME, display)

    raw = {
        "capture_id": capture_id,
        "label": "Moon",
        "kind": "lunar",
        "source_name": "clip.mp4",
        "created_utc": "2026-08-27T21:00:00+00:00",
        "width": w,
        "height": h,
        "keep_percent": 30.0,
        "n_graded": 10,
        "n_kept": 3,
        "n_stacked": 3,
        "n_align_failed": 0,
        "stride": 1,
        "aligned": True,
        "sharpness_best": 1.0,
        "sharpness_kept_median": 0.9,
        "sharpness_all_median": 0.5,
        "warnings": [],
        "scores": [0.5] * 10,
        "crop_available": False,
        "crop_measured": True,
        "crop_trim_fraction": 0.0,
        "source_width": w,
        "source_height": h,
    }
    raw.update(meta_overrides or {})
    (out_dir / video.META_NAME).write_text(json.dumps(raw, indent=2), encoding="utf-8")
    if grade is not None:
        (out_dir / video.GRADE_NAME).write_text(json.dumps(grade), encoding="utf-8")
    return settings


def _capture(body: dict, capture_id: str) -> dict:
    return next(c for c in body["captures"] if c["id"] == capture_id)


# A JSON-valid value of the wrong *type* for a required, typed response field.
# The dataclass takes it; ``VideoResultOut`` does not.
_WRONG_TYPED = {"width": "sixty-four"}


def test_videos_list_survives_a_wrong_typed_meta(client, data_root):
    """One unusable ``meta.json`` reads as "never stacked"; the rest still list."""
    _write_still(data_root, "Good_video")
    _write_still(data_root, "Broken_video", meta_overrides=_WRONG_TYPED)

    r = client.get("/api/videos")
    assert r.status_code == 200, r.text
    body = r.json()

    # The healthy capture keeps its finished picture...
    good = _capture(body, "Good_video")
    assert good["result"] is not None
    assert (good["result"]["width"], good["result"]["height"]) == (32, 24)
    # ...and the broken one degrades to "no result" rather than failing the page.
    assert _capture(body, "Broken_video")["result"] is None


def test_videos_list_survives_a_wrong_typed_grade(client, data_root):
    """The same contract for ``grade.json`` — it reads as "never checked"."""
    _write_still(data_root, "Good_video", grade={
        "capture_id": "Good_video",
        "source_name": "clip.mp4",
        "created_utc": "2026-08-27T21:00:00+00:00",
        "n_graded": 4,
        "stride": 1,
        "scores": [0.1, 0.9, 0.4, 0.5],
        "warnings": [],
        "best_index": 1,
    })
    _write_still(data_root, "Broken_video", grade={
        "capture_id": "Broken_video",
        "source_name": "clip.mp4",
        "created_utc": "2026-08-27T21:00:00+00:00",
        "n_graded": 4,
        "stride": 1,
        "scores": "not a list of numbers",
        "warnings": [],
        "best_index": 1,
    })

    r = client.get("/api/videos")
    assert r.status_code == 200, r.text
    body = r.json()
    assert _capture(body, "Good_video")["sharpness"] is not None
    assert _capture(body, "Broken_video")["sharpness"] is None
    # The result panel is independent of the grade, so it survives either way.
    assert _capture(body, "Broken_video")["result"] is not None


def test_gallery_stills_survive_a_wrong_typed_meta(client, data_root):
    """The Gallery's stills strip drops the one bad still, not all of them."""
    _write_still(data_root, "Good_video")
    _write_still(data_root, "Broken_video", meta_overrides={"n_stacked": None})

    r = client.get("/api/gallery")
    assert r.status_code == 200, r.text
    ids = [v["capture_id"] for v in r.json()["videos"]]
    assert ids == ["Good_video"]


def _register_run(data_root: Path, safe: str, *, seam_residual: float | None) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=7,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=7,
                options_json=json.dumps({"sigma_clip": True}),
                seam_residual=seam_residual,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_gallery_skips_one_unbuildable_run_and_keeps_the_rest(
    client, solved_library, monkeypatch,
):
    """One run whose card can't be built must not hide every other picture.

    Every ``GalleryItem`` field is NOT NULL today, so nothing is *known* to raise
    here — the point of the guard is that a future field (or one odd row on an
    upgraded install) costs the owner one picture, not the page. Forced through
    the one optional helper that reads a nullable column.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    good_id = _register_run(solved_library, safe, seam_residual=None)
    bad_id = _register_run(solved_library, safe, seam_residual=0.5)

    from webapp.routers import gallery as gallery_mod

    def _boom(residual):  # noqa: ANN001, ANN202
        if residual is not None:
            raise ValueError("simulated future field that can raise")
        return None

    monkeypatch.setattr(gallery_mod, "seam_verdict", _boom)

    r = client.get("/api/gallery")
    assert r.status_code == 200, r.text
    run_ids = [it["run_id"] for it in r.json()["items"]]
    assert good_id in run_ids
    assert bad_id not in run_ids


@pytest.mark.parametrize("bad", [
    {"width": "sixty-four"},
    {"source_name": None},
    {"n_stacked": None},
])
def test_a_bad_still_never_500s_either_page(client, data_root, bad):
    """The shapes a hand-edited file actually takes, across both endpoints."""
    _write_still(data_root, "Broken_video", meta_overrides=bad)
    assert client.get("/api/videos").status_code == 200
    assert client.get("/api/gallery").status_code == 200
