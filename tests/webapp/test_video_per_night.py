"""Moon & Sun with a per-night ``incoming/`` layout that repeats ``Lunar_video``.

Scout 2026-10-21 sweep (3): `/api/videos` listed one Moon capture out of three,
and a new night folder took over an already-stacked capture's id, so the stored
still was shown against the wrong folder while its own dropped off the list.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.webapp.test_video_crop import _write_still


def _clip(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not really a video")


def test_every_night_is_listed_and_addressable(client, data_root):
    incoming = Path(data_root) / "incoming"
    _clip(incoming / "2026-10-01" / "Lunar_video" / "a.mp4")
    _clip(incoming / "2026-10-05" / "Lunar_video" / "b.mp4")
    _clip(incoming / "Lunar_video" / "c.mp4")

    caps = client.get("/api/videos").json()["captures"]
    assert len(caps) == 3
    nights = sorted(c["night"] for c in caps)
    assert nights == ["", "2026-10-01", "2026-10-05"]
    for cap in caps:
        # The id round-trips through a route that resolves it server-side.
        r = client.get(f"/api/videos/{cap['id']}/preview.png")
        assert r.status_code == 404  # never stacked — but the id is the capture's own
    ids = {c["id"] for c in caps}
    assert ids == {"Lunar_video", "2026-10-01_Lunar_video", "2026-10-05_Lunar_video"}


def test_a_stacked_still_stays_with_its_own_night(client, data_root):
    incoming = Path(data_root) / "incoming"
    # A still stacked from a capture filed under a night folder (made from
    # `clip.mp4`, the source `_write_still` records)…
    _write_still(data_root)
    shutil.rmtree(incoming / "Lunar_video")
    _clip(incoming / "2026-10-01" / "Lunar_video" / "clip.mp4")
    # …then an earlier-sorting night with the same folder name arrives.
    _clip(incoming / "2026-09-28" / "Lunar_video" / "other.mp4")

    caps = {c["id"]: c for c in client.get("/api/videos").json()["captures"]}
    assert set(caps) == {"Lunar_video", "2026-09-28_Lunar_video"}
    stacked = caps["Lunar_video"]
    assert stacked["night"] == "2026-10-01"
    assert [f["name"] for f in stacked["files"]] == ["clip.mp4"]
    assert stacked["result"] is not None
    other = caps["2026-09-28_Lunar_video"]
    assert [f["name"] for f in other["files"]] == ["other.mp4"]
    assert other["result"] is None


def test_a_scan_of_one_night_asks_about_that_nights_capture(data_root):
    """Scanning ``incoming/<night>/`` alone must use the page's ids: there its
    ``Lunar_video`` is unique, and the bare id belongs to another night's still."""
    from webapp.config import Settings
    from webapp.pipeline import _unstacked_video_captures

    incoming = Path(data_root) / "incoming"
    settings = _write_still(data_root)  # stacked from incoming/Lunar_video/clip.mp4
    _clip(incoming / "2026-10-05" / "Lunar_video" / "new.mp4")
    assert isinstance(settings, Settings)

    night = _unstacked_video_captures(settings, incoming / "2026-10-05")
    assert night == [{"name": "Lunar_video", "label": "Moon"}]
    # The whole folder: only the new night is still waiting.
    assert _unstacked_video_captures(settings, incoming) == night
