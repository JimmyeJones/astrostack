"""Moon & Sun API: list captures, stack one, download the result.

Uses a real ffmpeg-encoded synthetic capture dropped into the fixture's
``incoming/`` folder, so the whole route — discover → job → save → serve —
runs end to end.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from seestack.video.ffmpeg import ffmpeg_available

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for videosynth
from videosynth import lunar_video  # noqa: E402

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed (bundled in the Docker image; see AGENTS.md §7)",
)


def _drop_capture(data_root: Path, folder: str = "Lunar_video", **kwargs) -> Path:
    d = data_root / "incoming" / folder
    d.mkdir(parents=True, exist_ok=True)
    kwargs.setdefault("n_frames", 10)
    kwargs.setdefault("sharp_indices", (1, 4, 7))
    kwargs.setdefault("w", 64)
    kwargs.setdefault("h", 48)
    return lunar_video(d / "clip.mp4", **kwargs)


def _wait_for_job(client, job_id: str) -> dict:
    for _ in range(600):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "error", "cancelled", "interrupted"):
            return job
        import time

        time.sleep(0.05)
    raise AssertionError("video stack job never finished")


def test_lists_a_lunar_capture_with_a_plain_language_label(client, data_root):
    _drop_capture(data_root)
    body = client.get("/api/videos").json()
    assert body["available"] is True
    assert body["hint"] is None
    (cap,) = body["captures"]
    assert cap["label"] == "Moon"
    assert cap["kind"] == "lunar"
    assert cap["id"] == "Lunar_video"
    assert [f["name"] for f in cap["files"]] == ["clip.mp4"]
    assert cap["files"][0]["size_bytes"] > 0
    # Nothing stacked yet.
    assert cap["result"] is None


def test_lists_nothing_when_there_are_no_video_folders(client):
    body = client.get("/api/videos").json()
    assert body["captures"] == []


def test_deep_sky_sub_folders_are_never_offered_as_videos(client, built_library):
    """The fixture's ``M_42``/``NGC_7000`` FITS folders belong to the stacker."""
    body = client.get("/api/videos").json()
    assert body["captures"] == []


def test_stacking_a_capture_produces_a_downloadable_picture(client, data_root):
    _drop_capture(data_root)
    r = client.post("/api/videos/Lunar_video/stack", json={"keep_percent": 30})
    assert r.status_code == 200
    job = _wait_for_job(client, r.json()["job_id"])
    assert job["state"] == "done", job.get("error")
    assert job["result"]["n_stacked"] == 3
    assert job["result"]["width"] == 64

    listed = client.get("/api/videos").json()["captures"][0]
    result = listed["result"]
    assert result is not None
    assert result["n_graded"] == 10
    assert result["n_kept"] == 3
    assert result["source_name"] == "clip.mp4"
    assert result["preview_url"] == "/api/videos/Lunar_video/preview.png"

    png = client.get(result["preview_url"])
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"

    tiff = client.get(result["tiff_url"])
    assert tiff.status_code == 200
    assert len(tiff.content) > 0


def test_result_survives_a_restart_and_is_reported_again(client, data_root):
    """The still lives on disk with its metadata, not in the job record."""
    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/stack", json={"keep_percent": 30}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    from webapp.config import Settings
    from webapp.video import read_meta

    settings = Settings(data_root=str(data_root))
    meta = read_meta(settings, "Lunar_video")
    assert meta is not None
    assert meta.label == "Moon"
    assert meta.n_stacked == 3
    assert meta.keep_percent == 30.0


def test_downloading_before_stacking_is_a_clean_404(client, data_root):
    _drop_capture(data_root)
    assert client.get("/api/videos/Lunar_video/preview.png").status_code == 404
    assert client.get("/api/videos/Lunar_video/download.tiff").status_code == 404


def test_stacking_an_unknown_capture_is_a_404(client):
    assert client.post("/api/videos/nope/stack", json={}).status_code == 404


def test_asking_for_a_file_that_is_not_in_the_folder_is_rejected(client, data_root):
    _drop_capture(data_root)
    r = client.post(
        "/api/videos/Lunar_video/stack",
        json={"keep_percent": 30, "file_name": "../../etc/passwd"},
    )
    assert r.status_code == 400


def test_a_silly_keep_percent_is_rejected_before_the_job_starts(client, data_root):
    _drop_capture(data_root)
    assert client.post("/api/videos/Lunar_video/stack", json={"keep_percent": 0}).status_code == 422
    assert client.post("/api/videos/Lunar_video/stack", json={"keep_percent": 250}).status_code == 422


def test_a_crafted_capture_id_cannot_escape_the_results_folder(data_root):
    """Paths are always resolved server-side from the *sanitised* id.

    Asserted on the resolver rather than through a URL, because a crafted URL
    is normalised by the ASGI stack long before the route sees it — the guard
    that actually matters is that whatever string does arrive is sanitised
    before it becomes a path.
    """
    from seestack.video.discover import video_capture_id
    from webapp.config import Settings
    from webapp.video import result_dir, video_root

    settings = Settings(data_root=str(data_root))
    root = video_root(settings).resolve()
    for crafted in ("../../state", "..", "/etc/passwd", "a/../../b", "....//"):
        resolved = result_dir(settings, video_capture_id(crafted)).resolve()
        assert root in resolved.parents, crafted


def test_an_unknown_capture_id_downloads_as_a_clean_404(client, data_root):
    _drop_capture(data_root)
    assert client.get("/api/videos/not_a_capture/preview.png").status_code == 404


def test_the_solar_folder_is_labelled_sun(client, data_root):
    _drop_capture(data_root, folder="Solar_video")
    (cap,) = client.get("/api/videos").json()["captures"]
    assert cap["label"] == "Sun"
    assert cap["kind"] == "solar"


def test_the_result_carries_the_captures_sharpness_profile(client, data_root):
    """"How steady was your capture?" — the grading pass's own scores, served so
    the keep-% decision stops being a guess."""
    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 30},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    result = client.get("/api/videos").json()["captures"][0]["result"]
    prof = result["sharpness"]
    assert prof is not None
    # The curve is the graded frames, sharpest first, normalised to the best.
    assert prof["curve"][0] == pytest.approx(1.0)
    assert prof["curve"] == sorted(prof["curve"], reverse=True)
    # The synthetic capture has exactly 3 genuinely sharp frames in 10, so the
    # sharpest slice really is sharper than a typical frame...
    assert prof["spread"] == "variable"
    # ...and 30% (3 of 10) is precisely the setting that takes every sharp frame
    # and no soft one — keeping more would start averaging blur back in.
    assert prof["suggested_percent"] == 30.0
    assert [o["percent"] for o in prof["options"]] == [15.0, 30.0, 50.0]
    assert prof["options"][0]["sharpness_vs_typical"] > prof["options"][-1]["sharpness_vs_typical"]
    # The cut marker reflects what was actually stacked (3 of 10 frames).
    assert prof["cut_fraction"] == pytest.approx(0.3)
    assert prof["summary"]


def test_a_result_stacked_before_scores_were_kept_still_loads(client, data_root):
    """Upgrade safety: an existing ``meta.json`` has no ``scores`` — the result
    must still list, just without the panel."""
    import json

    from webapp.config import Settings
    from webapp.video import META_NAME, result_dir

    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 30},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    settings = Settings(data_root=str(data_root))
    meta_path = result_dir(settings, "Lunar_video") / META_NAME
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    raw.pop("scores")                      # exactly what an older version wrote
    meta_path.write_text(json.dumps(raw), encoding="utf-8")

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result is not None
    assert result["n_stacked"] == 3        # everything else still reported
    assert result["sharpness"] is None


def test_checking_a_capture_grades_it_without_stacking(client, data_root):
    """"Check this capture first" — the profile arrives, no picture is made."""
    _drop_capture(data_root)
    r = client.post("/api/videos/Lunar_video/grade", json={})
    assert r.status_code == 200
    job = _wait_for_job(client, r.json()["job_id"])
    assert job["state"] == "done", job.get("error")
    assert job["result"]["n_graded"] == 10

    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["result"] is None                   # nothing was stacked
    prof = cap["sharpness"]
    assert prof is not None
    assert prof["spread"] == "variable"
    assert prof["suggested_percent"] == 30.0
    # No stack yet, so there is no cut to mark and no "you kept…" clause.
    assert prof["cut_fraction"] == 0.0
    assert "you kept" not in prof["summary"]

    # And no picture was written.
    assert client.get("/api/videos/Lunar_video/preview.png").status_code == 404


def test_checking_a_capture_leaves_an_existing_still_alone(client, data_root):
    """Grading writes its own file — it must never disturb a finished stack."""
    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 50},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    before = client.get("/api/videos").json()["captures"][0]["result"]

    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    after = client.get("/api/videos").json()["captures"][0]["result"]
    assert after == before
    assert client.get("/api/videos/Lunar_video/preview.png").status_code == 200


def test_checking_a_capture_also_shows_its_sharpest_frame(client, data_root):
    """"Quick look" — is this capture worth stacking at all?

    The sharpest frame comes off the grading pass's own decode, so a beginner
    can see what the capture actually holds without spending a full stack (two
    decode passes and a multi-minute wait) finding out.
    """
    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    cap = client.get("/api/videos").json()["captures"][0]
    ql = cap["quicklook"]
    assert ql is not None
    assert ql["n_graded"] == 10
    # The synthetic capture's good-seeing frames are 1, 4 and 7 (1-based: 2, 5, 8).
    assert ql["frame_number"] in (2, 5, 8)
    assert "It's one frame, so it's noisy" in ql["note"]
    assert f"frame {ql['frame_number']} of the 10 we checked" in ql["note"]

    # It is a real, servable picture — and at the capture's native size.
    r = client.get(ql["url"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(r.content)) as img:
        assert img.size == (64, 48)

    # Still nothing stacked — checking a capture never makes a picture of it.
    assert cap["result"] is None
    assert client.get("/api/videos/Lunar_video/preview.png").status_code == 404


def test_a_capture_that_was_never_checked_offers_no_quick_look(client, data_root):
    _drop_capture(data_root)
    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["quicklook"] is None
    r = client.get("/api/videos/Lunar_video/quicklook.png")
    assert r.status_code == 404
    assert "hasn't been checked yet" in r.json()["detail"]


def test_an_older_grade_without_a_quick_look_still_shows_its_curve(client, data_root):
    """Upgrade safety: a ``grade.json`` written before the quick look existed
    has the scores but no ``best_index`` and no picture on disk."""
    import json

    from webapp import video as videomod

    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    out_dir = data_root / "video" / "Lunar_video"
    (out_dir / videomod.QUICKLOOK_NAME).unlink()
    raw = json.loads((out_dir / videomod.GRADE_NAME).read_text())
    del raw["best_index"]
    (out_dir / videomod.GRADE_NAME).write_text(json.dumps(raw))

    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["quicklook"] is None
    assert cap["sharpness"] is not None
    assert cap["sharpness"]["suggested_percent"] == 30.0


def test_re_checking_a_capture_replaces_the_quick_look(client, data_root):
    """The picture on disk always belongs to the scores beside it.

    Re-recording the same target overwrites the clip in place, so a stale frame
    left behind would be shown next to a completely different capture's numbers.
    """
    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    first = client.get("/api/videos/Lunar_video/quicklook.png").content
    first_number = client.get("/api/videos").json()["captures"][0]["quicklook"][
        "frame_number"
    ]

    # Same folder, same file name, a different capture: 12 frames whose one
    # good-seeing moment is the last.
    _drop_capture(data_root, n_frames=12, sharp_indices=(11,), w=48, h=36)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    ql = client.get("/api/videos").json()["captures"][0]["quicklook"]
    assert ql["n_graded"] == 12
    assert ql["frame_number"] == 12
    assert ql["frame_number"] != first_number
    assert client.get("/api/videos/Lunar_video/quicklook.png").content != first


def test_a_check_of_a_replaced_clip_stops_being_offered_as_this_captures(
    client, data_root,
):
    """Re-record over the clip and last night's check must stop speaking for it.

    The Seestar writes every night's Moon video into the *same* ``<Target>_video/``
    folder, so re-recording replaces ``clip.mp4`` in place while the capture id
    stays ``Lunar_video``. Without the source stamp the old scores, the old
    "keep N%" advice and the old quick-look frame all stay on screen describing
    a recording that no longer exists.
    """
    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["sharpness"] is not None
    assert cap["quicklook"] is not None

    # A different recording, same folder, same file name — and no re-check.
    _drop_capture(data_root, n_frames=14, sharp_indices=(13,), w=48, h=36)

    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["sharpness"] is None, "stale advice must not describe the new clip"
    assert cap["quicklook"] is None, "stale frame must not be shown as this capture"

    # ...and one click puts it right, rather than leaving a dead end.
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["sharpness"] is not None
    assert cap["quicklook"]["n_graded"] == 14


def test_the_quick_look_image_itself_stops_serving_once_its_check_is_stale(
    client, data_root,
):
    """The panels drop out, but the picture lives at a plain URL of its own.

    A tab left open, a bookmark or a browser cache still holds
    ``/quicklook.png`` — and until this guard it was handed last night's frame
    quite happily, next to nothing that said so. Fails before / passes after.
    """
    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    assert client.get("/api/videos/Lunar_video/quicklook.png").status_code == 200

    # A different recording, same folder, same file name — and no re-check.
    _drop_capture(data_root, n_frames=14, sharp_indices=(13,), w=48, h=36)

    r = client.get("/api/videos/Lunar_video/quicklook.png")
    assert r.status_code == 404
    assert "hasn't been checked" in r.json()["detail"]

    # ...and re-checking brings it back, so this is never a dead end.
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    assert client.get("/api/videos/Lunar_video/quicklook.png").status_code == 200


def test_the_quick_look_still_serves_when_the_clip_is_gone_from_incoming(
    client, data_root,
):
    """Same rule the panels use: no files is nothing to disagree with.

    Clearing the video off the NAS must not take the frame away — there is no
    newer recording it could be misrepresenting.
    """
    clip = _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    Path(clip).unlink()

    assert client.get("/api/videos/Lunar_video/quicklook.png").status_code == 200


def test_a_check_of_the_clip_still_on_disk_keeps_its_panels(client, data_root):
    """The guard must only fire on a real mismatch — merely listing again is not one."""
    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    for _ in range(3):
        cap = client.get("/api/videos").json()["captures"][0]
        assert cap["sharpness"] is not None
        assert cap["quicklook"] is not None


def test_a_grade_written_before_the_source_stamp_is_still_trusted(client, data_root):
    """Upgrade safety: "unknown" must mean "trust it", never "hide it".

    Every check the owner has already run wrote a ``grade.json`` with no stamp
    at all; an upgrade that read that as "can't prove it matches" would silently
    empty the panel on every capture on the page.
    """
    import json

    from webapp import video as videomod

    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    grade_path = data_root / "video" / "Lunar_video" / videomod.GRADE_NAME
    raw = json.loads(grade_path.read_text())
    del raw["source_size"]
    del raw["source_mtime"]
    grade_path.write_text(json.dumps(raw))

    # Replace the clip too: even then an un-stamped grade stays, because there
    # is nothing to compare and hiding it would be a guess.
    _drop_capture(data_root, n_frames=14, sharp_indices=(13,))

    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["sharpness"] is not None
    assert cap["quicklook"] is not None


def test_a_check_survives_the_video_being_cleared_off_the_nas(client, data_root):
    """A still whose clip is gone keeps its panels — there is nothing to disagree with."""
    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 50},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    job_id = client.post("/api/videos/Lunar_video/grade", json={}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    import shutil

    shutil.rmtree(data_root / "incoming" / "Lunar_video")

    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["files"] == []
    assert cap["result"] is not None
    assert cap["sharpness"] is not None
    assert cap["quicklook"] is not None


def test_grading_an_unknown_capture_is_a_404(client):
    assert client.post("/api/videos/Nope_video/grade", json={}).status_code == 404


def test_grading_a_file_that_is_not_in_the_folder_is_rejected(client, data_root):
    _drop_capture(data_root)
    r = client.post("/api/videos/Lunar_video/grade", json={"file_name": "../secret.mp4"})
    assert r.status_code == 400
    assert "not a video in this capture folder" in r.json()["detail"]


def _detail_energy(png_bytes: bytes) -> float:
    """How much fine structure a saved picture carries (mean squared Laplacian)."""
    from io import BytesIO

    import numpy as np
    from PIL import Image
    from scipy.ndimage import laplace

    with Image.open(BytesIO(png_bytes)) as img:
        arr = np.asarray(img.convert("L"), dtype=np.float32)
    return float(np.mean(laplace(arr) ** 2))


def _stack(client, *, capture_id: str = "Lunar_video", **body) -> dict:
    body.setdefault("keep_percent", 50)
    job_id = client.post(f"/api/videos/{capture_id}/stack", json=body).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    return client.get("/api/videos").json()["captures"][0]


def test_sharpening_brings_out_the_surface_detail_a_stack_softens(client, data_root):
    """A lucky stack is an average, and averaging softens.

    The editor can't open a Moon still, so without this the picture the beginner
    downloads is the soft one.
    """
    _drop_capture(data_root, n_frames=12, sharp_indices=(1, 4, 7, 10))
    plain = _stack(client)
    assert plain["result"]["sharpen_amount"] == 0.0
    soft_png = client.get("/api/videos/Lunar_video/preview.png").content

    sharpened = _stack(client, sharpen=1.2)
    assert sharpened["result"]["sharpen_amount"] == pytest.approx(1.2)
    sharp_png = client.get("/api/videos/Lunar_video/preview.png").content

    assert _detail_energy(sharp_png) > _detail_energy(soft_png)
    # It is still an ordinary picture at the same size, not a clipped mess.
    assert sharpened["result"]["width"] == plain["result"]["width"]
    assert sharpened["result"]["height"] == plain["result"]["height"]
    assert client.get("/api/videos/Lunar_video/download.tiff").status_code == 200


def test_sharpening_is_opt_in_so_an_omitted_field_changes_nothing(client, data_root):
    """Upgrade safety: the picture an existing install gets must not move."""
    _drop_capture(data_root)
    _stack(client)
    omitted = client.get("/api/videos/Lunar_video/preview.png").content

    cap = _stack(client, sharpen=0)
    explicit_zero = client.get("/api/videos/Lunar_video/preview.png").content

    assert explicit_zero == omitted
    assert cap["result"]["sharpen_amount"] == 0.0


def test_a_silly_sharpen_amount_is_rejected_before_the_job_starts(client, data_root):
    _drop_capture(data_root)
    for amount in (-0.5, 9.0):
        r = client.post(
            "/api/videos/Lunar_video/stack",
            json={"keep_percent": 50, "sharpen": amount},
        )
        assert r.status_code == 422, amount


def test_a_still_stacked_before_sharpening_existed_reads_as_unsharpened(
    client, data_root,
):
    import json

    from webapp import video as videomod

    _drop_capture(data_root)
    _stack(client)
    meta_path = data_root / "video" / "Lunar_video" / videomod.META_NAME
    raw = json.loads(meta_path.read_text())
    del raw["sharpen_amount"]
    meta_path.write_text(json.dumps(raw))

    cap = client.get("/api/videos").json()["captures"][0]
    assert cap["result"]["sharpen_amount"] == 0.0


def test_a_sharpened_still_can_still_be_cropped_to_the_disk(client, data_root):
    """Sharpening happens on the whole frame, before any crop — the two compose."""
    _drop_capture(data_root, n_frames=12, w=160, h=120)
    cap = _stack(client, sharpen=0.6, crop=True)
    result = cap["result"]
    assert result["sharpen_amount"] == pytest.approx(0.6)
    assert result["crop_applied"] is True
    assert result["width"] < result["source_width"]
    assert client.get("/api/videos/Lunar_video/preview.png").status_code == 200


def test_a_stack_that_sharpens_keeps_the_soft_render_beside_it(client, data_root):
    """So the strength stays changeable afterwards, with no second decode.

    Without the kept copy, changing your mind about sharpening would mean
    re-stacking a multi-minute capture — which is exactly the wait the in-place
    edits exist to remove.
    """
    from webapp import video as videomod

    _drop_capture(data_root, n_frames=12, sharp_indices=(1, 4, 7, 10))
    cap = _stack(client, sharpen=1.2)
    assert cap["result"]["sharpen_editable"] is True
    out_dir = data_root / "video" / "Lunar_video"
    assert (out_dir / videomod.FULL_PNG_NAME).is_file()
    sharp_png = client.get("/api/videos/Lunar_video/preview.png").content

    # And it really is the soft one: taking the sharpening off lands on a
    # picture with visibly less fine detail, rendered from that copy.
    r = client.post("/api/videos/Lunar_video/sharpen", json={"amount": 0})
    assert r.status_code == 200, r.text
    assert r.json()["sharpen_amount"] == 0.0
    soft_png = client.get("/api/videos/Lunar_video/preview.png").content
    assert _detail_energy(sharp_png) > _detail_energy(soft_png)


def test_an_unsharpened_stack_grows_no_second_copy(client, data_root):
    """It is its own original, so there is nothing to keep. Storage matters."""
    from webapp import video as videomod

    _drop_capture(data_root)
    cap = _stack(client)
    assert cap["result"]["sharpen_editable"] is True
    assert not (data_root / "video" / "Lunar_video" / videomod.FULL_PNG_NAME).is_file()


def test_a_full_frame_still_offers_to_crop_the_empty_sky(client, data_root):
    """The Seestar frames the Moon generously — the finished still should say so.

    Nothing is cropped unless asked, but the result carries the measurement, so
    a beginner who didn't know to ask can be offered it after seeing the picture.
    """
    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 30},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["crop_applied"] is False
    assert result["crop_available"] is True
    assert result["crop_trim_fraction"] > 0.15
    # Not cropped → the picture is the full frame, and says so.
    assert (result["width"], result["height"]) == (64, 48)
    assert (result["source_width"], result["source_height"]) == (64, 48)


def test_cropping_trims_the_sky_and_keeps_the_moon(client, data_root):
    """The whole feature: a smaller picture, still containing the disk."""
    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 30, "crop": True},
    ).json()["job_id"]
    job = _wait_for_job(client, job_id)
    assert job["state"] == "done", job.get("error")

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["crop_applied"] is True
    # Nothing left to offer once it has been done.
    assert result["crop_available"] is False
    assert result["width"] < 64 and result["height"] < 48
    assert (result["source_width"], result["source_height"]) == (64, 48)
    assert result["crop_trim_fraction"] > 0.15

    # The disk survives: the cropped picture is still mostly bright subject.
    import io

    import numpy as np
    from PIL import Image

    png = client.get(result["preview_url"])
    assert png.status_code == 200
    arr = np.asarray(Image.open(io.BytesIO(png.content)).convert("L"), dtype=np.float32)
    assert arr.shape == (result["height"], result["width"])
    assert float(np.mean(arr > 128)) > 0.4

    # The saved TIFF is cropped too — the two artifacts never disagree.
    tiff = client.get(result["tiff_url"])
    assert tiff.status_code == 200
    tarr = np.asarray(Image.open(io.BytesIO(tiff.content)))
    assert tarr.shape[:2] == (result["height"], result["width"])


def test_cropping_in_place_gives_what_a_re_stack_would_have(client, data_root):
    """The reason "Crop it" no longer re-stacks: it can't tell you anything new.

    Cropping the saved picture and re-stacking the capture with ``crop=True``
    must land on the same picture — same size, same pixels — otherwise the fast
    path would be quietly changing someone's result to save time.
    """
    import io

    import numpy as np
    from PIL import Image

    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 30},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    in_place = np.asarray(Image.open(io.BytesIO(
        client.get("/api/videos/Lunar_video/preview.png").content)).convert("RGB"))

    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 30, "crop": True},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    re_stacked = np.asarray(Image.open(io.BytesIO(
        client.get("/api/videos/Lunar_video/preview.png").content)).convert("RGB"))

    assert in_place.shape == re_stacked.shape
    assert np.array_equal(in_place, re_stacked)


def test_cropping_is_opt_in_so_an_omitted_field_changes_nothing(client, data_root):
    """Upgrade safety: a client that never heard of cropping gets the old picture."""
    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 30},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    assert client.get("/api/videos").json()["captures"][0]["result"]["width"] == 64


def test_a_result_stacked_before_cropping_existed_gets_measured(client, data_root):
    """Upgrade safety: an old ``meta.json`` has none of the framing fields.

    It still loads and still reads as *uncropped* — and because cropping now
    works off the saved picture, its framing is measured on the spot, so a
    picture the user already had gets the same offer a new one does instead of
    being stuck at "nothing to trim" because nobody ever looked.
    """
    import json

    from webapp.config import Settings
    from webapp.video import META_NAME, result_dir

    _drop_capture(data_root)
    job_id = client.post(
        "/api/videos/Lunar_video/stack", json={"keep_percent": 30},
    ).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    settings = Settings(data_root=str(data_root))
    meta_path = result_dir(settings, "Lunar_video") / META_NAME
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in (
        "crop_applied", "crop_available", "crop_trim_fraction", "crop_measured",
        "source_width", "source_height",
    ):
        raw.pop(key, None)
    meta_path.write_text(json.dumps(raw), encoding="utf-8")

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result is not None
    # Nothing claims it was cropped — it wasn't.
    assert result["crop_applied"] is False
    # ...but the framing is now measured from the saved picture, so the offer
    # is the same one this capture gets when stacked by a current version.
    assert result["crop_available"] is True
    assert result["crop_trim_fraction"] > 0.15
    # ...and the size still reports as the picture's own, not as 0.
    assert (result["source_width"], result["source_height"]) == (64, 48)


def test_asking_to_crop_a_frame_filling_disk_says_why_it_didnt(client, data_root):
    """A close-up has no sky to trim — the picture is left alone, and it says so
    rather than silently doing nothing."""
    from videosynth import lunar_frame, write_video

    d = data_root / "incoming" / "Solar_video"
    d.mkdir(parents=True, exist_ok=True)
    write_video(d / "clip.mp4", [
        lunar_frame(64, 48, cx=32, cy=24, radius=60,
                    sharpness=1.0 if i in (1, 4, 7) else 0.15, seed=i)
        for i in range(10)
    ])

    job_id = client.post(
        "/api/videos/Solar_video/stack", json={"keep_percent": 30, "crop": True},
    ).json()["job_id"]
    job = _wait_for_job(client, job_id)
    assert job["state"] == "done", job.get("error")

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["crop_applied"] is False
    assert result["crop_available"] is False
    assert (result["width"], result["height"]) == (64, 48)
    assert any("Nothing worth cropping" in w for w in result["warnings"])
    assert any("Sun" in w for w in result["warnings"])


# --- a still made before the video path could demosaic a raw capture ---------
#
# v0.347.0 fixed the stacking, but the picture already on disk keeps the mesh:
# nothing re-derives itself and there is no auto-stack for video. So the page
# has to say so. These pin who gets told and — more importantly — who doesn't.

def _drop_raw_capture(data_root: Path, folder: str = "Solar_video") -> Path:
    from videosynth import solar_raw_video

    d = data_root / "incoming" / folder
    d.mkdir(parents=True, exist_ok=True)
    return solar_raw_video(d / "clip.avi", n_frames=10, w=64, h=48,
                           sharp_indices=(1, 4, 7))


def _stale_meta(data_root: Path, capture_id: str) -> None:
    """Rewrite a finished still's metadata the way a pre-v0.347.0 build wrote
    it: with no ``colour_current`` claim at all."""
    import json

    from webapp.config import Settings
    from webapp.video import META_NAME, result_dir

    path = result_dir(Settings(data_root=str(data_root)), capture_id) / META_NAME
    raw = json.loads(path.read_text())
    raw.pop("colour_current", None)
    path.write_text(json.dumps(raw))


def test_a_still_stacked_before_the_demosaic_offers_a_re_stack(client, data_root):
    """The bug's leftover: a Sun stacked by an older build from a raw capture."""
    _drop_raw_capture(data_root)
    job_id = client.post("/api/videos/Solar_video/stack",
                         json={"keep_percent": 30}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    _stale_meta(data_root, "Solar_video")

    listed = client.get("/api/videos").json()["captures"][0]
    assert listed["result"]["colour_stale"] is True


def test_a_still_this_build_made_is_never_called_stale(client, data_root):
    """The same raw capture, stacked by this build — the picture is right, so
    the page must say nothing."""
    _drop_raw_capture(data_root)
    job_id = client.post("/api/videos/Solar_video/stack",
                         json={"keep_percent": 30}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"

    listed = client.get("/api/videos").json()["captures"][0]
    assert listed["result"]["colour_stale"] is False


def test_an_old_still_from_a_colour_capture_is_left_alone(client, data_root):
    """The case that must never be nagged: an ordinary colour Moon video. Its
    old still is as good as this build can make it, whatever its metadata says
    — and the check is *recorded*, so the source is probed exactly once."""
    _drop_capture(data_root)
    job_id = client.post("/api/videos/Lunar_video/stack",
                         json={"keep_percent": 30}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    _stale_meta(data_root, "Lunar_video")

    listed = client.get("/api/videos").json()["captures"][0]
    assert listed["result"]["colour_stale"] is False

    from webapp.config import Settings
    from webapp.video import read_meta

    meta = read_meta(Settings(data_root=str(data_root)), "Lunar_video")
    assert meta is not None
    assert meta.colour_current is True  # written back, so it is asked once


def test_a_still_whose_video_is_gone_is_never_called_stale(client, data_root):
    """No source to check means no verdict: telling someone to re-stack a
    capture they no longer have is worse than saying nothing."""
    clip = _drop_raw_capture(data_root)
    job_id = client.post("/api/videos/Solar_video/stack",
                         json={"keep_percent": 30}).json()["job_id"]
    assert _wait_for_job(client, job_id)["state"] == "done"
    _stale_meta(data_root, "Solar_video")
    clip.unlink()

    listed = client.get("/api/videos").json()["captures"][0]
    assert listed["result"]["colour_stale"] is False
