"""Cropping a finished Moon/Sun still in place — no re-stack, no ffmpeg.

The offer to trim the empty sky only lands *after* the picture exists, so acting
on it must not cost a second decode of the capture. These tests build the saved
artifacts directly (a stacked still is just ``stack.png`` + ``stack.tiff`` +
``meta.json``), which is also why they run in a container without ffmpeg — the
crop never touches the source video, and that is exactly the point.
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from webapp import video
from webapp.config import Settings


def _disk_still(w: int = 64, h: int = 48, radius: float = 8.0) -> np.ndarray:
    """A small bright disk on a dark sky, in the 0–1 display range."""
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - h / 2.0, xx - w / 2.0)
    lum = np.where(r <= radius, 0.9, 0.02).astype(np.float32)
    return np.repeat(lum[:, :, None], 3, axis=2)


def _write_still(data_root: Path, capture_id: str = "Lunar_video", *,
                 image: np.ndarray | None = None,
                 tiff: bool = True) -> Settings:
    """Put a finished still on disk exactly as ``_video_stack_body`` would."""
    settings = Settings(data_root=str(data_root))
    display = _disk_still() if image is None else image
    # The capture folder itself, so `/api/videos` lists it. Never decoded — the
    # listing is a directory walk and cropping only ever touches the saved
    # picture — so a placeholder file is enough and no ffmpeg is needed.
    incoming = Path(data_root) / "incoming" / capture_id
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "clip.mp4").write_bytes(b"not really a video")
    out_dir = video.result_dir(settings, capture_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    from seestack.stack.output import write_full_res_png

    write_full_res_png(out_dir / video.PNG_NAME, display)
    if tiff:
        video._write_tiff16(out_dir / video.TIFF_NAME, display)

    framing = video.measure_framing(display)
    meta = video.VideoStackMeta(
        capture_id=capture_id,
        label="Moon",
        kind="lunar",
        source_name="clip.mp4",
        created_utc="2026-08-06T21:00:00+00:00",
        width=int(display.shape[1]),
        height=int(display.shape[0]),
        keep_percent=30.0,
        n_graded=10,
        n_kept=3,
        n_stacked=3,
        n_align_failed=0,
        stride=1,
        aligned=True,
        sharpness_best=1.0,
        sharpness_kept_median=0.9,
        sharpness_all_median=0.5,
        warnings=[],
        scores=[0.5] * 10,
        crop_available=bool(framing is not None and framing.worthwhile),
        crop_trim_fraction=(
            round(framing.trim_fraction, 4)
            if framing is not None and framing.worthwhile else 0.0
        ),
        source_width=int(display.shape[1]),
        source_height=int(display.shape[0]),
    )
    (out_dir / video.META_NAME).write_text(
        json.dumps(asdict(meta), indent=2), encoding="utf-8",
    )
    return settings


def _png_array(client, capture_id: str = "Lunar_video") -> np.ndarray:
    r = client.get(f"/api/videos/{capture_id}/preview.png")
    assert r.status_code == 200
    return np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))


def test_cropping_a_saved_still_trims_the_sky_without_restacking(client, data_root):
    """The whole feature: one request, a smaller picture, the disk still there."""
    _write_still(data_root)
    before = _png_array(client)

    r = client.post("/api/videos/Lunar_video/crop")
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["crop_applied"] is True
    assert result["crop_available"] is False
    assert result["crop_restorable"] is True
    assert result["width"] < 64 and result["height"] < 48
    assert (result["source_width"], result["source_height"]) == (64, 48)
    assert result["crop_trim_fraction"] > 0.15

    after = _png_array(client)
    assert after.shape[:2] == (result["height"], result["width"])
    # The disk survives — the cropped picture is mostly subject.
    assert float(np.mean(after[..., 0] > 128)) > 0.4
    assert after.max() == before.max()


def test_the_cropped_pixels_are_the_ones_the_full_frame_had(client, data_root):
    """Cropping is a slice, not a re-render — no pixel changes value."""
    settings = _write_still(data_root)
    full = _png_array(client)

    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    meta = video.read_meta(settings, "Lunar_video")
    assert meta is not None

    # Recover the box the crop used from the sizes, then compare pixel for pixel.
    cropped = _png_array(client)
    h, w = cropped.shape[:2]
    found = any(
        np.array_equal(cropped, full[y0:y0 + h, x0:x0 + w])
        for y0 in range(full.shape[0] - h + 1)
        for x0 in range(full.shape[1] - w + 1)
    )
    assert found, "the cropped PNG is not a sub-rectangle of the full frame"


def test_the_tiff_is_cropped_too_so_the_artifacts_never_disagree(client, data_root):
    _write_still(data_root)
    r = client.post("/api/videos/Lunar_video/crop")
    assert r.status_code == 200
    result = r.json()

    tiff = client.get("/api/videos/Lunar_video/download.tiff")
    assert tiff.status_code == 200
    arr = np.asarray(Image.open(io.BytesIO(tiff.content)))
    assert arr.shape[:2] == (result["height"], result["width"])


def test_a_crop_can_be_undone_and_the_full_frame_comes_back_unchanged(client, data_root):
    settings = _write_still(data_root)
    full = _png_array(client)

    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    r = client.post("/api/videos/Lunar_video/uncrop")
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["crop_applied"] is False
    assert result["crop_restorable"] is False
    # The offer comes back, re-measured from the restored picture.
    assert result["crop_available"] is True
    assert (result["width"], result["height"]) == (64, 48)

    assert np.array_equal(_png_array(client), full)
    # The kept originals are moved back, not left lying around as duplicates.
    out_dir = video.result_dir(settings, "Lunar_video")
    assert not (out_dir / video.FULL_PNG_NAME).exists()
    assert not (out_dir / video.FULL_TIFF_NAME).exists()


def test_cropping_twice_is_refused_with_a_line_the_user_can_act_on(client, data_root):
    _write_still(data_root)
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    r = client.post("/api/videos/Lunar_video/crop")
    assert r.status_code == 400
    assert "already been cropped" in r.json()["detail"]


def test_a_frame_filling_disk_is_refused_rather_than_cropped_pointlessly(
    client, data_root,
):
    # A disk that fills the frame: there is no sky worth trimming.
    _write_still(data_root, image=_disk_still(radius=40.0))
    r = client.post("/api/videos/Lunar_video/crop")
    assert r.status_code == 400
    assert "Nothing worth cropping" in r.json()["detail"]
    # ...and the picture is untouched.
    assert _png_array(client).shape[:2] == (48, 64)


def test_cropping_a_capture_with_no_picture_yet_is_a_clean_error(client, data_root):
    r = client.post("/api/videos/Never_stacked/crop")
    assert r.status_code == 400
    assert "no finished picture" in r.json()["detail"].lower()


def test_undoing_without_a_saved_full_frame_says_so(client, data_root):
    _write_still(data_root)
    r = client.post("/api/videos/Lunar_video/uncrop")
    assert r.status_code == 400
    assert "full-frame" in r.json()["detail"]


def test_a_still_saved_without_a_tiff_can_still_be_cropped(client, data_root):
    """Upgrade safety: a result from before TIFFs were written still crops."""
    _write_still(data_root, tiff=False)
    r = client.post("/api/videos/Lunar_video/crop")
    assert r.status_code == 200, r.text
    assert r.json()["crop_applied"] is True
    assert client.get("/api/videos/Lunar_video/download.tiff").status_code == 404


def test_a_crafted_capture_id_cannot_escape_the_results_folder(client, data_root):
    """Assert on the sanitiser itself, not on a traversal URL.

    A request path like ``/api/videos/..%2F..%2Fetc/crop`` never reaches the
    endpoint — the HTTP client collapses the dot segments, so the assertion
    would be about routing (and would flip between 404 and 405 depending on
    whether the SPA bundle happens to be built) rather than about safety.
    """
    from webapp.routers.video import _safe_capture_id

    # Every path character is stripped, so an id can only name a folder *inside*
    # the video results directory.
    assert _safe_capture_id("../../etc") == "etc"
    assert _safe_capture_id("/etc/passwd") == "etc_passwd"
    assert ".." not in _safe_capture_id("..")
    assert "/" not in _safe_capture_id("a/b")

    # ...and a sanitised id that names nothing is a clean refusal.
    r = client.post("/api/videos/etc/crop")
    assert r.status_code == 400
    assert not (Path(data_root).parent / "etc").exists()


@pytest.mark.parametrize("endpoint", ["crop", "uncrop"])
def test_the_meta_on_disk_is_what_the_api_reports(client, data_root, endpoint):
    """The saved metadata and the wire response can't drift apart."""
    settings = _write_still(data_root)
    if endpoint == "uncrop":
        assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    result = client.post(f"/api/videos/Lunar_video/{endpoint}").json()
    meta = video.read_meta(settings, "Lunar_video")
    assert meta is not None
    assert (meta.width, meta.height) == (result["width"], result["height"])
    assert meta.crop_applied is result["crop_applied"]
    assert meta.crop_available is result["crop_available"]


def test_a_still_from_before_framing_existed_gets_the_offer_too(client, data_root):
    """The owner's existing Moon pictures must not miss out on the crop.

    An older ``meta.json`` carries none of the ``crop_*`` fields, so it reads as
    "nothing to trim" when the truth is nobody ever looked. Since cropping works
    off the saved picture, the measurement can simply be made now.
    """
    settings = _write_still(data_root)
    out_dir = video.result_dir(settings, "Lunar_video")
    meta_path = out_dir / video.META_NAME
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("crop_applied", "crop_available", "crop_trim_fraction",
                "crop_measured", "source_width", "source_height"):
        raw.pop(key, None)
    meta_path.write_text(json.dumps(raw), encoding="utf-8")

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["crop_available"] is True
    assert result["crop_trim_fraction"] > 0.15
    # ...and it is offered for real: the crop then works.
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200


def test_the_backfilled_measurement_is_recorded_once(client, data_root, monkeypatch):
    """It costs one image read per pre-existing still, ever — not one per page
    load, which on a library of stills would be a directory of PNG decodes on
    every poll."""
    settings = _write_still(data_root)
    meta_path = video.result_dir(settings, "Lunar_video") / video.META_NAME
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("crop_applied", "crop_available", "crop_trim_fraction", "crop_measured"):
        raw.pop(key, None)
    meta_path.write_text(json.dumps(raw), encoding="utf-8")

    calls: list[int] = []
    real = video.measure_framing
    monkeypatch.setattr(
        video, "measure_framing", lambda img, **kw: (calls.append(1), real(img, **kw))[1],
    )
    for _ in range(3):
        assert client.get("/api/videos").json()["captures"][0]["result"][
            "crop_available"] is True
    assert len(calls) == 1
    assert json.loads(meta_path.read_text(encoding="utf-8"))["crop_measured"] is True


def test_a_frame_filling_still_is_measured_but_never_offered(client, data_root):
    """The backfill records "looked, nothing to trim" — it must not nag."""
    settings = _write_still(data_root, image=_disk_still(radius=40.0))
    meta_path = video.result_dir(settings, "Lunar_video") / video.META_NAME
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("crop_available", "crop_trim_fraction", "crop_measured"):
        raw.pop(key, None)
    meta_path.write_text(json.dumps(raw), encoding="utf-8")

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["crop_available"] is False
    assert json.loads(meta_path.read_text(encoding="utf-8"))["crop_measured"] is True


def test_an_already_cropped_still_is_never_re_measured(client, data_root):
    """Backfilling a cropped still would offer to crop the crop."""
    settings = _write_still(data_root)
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    meta = video.read_meta(settings, "Lunar_video")
    assert meta is not None
    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["crop_applied"] is True
    assert result["crop_available"] is False


def test_writing_a_new_still_drops_a_stale_full_frame_backup(data_root):
    """A fresh stack replaces the picture, so an old "undo" must not survive —
    restoring it would hand back a render of something else entirely."""
    settings = _write_still(data_root)
    video.crop_saved_still(settings, "Lunar_video")
    out_dir = video.result_dir(settings, "Lunar_video")
    assert (out_dir / video.FULL_PNG_NAME).is_file()
    assert (out_dir / video.FULL_TIFF_NAME).is_file()

    # This is the one line ``_video_stack_body`` runs after saving a new still.
    video._clear_full_frame_backup(out_dir)
    assert video.has_full_frame_backup(settings, "Lunar_video") is False
    assert not (out_dir / video.FULL_TIFF_NAME).exists()


# --- the Gallery offers the same crop -------------------------------------
#
# Moon & Sun lists the *captures* still sitting in ``incoming/``, so a user who
# has cleared the source video off the NAS — exactly the case the in-place crop
# was built for, since it never touches the source — only ever sees their
# picture in the Gallery. Before this, that user had a Moon adrift in black sky
# and nowhere to fix it.


def _gallery_still(client, capture_id: str = "Lunar_video") -> dict:
    stills = client.get("/api/gallery").json()["videos"]
    return next(s for s in stills if s["capture_id"] == capture_id)


def test_the_gallery_offers_the_crop_on_an_uncropped_still(client, data_root):
    _write_still(data_root)

    still = _gallery_still(client)
    assert still["crop_available"] is True
    assert still["crop_trim_fraction"] > 0.15
    assert still["crop_applied"] is False
    assert still["crop_restorable"] is False
    # ...and the offer is real: the crop the card fires actually works.
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200


def test_a_gallery_still_cropped_in_place_reports_its_undo(client, data_root):
    _write_still(data_root)
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200

    still = _gallery_still(client)
    assert still["crop_applied"] is True
    assert still["crop_available"] is False
    assert still["crop_restorable"] is True
    assert still["width"] < 64 and still["height"] < 48
    assert (still["source_width"], still["source_height"]) == (64, 48)

    # And undoing it from the same card puts the full frame back.
    assert client.post("/api/videos/Lunar_video/uncrop").status_code == 200
    back = _gallery_still(client)
    assert back["crop_applied"] is False
    assert back["crop_restorable"] is False
    assert (back["width"], back["height"]) == (64, 48)


def test_the_gallery_backfills_the_framing_of_a_pre_framing_still(client, data_root):
    """Same backfill the Moon & Sun page does — without it, the owner's existing
    stills would read as "nothing to trim" on the Gallery because nobody looked."""
    settings = _write_still(data_root)
    meta_path = video.result_dir(settings, "Lunar_video") / video.META_NAME
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("crop_applied", "crop_available", "crop_trim_fraction",
                "crop_measured", "source_width", "source_height"):
        raw.pop(key, None)
    meta_path.write_text(json.dumps(raw), encoding="utf-8")

    still = _gallery_still(client)
    assert still["crop_available"] is True
    assert still["crop_trim_fraction"] > 0.15
    assert json.loads(meta_path.read_text(encoding="utf-8"))["crop_measured"] is True


def test_a_still_whose_framing_cannot_be_read_does_not_break_the_gallery(
    client, data_root, monkeypatch,
):
    """The stills are an extra source on a page that must always render — a
    picture the backfill chokes on falls back to what its ``meta.json`` says
    rather than taking the whole Gallery down with it."""
    settings = _write_still(data_root)
    meta_path = video.result_dir(settings, "Lunar_video") / video.META_NAME
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("crop_available", "crop_trim_fraction", "crop_measured"):
        raw.pop(key, None)
    meta_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(
        video, "ensure_framing_measured",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("boom")),
    )

    body = client.get("/api/gallery").json()
    still = next(s for s in body["videos"] if s["capture_id"] == "Lunar_video")
    # Still listed, just with nothing to offer.
    assert still["label"] == "Moon"
    assert still["crop_available"] is False
    assert still["crop_restorable"] is False
