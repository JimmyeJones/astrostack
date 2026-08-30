"""Gallery endpoint: every stack run across targets, with its settings."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, options: dict,
                  total_exposure_s: float | None = None, **kw) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=7,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=7,
                options_json=json.dumps(options),
                total_exposure_s=total_exposure_s,
                **kw,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_gallery_lists_runs_with_options(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    opts = {"sigma_clip": True, "sigma_kappa": 2.5, "drizzle": False, "output_name": "m42"}
    run_id = _register_run(solved_library, safe, opts, total_exposure_s=3600.0)

    r = client.get("/api/gallery")
    assert r.status_code == 200
    items = r.json()["items"]
    mine = next(it for it in items if it["run_id"] == run_id)
    assert mine["safe"] == safe
    assert mine["n_frames_used"] == 7
    assert mine["canvas_w"] == 480 and mine["canvas_h"] == 320
    assert mine["total_exposure_s"] == 3600.0
    assert mine["preview_url"].endswith(f"/stack-runs/{run_id}/preview")
    # The full stacking settings round-trip through options_json.
    assert mine["options"]["sigma_clip"] is True
    assert mine["options"]["sigma_kappa"] == 2.5
    # A plain stack run can pre-fill the Stack form ("Reuse settings").
    assert mine["reusable"] is True
    # No label set yet → notes is null.
    assert mine["notes"] is None


def test_gallery_surfaces_run_notes(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe, {"sigma_clip": True})
    # Label the run via the notes PATCH, then confirm the gallery exposes it.
    r = client.patch(f"/api/targets/{safe}/stack-runs/{run_id}",
                     json={"notes": "best RGB v2"})
    assert r.status_code == 200
    items = client.get("/api/gallery").json()["items"]
    mine = next(it for it in items if it["run_id"] == run_id)
    assert mine["notes"] == "best RGB v2"


def test_gallery_carries_the_panel_flatness_verdict(client, solved_library):
    """The Gallery and the Compare view render these items, and Compare is where
    two stacks of one target actually get weighed against each other — so a
    mosaic's panel flatness has to travel with the item, not only with the run
    listing. Same server-side verdict, so no surface can disagree with another."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    flat = _register_run(solved_library, safe, {"sigma_clip": True},
                         is_mosaic=True, seam_residual=0.3)
    stepped = _register_run(solved_library, safe, {"sigma_clip": True},
                            is_mosaic=True, seam_residual=2.2)
    single = _register_run(solved_library, safe, {"sigma_clip": True})

    items = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert items[flat]["seam_verdict"] == "flat"
    assert items[stepped]["seam_verdict"] == "check"
    # An ordinary single-field stack has no joins to compare — no chip at all.
    assert items[single]["seam_verdict"] is None


def test_gallery_reports_a_preview_already_saved_north_up(client, solved_library):
    """The viewer's "North up" *view* asks the server to turn the stored bytes on
    the way out — which is a no-op on a picture a past "Adjust → North up → Save"
    already turned. The item carries the baked angle so the control can hide
    there instead of appearing and doing nothing, exactly as the Target hero
    reads the same field off the run listing."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    plain = _register_run(solved_library, safe, {"sigma_clip": True})
    baked = _register_run(solved_library, safe, {"sigma_clip": True})
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_stack_preview_north_up(baked, 90.0)
        finally:
            proj.close()
    finally:
        lib.close()

    items = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert items[baked]["preview_north_up_deg"] == 90.0
    # Every ordinary run reports nothing, so the control is offered as before.
    assert items[plain]["preview_north_up_deg"] is None


def test_gallery_reusable_flag_excludes_combine_and_editor(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    stack_id = _register_run(solved_library, safe, {"sigma_clip": True})
    combine_id = _register_run(solved_library, safe, {"channel_combine": {"mode": "RGB"}})
    editor_id = _register_run(solved_library, safe, {"editor_recipe": {"ops": []}})

    items = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert items[stack_id]["reusable"] is True
    assert items[combine_id]["reusable"] is False
    assert items[editor_id]["reusable"] is False


def test_gallery_empty_when_no_runs(client):
    # Fresh data root with no stacks → empty list, still 200.
    r = client.get("/api/gallery")
    assert r.status_code == 200
    assert r.json()["items"] == []


def _corrupt_project_schema(data_root, safe: str) -> None:
    """Stamp one target's project DB with a schema newer than this build, so
    ``Project.open`` raises ``RuntimeError`` — the realistic "opened after an
    image rollback" failure — without leaving a truly corrupt file."""
    import sqlite3

    lib = Library.open_or_create(data_root / "library")
    try:
        db = lib.target_dir(lib.find_target(safe)) / "project.sqlite"
    finally:
        lib.close()
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
    finally:
        conn.close()


def test_gallery_skips_a_broken_project_without_500ing(client, solved_library):
    """A single unreadable/newer-schema project DB must not hide *every* target's
    images. The gallery loop calls ``Project.open`` per target; without a guard one
    ``RuntimeError`` (schema newer than this build, e.g. after an image rollback)
    500s the whole endpoint. It must skip the bad target instead — like stats.py /
    storage.py already do."""
    targets = client.get("/api/targets").json()
    assert len(targets) >= 2  # the fixture ingests two targets
    good, bad = targets[0]["safe_name"], targets[1]["safe_name"]
    run_id = _register_run(solved_library, good, {"sigma_clip": True})
    _corrupt_project_schema(solved_library, bad)

    r = client.get("/api/gallery")
    assert r.status_code == 200  # fail-before: the broken target 500s the gallery
    run_ids = {it["run_id"] for it in r.json()["items"]}
    assert run_id in run_ids  # the healthy target's run still appears


def test_gallery_tolerates_bad_options_json(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-03T00:00:00Z",
                output_basename="bad", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=1,
                canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=1,
                options_json="not json{",
            ))
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get("/api/gallery")
    assert r.status_code == 200
    mine = next(it for it in r.json()["items"] if it["run_id"] == run_id)
    assert mine["options"] == {}


# --- Moon/Sun stills folded into the gallery -------------------------------
#
# A finished video still lives outside the library (``<data_root>/video/<id>/``)
# because none of the per-target machinery applies to it — which used to mean a
# beginner who stacked their first Moon picture went looking for it where every
# *other* finished picture lives and found nothing. These pin that it shows up,
# read-only, without becoming a stack run.


def _drop_video_still(data_root, folder: str = "Lunar_video", **overrides) -> dict:
    """Write a finished video result (PNG + meta.json) straight to disk.

    Deliberately avoids the ffmpeg-dependent stack path: what the gallery reads
    is the saved result, so the test writes exactly that.
    """
    d = data_root / "video" / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "stack.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    meta = {
        "capture_id": folder, "label": "Moon", "kind": "lunar",
        "source_name": "clip.mp4", "created_utc": "2026-05-04T00:00:00+00:00",
        "width": 640, "height": 480, "keep_percent": 30.0,
        "n_graded": 100, "n_kept": 30, "n_stacked": 29, "n_align_failed": 1,
        "stride": 1, "aligned": True,
        "sharpness_best": 1.0, "sharpness_kept_median": 0.9,
        "sharpness_all_median": 0.7, "warnings": [], "scores": [],
    }
    meta.update(overrides)
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def test_gallery_lists_a_finished_moon_still(client, data_root):
    _drop_video_still(data_root)

    body = client.get("/api/gallery").json()
    (still,) = body["videos"]
    assert still["capture_id"] == "Lunar_video"
    assert still["label"] == "Moon"
    assert still["kind"] == "lunar"
    assert still["source_name"] == "clip.mp4"
    assert still["n_stacked"] == 29
    assert (still["width"], still["height"]) == (640, 480)
    # The preview URL is the one the Moon & Sun page already serves.
    assert still["preview_url"] == "/api/videos/Lunar_video/preview.png"
    assert client.get(still["preview_url"]).status_code == 200
    # And it is *not* smuggled in as a stack run.
    assert body["items"] == []


def test_gallery_has_no_stills_on_an_install_that_never_stacked_a_video(client):
    body = client.get("/api/gallery").json()
    assert body["videos"] == []


def test_gallery_stills_are_newest_first(client, data_root):
    _drop_video_still(data_root, "A_video", created_utc="2026-05-01T00:00:00+00:00")
    _drop_video_still(data_root, "B_video", created_utc="2026-06-01T00:00:00+00:00")

    body = client.get("/api/gallery").json()
    assert [v["capture_id"] for v in body["videos"]] == ["B_video", "A_video"]


def test_gallery_skips_a_half_written_video_result(client, data_root):
    """A folder with no readable meta.json has no label or date to show."""
    _drop_video_still(data_root, "Good_video")
    bad = data_root / "video" / "Broken_video"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "stack.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (bad / "meta.json").write_text("not json{", encoding="utf-8")
    # ...and a graded-but-never-stacked capture has no picture to show at all.
    graded = data_root / "video" / "Graded_video"
    graded.mkdir(parents=True, exist_ok=True)
    (graded / "grade.json").write_text("{}", encoding="utf-8")

    body = client.get("/api/gallery").json()
    assert [v["capture_id"] for v in body["videos"]] == ["Good_video"]


def test_gallery_addresses_a_still_by_its_folder_not_its_metadata(client, data_root):
    """A hand-edited ``capture_id`` must not hand the UI a URL that 404s."""
    _drop_video_still(data_root, "Lunar_video", capture_id="something-else")

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["capture_id"] == "Lunar_video"
    assert client.get(still["preview_url"]).status_code == 200


def test_gallery_offers_the_16_bit_tiff_of_a_still(client, data_root):
    """The Gallery is where a beginner finds a finished Moon picture, so the
    full-quality copy has to be reachable from here — not only from the page
    that lists the source video (which a cleared-off NAS no longer has)."""
    _drop_video_still(data_root)
    (data_root / "video" / "Lunar_video" / "stack.tiff").write_bytes(b"II*\x00")

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["tiff_url"] == "/api/videos/Lunar_video/download.tiff"
    r = client.get(still["tiff_url"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/tiff"


def test_gallery_offers_no_tiff_when_the_still_has_none(client, data_root):
    """Offering a download that 404s is worse than not offering it."""
    _drop_video_still(data_root)

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["tiff_url"] is None


def test_gallery_reports_how_hard_a_still_was_sharpened(client, data_root):
    """The Moon & Sun card says "Sharpening: Medium"; the Gallery shows the same
    picture, so it needs the same field to say the same thing about it."""
    _drop_video_still(data_root, sharpen_amount=1.2)

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["sharpen_amount"] == 1.2


def test_a_still_made_before_sharpening_existed_reads_as_unsharpened(client, data_root):
    """Upgrade safety: an older ``meta.json`` has no such key, and must read as
    "not sharpened" rather than breaking the listing."""
    _drop_video_still(data_root)

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["sharpen_amount"] == 0.0
    # ...and it can still be sharpened in place: nothing was baked into it, so
    # the unsharpened original *is* the picture on disk.
    assert still["sharpen_editable"] is True


def test_gallery_carries_a_stills_warnings(client, data_root):
    """The Gallery is the only surface left for a user who has cleared the clip
    off their NAS, so it must not be the one that stays quiet about frames the
    stack had to drop. Same engine strings, verbatim — not re-worded."""
    _drop_video_still(data_root, warnings=["12 frames couldn't be aligned."])

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["warnings"] == ["12 frames couldn't be aligned."]


def test_a_still_with_nothing_to_report_carries_no_warnings(client, data_root):
    """An empty list, not a missing key, so the card has nothing to render rather
    than something to guard against.

    (``warnings`` is a *required* field on ``VideoStackMeta`` — it has been
    written by every version that ever made a still — so there is no "older
    ``meta.json``" case to cover here, unlike the framing and sharpening fields.
    A meta.json missing it isn't an old still, it's a broken one, and
    ``read_meta`` already drops those: see the half-written-result test above.)
    """
    _drop_video_still(data_root)

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["warnings"] == []


def test_gallery_offers_the_in_place_sharpen_on_a_still(client, data_root):
    """Someone who has cleared the clip off their NAS finds the picture only
    here, and is exactly the person who can't re-stack to change how sharp it
    is — so the Gallery has to carry the same offer the Moon & Sun page does."""
    _drop_video_still(data_root, sharpen_amount=0.6)

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["sharpen_editable"] is True


def test_gallery_offers_no_sharpen_when_the_stack_baked_one_in(client, data_root):
    """A picture whose *stack* sharpened it has no soft version kept beside it,
    so the strength can't be changed without stacking again. Offering a control
    that would only ever error is worse than offering none — and the Gallery
    must reach the same verdict the Moon & Sun page does."""
    _drop_video_still(data_root, sharpen_amount=1.2, sharpen_baked=1.2)

    (still,) = client.get("/api/gallery").json()["videos"]
    assert still["sharpen_amount"] == 1.2
    assert still["sharpen_editable"] is False
    # The endpoint agrees — which is the whole reason the offer is withheld.
    r = client.post("/api/videos/Lunar_video/sharpen", json={"amount": 0.6})
    assert r.status_code == 400
