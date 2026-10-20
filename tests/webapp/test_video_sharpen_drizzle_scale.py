"""Moon & Sun sharpening reaches the same detail on a drizzled still.

v0.502.0 made the Moon/Sun stack drizzle onto a ×1.5 grid, but the unsharp
mask's radius (``SHARPEN_SIGMA_PX``) stayed a count of *output* pixels — so on a
drizzled still every preset measured detail against a blur ⅔ the size it was
tuned for, and "Medium" lifted a crater rim about half as much as it does on the
camera-sized still of the same capture (46–63 % of the boost, measured). The
radius now follows the still's ``drizzle_scale``, at stack time and on every
later re-sharpen from the saved picture.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from seestack.video.detail import SHARPEN_PRESETS, sharpen_still

sys.path.insert(0, str(Path(__file__).resolve().parent))  # webapp/ helpers
from test_video_sharpen_still import _write_still  # noqa: E402


def _ripple(n_camera_px: int, scale: float, cycles_per_camera_px: float) -> np.ndarray:
    """One scene — a surface ripple of fixed size on the sky — sampled at ``scale``
    output pixels per camera pixel."""
    x = np.arange(int(round(n_camera_px * scale))) / scale
    row = 0.5 + 0.1 * np.sin(2.0 * np.pi * cycles_per_camera_px * x)
    return np.repeat(np.tile(row, (32, 1))[..., None], 3, axis=2).astype(np.float32)


def _boost(before: np.ndarray, after: np.ndarray) -> float:
    """How much the ripple's amplitude grew (0 = untouched), away from the edges."""
    def amp(a: np.ndarray) -> float:
        r = a[16, 60:-60, 0].astype(np.float64) - 0.5
        return float(np.sqrt(2.0 * np.mean(r * r)))
    return amp(after) / amp(before) - 1.0


@pytest.mark.parametrize("freq", [0.08, 0.15, 0.25])
@pytest.mark.parametrize("amount", [a for _, a in SHARPEN_PRESETS if a > 0])
def test_a_preset_lifts_the_same_detail_on_a_drizzled_still(freq, amount):
    camera = _ripple(400, 1.0, freq)
    drizzled = _ripple(400, 1.5, freq)
    want = _boost(camera, sharpen_still(camera, amount))
    got = _boost(drizzled, sharpen_still(drizzled, amount, scale=1.5))
    assert got == pytest.approx(want, rel=0.05)


def test_camera_scale_is_the_picture_it_always_was():
    img = _ripple(200, 1.0, 0.15)
    assert np.array_equal(sharpen_still(img, 1.2), sharpen_still(img, 1.2, scale=1.0))


@pytest.mark.parametrize("bad", [0.0, -1.5, float("nan"), float("inf")])
def test_a_nonsense_scale_falls_back_to_camera_pixels(bad):
    img = _ripple(200, 1.0, 0.15)
    assert np.array_equal(sharpen_still(img, 1.2, scale=bad), sharpen_still(img, 1.2))


def test_resharpening_a_saved_drizzled_still_uses_its_scale(client, data_root):
    """The route that changes the strength later re-renders from the kept
    original — it must read the still's drizzle, not assume camera pixels."""
    from webapp import video

    yy, xx = np.mgrid[0:72, 0:96]
    r = np.hypot(yy - 36.0, xx - 48.0)
    lum = np.where(r <= 20, 0.6 + 0.1 * np.sin(xx * 0.7) * np.cos(yy * 0.6), 0.02)
    image = np.repeat(np.clip(lum, 0, 1)[..., None], 3, axis=2).astype(np.float32)
    settings = _write_still(data_root, image=image)
    meta_path = video.result_dir(settings, "Lunar_video") / video.META_NAME
    raw = json.loads(meta_path.read_text())
    raw["drizzle_scale"] = 1.5
    meta_path.write_text(json.dumps(raw))
    src = np.asarray(Image.open(video.result_dir(settings, "Lunar_video") / video.PNG_NAME)
                     .convert("RGB"), dtype=np.float32) / 255.0

    resp = client.post("/api/videos/Lunar_video/sharpen", json={"amount": 1.2})
    assert resp.status_code == 200, resp.text
    png = client.get("/api/videos/Lunar_video/preview.png").content
    got = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.int16)

    want = np.rint(sharpen_still(src, 1.2, scale=1.5) * 255.0).astype(np.int16)
    camera = np.rint(sharpen_still(src, 1.2) * 255.0).astype(np.int16)
    assert np.abs(got - want).max() <= 1
    assert np.abs(got - camera).max() > 1  # and the two radii really differ here


def test_a_stack_time_sharpen_on_a_drizzled_stack_uses_its_scale(
    client, data_root, monkeypatch,
):
    """The stack's own sharpen (the page's strength picked before stacking)
    runs on the drizzled render, so it too must size its radius to it."""
    from dataclasses import replace

    from seestack.video.ffmpeg import ffmpeg_available
    from webapp import video

    if not ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not installed")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for videosynth
    from videosynth import solar_raw_jittered_video

    d = data_root / "incoming" / "Solar_video"
    d.mkdir(parents=True, exist_ok=True)
    solar_raw_jittered_video(d / "clip.avi", 12, jitter=2.0)

    real_stack = video.stack_video
    monkeypatch.setattr(
        video, "stack_video",
        lambda *a, **k: replace(real_stack(*a, **k), drizzle_scale=1.5),
    )
    scales: list[float] = []
    real_sharpen = video.sharpen_still

    def spy(rgb, amount, *, scale=1.0):
        scales.append(scale)
        return real_sharpen(rgb, amount, scale=scale)

    monkeypatch.setattr(video, "sharpen_still", spy)

    import time

    job_id = client.post(
        "/api/videos/Solar_video/stack", json={"keep_percent": 100, "sharpen": 1.2},
    ).json()["job_id"]
    for _ in range(1200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "error", "cancelled", "interrupted"):
            break
        time.sleep(0.05)
    assert job["state"] == "done", job
    assert scales == [1.5]
