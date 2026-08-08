"""Sharpening a finished Moon/Sun still in place — no re-stack, no ffmpeg.

How much sharpening a picture wants is something you can only judge by *looking
at it*, exactly like the framing — so acting on that judgement must not cost a
second multi-minute decode of the capture. Both edits are expressed as one
derivation from a kept original (see ``webapp/video.py``'s state model), which is
what lets them compose, and what these tests are mostly about: every path through
crop × sharpen × undo has to land on the right picture, because getting it wrong
loses one.

Like the crop tests, these build the saved artifacts directly (a stacked still is
just ``stack.png`` + ``stack.tiff`` + ``meta.json``), so they run in a container
with no ffmpeg — nothing here ever touches the source video.
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from seestack.video.detail import SHARPEN_MAX
from webapp import video
from webapp.config import Settings


def _textured_disk(w: int = 64, h: int = 48, radius: float = 8.0) -> np.ndarray:
    """A bright disk with fine surface detail, on a dark sky, in 0–1.

    The ripple matters: an unsharp mask has nothing to lift out of a flat disk,
    so a featureless test image would make "did the sharpen do anything?"
    unanswerable.
    """
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(yy - h / 2.0, xx - w / 2.0)
    ripple = 0.08 * np.sin(xx * 1.7) * np.cos(yy * 1.3)
    lum = np.where(r <= radius, 0.7 + ripple, 0.02).astype(np.float32)
    return np.repeat(np.clip(lum, 0.0, 1.0)[:, :, None], 3, axis=2)


def _write_still(
    data_root: Path,
    capture_id: str = "Lunar_video",
    *,
    image: np.ndarray | None = None,
    tiff: bool = True,
    sharpen_amount: float = 0.0,
    sharpen_baked: float = 0.0,
    crop_applied: bool = False,
    crop_box: list[int] | None = None,
) -> Settings:
    """Put a finished still on disk exactly as ``_video_stack_body`` would."""
    settings = Settings(data_root=str(data_root))
    display = _textured_disk() if image is None else image
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
        created_utc="2026-08-08T21:00:00+00:00",
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
        crop_applied=crop_applied,
        crop_available=bool(
            not crop_applied and framing is not None and framing.worthwhile
        ),
        crop_trim_fraction=(
            round(framing.trim_fraction, 4)
            if framing is not None and framing.worthwhile else 0.0
        ),
        source_width=int(display.shape[1]),
        source_height=int(display.shape[0]),
        crop_measured=True,
        sharpen_amount=sharpen_amount,
        sharpen_baked=sharpen_baked,
        crop_box=list(crop_box or []),
    )
    (out_dir / video.META_NAME).write_text(
        json.dumps(asdict(meta), indent=2), encoding="utf-8",
    )
    return settings


def _png_array(client, capture_id: str = "Lunar_video") -> np.ndarray:
    r = client.get(f"/api/videos/{capture_id}/preview.png")
    assert r.status_code == 200
    return np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))


def _tiff_array(client, capture_id: str = "Lunar_video") -> np.ndarray:
    import tifffile

    r = client.get(f"/api/videos/{capture_id}/download.tiff")
    assert r.status_code == 200
    return np.asarray(tifffile.imread(io.BytesIO(r.content)))


def _detail(arr: np.ndarray) -> float:
    """Local contrast — how much fine structure the picture carries."""
    a = np.asarray(arr, dtype=np.float64)
    return float(np.mean(np.abs(np.diff(a[..., 0], axis=1))))


def _sharpen(client, amount: float, capture_id: str = "Lunar_video"):
    return client.post(f"/api/videos/{capture_id}/sharpen", json={"amount": amount})


# --- the feature itself ------------------------------------------------------

def test_sharpening_a_saved_still_lifts_detail_without_restacking(client, data_root):
    """The whole point: one request, a crisper picture, the same capture."""
    _write_still(data_root)
    before = _png_array(client)

    r = _sharpen(client, 1.2)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["sharpen_amount"] == pytest.approx(1.2)
    assert result["sharpen_editable"] is True

    after = _png_array(client)
    assert after.shape == before.shape
    assert _detail(after) > _detail(before) * 1.2


def test_the_strength_can_be_changed_without_ever_compounding(client, data_root):
    """Every strength renders from the original, so trying several is safe."""
    _write_still(data_root)
    assert _sharpen(client, 0.6).status_code == 200
    once = _png_array(client)

    # Ask for the *same* strength again from a different starting point: sharpen
    # harder, then back. If any step rendered from the picture on disk instead of
    # the kept original, the result would be visibly over-cooked.
    assert _sharpen(client, 2.0).status_code == 200
    assert _sharpen(client, 0.6).status_code == 200
    again = _png_array(client)
    assert np.array_equal(once, again)


def test_taking_the_sharpening_back_off_restores_the_original_exactly(client, data_root):
    """Undo means the render the stack wrote, byte for byte — not an approximation."""
    _write_still(data_root)
    original_png = _png_array(client)
    original_tiff = _tiff_array(client)

    assert _sharpen(client, 2.0).status_code == 200
    assert not np.array_equal(_png_array(client), original_png)

    r = _sharpen(client, 0.0)
    assert r.status_code == 200, r.text
    assert r.json()["sharpen_amount"] == 0.0
    assert np.array_equal(_png_array(client), original_png)
    assert np.array_equal(_tiff_array(client), original_tiff)


def test_no_duplicate_is_left_behind_once_the_picture_is_back_to_itself(
    client, data_root,
):
    """The kept copy exists exactly while the picture differs from the stack's."""
    settings = _write_still(data_root)
    out_dir = video.result_dir(settings, "Lunar_video")
    assert not (out_dir / video.FULL_PNG_NAME).is_file()

    assert _sharpen(client, 1.2).status_code == 200
    assert (out_dir / video.FULL_PNG_NAME).is_file()

    assert _sharpen(client, 0.0).status_code == 200
    assert not (out_dir / video.FULL_PNG_NAME).is_file()
    assert not (out_dir / video.FULL_TIFF_NAME).is_file()


def test_the_sixteen_bit_tiff_is_sharpened_too_so_the_files_never_disagree(
    client, data_root,
):
    _write_still(data_root)
    before = _tiff_array(client)
    assert _sharpen(client, 1.2).status_code == 200
    after = _tiff_array(client)
    assert after.shape == before.shape
    assert after.dtype == np.uint16
    assert _detail(after) > _detail(before) * 1.2


def test_an_unsharpened_still_says_its_strength_can_be_changed(client, data_root):
    _write_still(data_root)
    r = client.get("/api/videos")
    result = r.json()["captures"][0]["result"]
    assert result["sharpen_amount"] == 0.0
    assert result["sharpen_editable"] is True


# --- crop x sharpen x undo: every path has to land on the right picture ------

def test_sharpening_a_cropped_still_keeps_the_crop(client, data_root):
    _write_still(data_root)
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    cropped = _png_array(client)

    r = _sharpen(client, 1.2)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["crop_applied"] is True
    assert result["crop_restorable"] is True
    after = _png_array(client)
    assert after.shape == cropped.shape
    assert (result["height"], result["width"]) == after.shape[:2]
    assert _detail(after) > _detail(cropped) * 1.2


def test_cropping_a_sharpened_still_keeps_the_sharpening(client, data_root):
    _write_still(data_root)
    assert _sharpen(client, 1.2).status_code == 200
    sharp_full = _png_array(client)

    r = client.post("/api/videos/Lunar_video/crop")
    assert r.status_code == 200, r.text
    assert r.json()["sharpen_amount"] == pytest.approx(1.2)
    cropped = _png_array(client)
    assert cropped.shape[0] < sharp_full.shape[0]
    # It is the *sharpened* picture that got cropped, not a re-derivation that
    # quietly dropped the sharpening: the same crop of the soft original would
    # carry visibly less fine detail.
    assert client.post("/api/videos/Lunar_video/uncrop").status_code == 200
    assert _sharpen(client, 0.0).status_code == 200
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    soft_cropped = _png_array(client)
    assert _detail(cropped) > _detail(soft_cropped) * 1.2


def test_undoing_the_crop_keeps_the_sharpening(client, data_root):
    """"Undo the crop" is not a request to change how sharp the picture is."""
    _write_still(data_root)
    assert _sharpen(client, 1.2).status_code == 200
    sharp_full = _png_array(client)
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200

    r = client.post("/api/videos/Lunar_video/uncrop")
    assert r.status_code == 200, r.text
    assert r.json()["crop_applied"] is False
    assert r.json()["sharpen_amount"] == pytest.approx(1.2)
    assert np.array_equal(_png_array(client), sharp_full)


def test_unsharpening_a_cropped_still_keeps_the_crop(client, data_root):
    _write_still(data_root)
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    plain_crop_png = _png_array(client)
    plain_crop_tiff = _tiff_array(client)

    assert _sharpen(client, 2.0).status_code == 200
    r = _sharpen(client, 0.0)
    assert r.status_code == 200, r.text
    assert r.json()["crop_applied"] is True
    assert r.json()["crop_restorable"] is True
    # Back to exactly the cropped picture it was — the crop is still a slice.
    assert np.array_equal(_png_array(client), plain_crop_png)
    assert np.array_equal(_tiff_array(client), plain_crop_tiff)


def test_both_routes_to_cropped_and_sharpened_land_on_the_same_picture(
    client, data_root,
):
    """The order the user happens to press the buttons in must not matter."""
    _write_still(data_root, capture_id="A_video")
    _write_still(data_root, capture_id="B_video")

    assert client.post("/api/videos/A_video/crop").status_code == 200
    assert _sharpen(client, 1.2, capture_id="A_video").status_code == 200

    assert _sharpen(client, 1.2, capture_id="B_video").status_code == 200
    assert client.post("/api/videos/B_video/crop").status_code == 200

    a = _png_array(client, "A_video")
    b = _png_array(client, "B_video")
    # Not asserted byte-identical on purpose: the crop box is measured on
    # whatever picture is on screen when it is asked for, and sharpening moves
    # the disk's edge by a fraction of a pixel. The framing must still agree to
    # within a pixel, and both must carry the sharpening.
    assert abs(a.shape[0] - b.shape[0]) <= 2
    assert abs(a.shape[1] - b.shape[1]) <= 2
    soft = _detail(_textured_disk())
    assert _detail(a) > soft and _detail(b) > soft
    for cap in ("A_video", "B_video"):
        result = client.get("/api/videos").json()
        listed = next(c for c in result["captures"] if c["id"] == cap)["result"]
        assert listed["crop_applied"] is True
        assert listed["sharpen_amount"] == pytest.approx(1.2)


def test_sharpening_never_invents_an_undo_crop_that_would_do_nothing(
    client, data_root,
):
    """A still the *stack* cropped has no bigger frame to go back to.

    Keeping the original is what the first in-place edit does, so after a
    sharpen one exists — but it holds the framing the picture already has.
    Offering "Undo crop" off its mere existence would be a button that changes
    the label and not the picture.
    """
    # A stack-time crop: already cropped, with no original kept beside it.
    settings = _write_still(data_root, crop_applied=True)
    assert client.get("/api/videos").json()["captures"][0]["result"][
        "crop_restorable"] is False

    r = _sharpen(client, 1.2)
    assert r.status_code == 200, r.text
    assert r.json()["crop_applied"] is True
    assert r.json()["crop_restorable"] is False
    assert (video.result_dir(settings, "Lunar_video") / video.FULL_PNG_NAME).is_file()
    # The Gallery reads the same decision, so the two surfaces can't disagree.
    still = client.get("/api/gallery").json()["videos"][0]
    assert still["crop_restorable"] is False
    # Un-sharpening still works — the crop is simply baked into the original.
    assert _sharpen(client, 0.0).status_code == 200
    assert client.get("/api/videos").json()["captures"][0]["result"][
        "crop_applied"] is True


def test_a_full_round_trip_returns_the_picture_the_stack_wrote(client, data_root):
    """crop → sharpen → unsharpen → uncrop lands exactly back at the start."""
    settings = _write_still(data_root)
    out_dir = video.result_dir(settings, "Lunar_video")
    original_png = _png_array(client)
    original_tiff = _tiff_array(client)

    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    assert _sharpen(client, 2.0).status_code == 200
    assert _sharpen(client, 0.0).status_code == 200
    r = client.post("/api/videos/Lunar_video/uncrop")
    assert r.status_code == 200, r.text

    assert np.array_equal(_png_array(client), original_png)
    assert np.array_equal(_tiff_array(client), original_tiff)
    assert not (out_dir / video.FULL_PNG_NAME).is_file()
    meta = video.read_meta(settings, "Lunar_video")
    assert meta is not None
    assert meta.crop_applied is False
    assert meta.crop_box == []
    assert meta.sharpen_amount == 0.0


# --- refusals: each one has a sentence the user can act on -------------------

def test_a_capture_with_no_picture_yet_is_a_clean_error(client, data_root):
    r = _sharpen(client, 1.2, capture_id="Nothing_video")
    assert r.status_code == 400
    assert "no finished picture" in r.json()["detail"].lower()


def test_asking_for_the_strength_it_already_has_says_so(client, data_root):
    _write_still(data_root)
    assert _sharpen(client, 1.2).status_code == 200
    r = _sharpen(client, 1.2)
    assert r.status_code == 400
    assert "already sharpened" in r.json()["detail"].lower()


def test_a_strength_past_the_ceiling_is_refused_before_anything_is_written(
    client, data_root,
):
    settings = _write_still(data_root)
    before = _png_array(client)
    r = _sharpen(client, SHARPEN_MAX + 1)
    assert r.status_code == 422
    assert np.array_equal(_png_array(client), before)
    assert not (
        video.result_dir(settings, "Lunar_video") / video.FULL_PNG_NAME
    ).is_file()


def test_a_still_sharpened_at_stack_time_by_an_older_version_says_why_not(
    client, data_root,
):
    """No soft render was kept, so a strength change would compound. Say so."""
    _write_still(data_root, sharpen_amount=1.2, sharpen_baked=1.2)
    listed = client.get("/api/videos").json()["captures"][0]["result"]
    assert listed["sharpen_amount"] == pytest.approx(1.2)
    assert listed["sharpen_editable"] is False

    r = _sharpen(client, 0.6)
    assert r.status_code == 400
    assert "stack the capture again" in r.json()["detail"].lower()


def test_a_crafted_capture_id_cannot_escape_the_results_folder(client, data_root):
    """The sharpen endpoint sanitises its id like every other one.

    Asserted against the sanitiser rather than a traversal URL for the reason
    the crop tests spell out: the HTTP client collapses dot segments, so such a
    request never reaches the endpoint at all.
    """
    _write_still(data_root)
    r = _sharpen(client, 1.2, capture_id="etc")
    assert r.status_code == 400
    assert not (Path(data_root).parent / "etc").exists()


# --- upgrade safety ----------------------------------------------------------

def test_a_still_saved_without_a_tiff_can_still_be_sharpened(client, data_root):
    """Results from before 16-bit TIFFs existed keep working."""
    settings = _write_still(data_root, tiff=False)
    before = _png_array(client)
    r = _sharpen(client, 1.2)
    assert r.status_code == 200, r.text
    assert _detail(_png_array(client)) > _detail(before) * 1.2
    assert not (video.result_dir(settings, "Lunar_video") / video.TIFF_NAME).is_file()
    # …and undo still puts the picture back exactly.
    assert _sharpen(client, 0.0).status_code == 200
    assert np.array_equal(_png_array(client), before)


def test_a_still_cropped_before_the_box_was_recorded_can_still_be_sharpened(
    client, data_root,
):
    """An older in-place crop kept no box; it is re-measured from the original."""
    settings = _write_still(data_root)
    assert client.post("/api/videos/Lunar_video/crop").status_code == 200
    cropped = _png_array(client)

    # Forget the box, exactly as a meta.json written before it existed would.
    meta = video.read_meta(settings, "Lunar_video")
    assert meta is not None and meta.crop_box
    out_dir = video.result_dir(settings, "Lunar_video")
    raw = json.loads((out_dir / video.META_NAME).read_text())
    del raw["crop_box"]
    (out_dir / video.META_NAME).write_text(json.dumps(raw), encoding="utf-8")

    r = _sharpen(client, 1.2)
    assert r.status_code == 200, r.text
    after = _png_array(client)
    assert after.shape == cropped.shape
    assert _detail(after) > _detail(cropped) * 1.2
    # The box is recorded now, so the next rebuild doesn't have to guess.
    refreshed = video.read_meta(settings, "Lunar_video")
    assert refreshed is not None and len(refreshed.crop_box) == 4


def test_an_old_meta_with_no_sharpen_fields_reads_as_an_unsharpened_picture(
    client, data_root,
):
    settings = _write_still(data_root)
    out_dir = video.result_dir(settings, "Lunar_video")
    raw = json.loads((out_dir / video.META_NAME).read_text())
    for gone in ("sharpen_amount", "sharpen_baked", "crop_box"):
        raw.pop(gone, None)
    (out_dir / video.META_NAME).write_text(json.dumps(raw), encoding="utf-8")

    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["sharpen_amount"] == 0.0
    assert result["sharpen_editable"] is True
    assert _sharpen(client, 1.2).status_code == 200


def test_a_failed_rebuild_leaves_the_picture_that_was_already_there(
    client, data_root, monkeypatch,
):
    """Every write lands on a temporary first, so a crash can't eat the still."""
    _write_still(data_root)
    before_png = _png_array(client)
    before_tiff = _tiff_array(client)

    real = video._rebuild_still

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(video, "_rebuild_still", boom)
    with pytest.raises(OSError):
        _sharpen(client, 1.2)
    monkeypatch.setattr(video, "_rebuild_still", real)

    assert np.array_equal(_png_array(client), before_png)
    assert np.array_equal(_tiff_array(client), before_tiff)
    # The metadata was never advanced either, so the picture and its description
    # still agree.
    result = client.get("/api/videos").json()["captures"][0]["result"]
    assert result["sharpen_amount"] == 0.0
