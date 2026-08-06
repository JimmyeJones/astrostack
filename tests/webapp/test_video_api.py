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


def test_grading_an_unknown_capture_is_a_404(client):
    assert client.post("/api/videos/Nope_video/grade", json={}).status_code == 404


def test_grading_a_file_that_is_not_in_the_folder_is_rejected(client, data_root):
    _drop_capture(data_root)
    r = client.post("/api/videos/Lunar_video/grade", json={"file_name": "../secret.mp4"})
    assert r.status_code == 400
    assert "not a video in this capture folder" in r.json()["detail"]


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
