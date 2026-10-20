"""Moon & Sun API: the stack drizzles when it is worth it, and says which it did.

Drives the whole route — request → job → ``stack_video`` → ``meta.json`` → the
``/api/videos`` result — on real ffmpeg-encoded raw captures in the owner's
file shape, so the sentence the page shows is the one the stack decided.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from seestack.video.drizzle import LUCKY_DRIZZLE_MIN_FRAMES
from seestack.video.ffmpeg import ffmpeg_available

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for videosynth
from videosynth import JITTER_H, JITTER_W, solar_raw_jittered_video  # noqa: E402

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(),
    reason="ffmpeg/ffprobe not installed (bundled in the Docker image; see AGENTS.md §7)",
)


def _drop(data_root: Path, n_frames: int, *, jitter: float) -> Path:
    d = data_root / "incoming" / "Solar_video"
    d.mkdir(parents=True, exist_ok=True)
    return solar_raw_jittered_video(d / "clip.avi", n_frames, jitter=jitter)


def _stack(client, **body) -> dict:
    import time

    body.setdefault("keep_percent", 100)
    job_id = client.post("/api/videos/Solar_video/stack", json=body).json()["job_id"]
    for _ in range(1200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "error", "cancelled", "interrupted"):
            break
        time.sleep(0.05)
    assert job["state"] == "done", job
    (cap,) = client.get("/api/videos").json()["captures"]
    return cap["result"]


def test_an_omitted_drizzle_field_is_the_picture_an_older_version_made(client, data_root):
    """Upgrade safety: an older client never sends the field, and must get the
    camera-sized stack with nothing new claimed about it."""
    _drop(data_root, 12, jitter=2.0)
    res = _stack(client)
    assert res["drizzle_scale"] == 1.0
    assert res["drizzle_note"] == ""
    assert (res["width"], res["height"]) == (JITTER_W, JITTER_H)


def test_a_short_capture_asked_to_drizzle_says_why_it_did_not(client, data_root):
    _drop(data_root, 12, jitter=2.0)
    res = _stack(client, drizzle=True)
    assert res["drizzle_scale"] == 1.0
    assert res["drizzle_note"].startswith("Kept at camera resolution")
    assert str(LUCKY_DRIZZLE_MIN_FRAMES) in res["drizzle_note"]
    assert (res["width"], res["height"]) == (JITTER_W, JITTER_H)


def test_a_long_jittery_capture_comes_back_drizzled_and_says_so(client, data_root):
    _drop(data_root, LUCKY_DRIZZLE_MIN_FRAMES + 20, jitter=3.0)
    res = _stack(client, drizzle=True)
    assert res["drizzle_scale"] == 1.5
    assert res["drizzle_note"].startswith("Drizzled to 1.5×")
    assert (res["width"], res["height"]) == (int(JITTER_W * 1.5), int(JITTER_H * 1.5))
    assert (res["source_width"], res["source_height"]) == (res["width"], res["height"])
    # The picture on disk is the finer one, not only the number in the record.
    from io import BytesIO

    from PIL import Image

    png = client.get("/api/videos/Solar_video/preview.png").content
    with Image.open(BytesIO(png)) as img:
        assert img.size == (res["width"], res["height"])


def test_an_old_meta_json_reads_as_not_drizzled(data_root):
    """Upgrade safety (AGENTS.md §9): the ``meta.json`` files already on the
    owner's box have neither key, and must load as what they were."""
    from webapp.config import Settings
    from webapp.video import META_NAME, VideoStackMeta, read_meta, result_dir

    settings = Settings(data_root=str(data_root))
    out = result_dir(settings, "Solar_video")
    out.mkdir(parents=True, exist_ok=True)
    meta = VideoStackMeta(
        capture_id="Solar_video", label="Sun", kind="solar",
        source_name="clip.avi", created_utc="2026-06-19T17:55:58Z",
        width=64, height=48, keep_percent=30, n_graded=10, n_kept=3,
        n_stacked=3, n_align_failed=0, stride=1, aligned=True,
        sharpness_best=1.0, sharpness_kept_median=0.9,
        sharpness_all_median=0.5, warnings=[],
    )
    raw = {k: getattr(meta, k) for k in VideoStackMeta.__dataclass_fields__}
    raw.pop("drizzle_scale")
    raw.pop("drizzle_note")
    (out / META_NAME).write_text(json.dumps(raw))

    loaded = read_meta(settings, "Solar_video")
    assert loaded is not None
    assert loaded.drizzle_scale == 1.0 and loaded.drizzle_note == ""


def test_the_running_job_says_how_long_a_drizzle_adds():
    """The owner's 2026-10-13 answer: say how long it will take, then run it."""
    from webapp.video import stack_progress_message

    short = stack_progress_message(40, drizzle=True, align=True, height=1080, width=1920)
    assert short == "Stacking the sharpest 40 frames"
    off = stack_progress_message(449, drizzle=False, align=True, height=1080, width=1920)
    assert off == "Stacking the sharpest 449 frames"
    long = stack_progress_message(449, drizzle=True, align=True, height=1080, width=1920)
    assert long.startswith("Stacking the sharpest 449 frames, and drizzling them")
    assert "min" in long
