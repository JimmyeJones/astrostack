"""Moon & Sun: a capture stacked while still copying in says so, and its still
is marked once the clip has changed (``VideoStackMeta.source_size``/``source_mtime``,
``VideoResultOut.source_changed``).

Reproduces the Scout's 2026-10-21 sweep (3) shape through the real
``POST /api/videos/Solar_video/stack``: the owner's undebayered pal8
``…-Solar-RAW.avi`` cut to 40 % of its bytes stacked ``done`` with
``warnings: []``, and after the file completed the list served the same result
with nothing said.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from seestack.video.ffmpeg import ffmpeg_available

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for videosynth
from videosynth import solar_raw_video  # noqa: E402

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed (bundled in the Docker image; see AGENTS.md §7)",
)


def _wait_for_job(client, job_id: str) -> dict:
    for _ in range(600):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "error", "cancelled", "interrupted"):
            return job
        time.sleep(0.05)
    raise AssertionError("video job never finished")


def _copying_capture(data_root: Path, tmp_path: Path) -> tuple[Path, bytes]:
    """A raw solar AVI 40 % of the way through being copied in, and its full bytes."""
    full = solar_raw_video(
        tmp_path / "whole.avi", n_frames=50, w=64, h=48, sharp_indices=range(40, 50),
    )
    data = full.read_bytes()
    d = data_root / "incoming" / "Solar_video"
    d.mkdir(parents=True, exist_ok=True)
    clip = d / "clip.avi"
    clip.write_bytes(data[: int(len(data) * 0.4)])
    return clip, data


def _stack(client) -> dict:
    job_id = client.post(
        "/api/videos/Solar_video/stack", json={"keep_percent": 30},
    ).json()["job_id"]
    job = _wait_for_job(client, job_id)
    assert job["state"] == "done", job.get("error")
    return client.get("/api/videos").json()["captures"][0]["result"]


def test_a_capture_stacked_mid_copy_warns_and_is_marked_once_it_completes(
    client, data_root, tmp_path,
):
    clip, whole = _copying_capture(data_root, tmp_path)
    result = _stack(client)
    assert any("could be read" in w and "still copying?" in w for w in result["warnings"]), (
        result["warnings"]
    )
    # Nothing has changed yet: the still describes the file on disk.
    assert result["source_changed"] is False

    clip.write_bytes(whole)  # the copy finishes under the same name

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result is not None, "the picture he made is kept, not hidden"
    assert result["source_changed"] is True

    # One click puts it right: the re-stack reads the whole clip and says nothing.
    result = _stack(client)
    assert result["source_changed"] is False
    assert not any("could be read" in w for w in result["warnings"])
    assert result["n_graded"] == 50


def test_the_edit_routes_answer_the_same_as_the_list(client, data_root, tmp_path):
    clip, whole = _copying_capture(data_root, tmp_path)
    _stack(client)
    clip.write_bytes(whole)
    r = client.post("/api/videos/Solar_video/sharpen", json={"amount": 0.5})
    assert r.status_code == 200, r.text
    assert r.json()["source_changed"] is True


def test_a_still_stacked_before_the_stamp_is_never_called_changed(
    client, data_root, tmp_path,
):
    """Upgrade safety: a ``meta.json`` with no stamp reads as current, even if the
    clip has since changed — "unknown" must never nag."""
    from webapp.config import Settings
    from webapp.video import META_NAME, result_dir

    clip, whole = _copying_capture(data_root, tmp_path)
    _stack(client)
    path = result_dir(Settings(data_root=str(data_root)), "Solar_video") / META_NAME
    raw = json.loads(path.read_text())
    del raw["source_size"]
    del raw["source_mtime"]
    path.write_text(json.dumps(raw))
    clip.write_bytes(whole)

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["source_changed"] is False


def test_a_still_whose_clip_is_gone_is_never_called_changed(client, data_root, tmp_path):
    clip, _whole = _copying_capture(data_root, tmp_path)
    _stack(client)
    clip.unlink()
    caps = client.get("/api/videos").json()["captures"]
    assert len(caps) == 1 and caps[0]["files"] == []
    assert caps[0]["result"]["source_changed"] is False
