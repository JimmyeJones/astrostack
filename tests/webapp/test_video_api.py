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
