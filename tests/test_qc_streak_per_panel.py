"""The streak guard's majority, asked per **mosaic panel** (Scout 2026-11-19).

A mosaic's stationary object sits in one panel of four or nine, so the
whole-target majority in ``reconcile_streak_rejections`` can never fire for it,
and the position guard alone loses part of that panel on an alt-az night: the
panel's object is off the frame centre by construction, so it sweeps an arc as
the field turns, fastest across the meridian. These tests replay the Scout's
probe end to end through a real ``Project`` and pin both sides — the object
panel comes back in full, and nothing changes for a single field, for a mosaic
whose subs all carry the mosaic's centre, or for a short burst of real trails.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.qc.runner import reconcile_streak_rejections

_T0 = datetime(2026, 3, 14, 4, 0, tzinfo=UTC)
#: S30 portrait sub, pixels.
_W, _H = 1080, 1920
_CADENCE_S = 20.0
_LAT = 40.0


def _stamp(seconds: float) -> str:
    return (_T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _parallactic_deg(ha_h: float, dec_deg: float, lat_deg: float = _LAT) -> float:
    h = math.radians(ha_h * 15.0)
    d, p = math.radians(dec_deg), math.radians(lat_deg)
    return math.degrees(math.atan2(math.sin(h),
                                   math.tan(p) * math.cos(d) - math.sin(d) * math.cos(h)))


def _object_mark(offset: tuple[float, float], turn_deg: float) -> tuple[float, float]:
    """Where an object ``offset`` (frame fractions) from the centre lands after
    the field has turned ``turn_deg`` about the frame centre — rotated in
    *pixels*, reported back in normalised frame coordinates like QC records."""
    dx, dy = offset[0] * _W, offset[1] * _H
    a = math.radians(turn_deg)
    rx = dx * math.cos(a) - dy * math.sin(a)
    ry = dx * math.sin(a) + dy * math.cos(a)
    return 0.5 + rx / _W, 0.5 + ry / _H


def _mosaic(tmp_path, *, grid: int, dec: float, offset, hints: str = "panel",
            hours: tuple[float, float] = (-1.5, 1.5)):
    """A ``grid``×``grid`` mosaic shot interleaved (the Seestar's mosaic mode
    cycles the panels), the object in panel 0 flagged on every one of its subs.

    ``hints``: ``"panel"`` writes each panel's own pointing into its subs'
    header hint; ``"centre"`` writes the mosaic's centre into all of them.
    Returns ``(project, object_panel_ids)``.
    """
    proj = Project.create(tmp_path / "p", name="NGC 4565")
    ra0, dec_step, ra_step = 180.0, 1.8, 1.0 / max(0.2, math.cos(math.radians(dec)))
    panels = [(ra0 + (c - (grid - 1) / 2) * ra_step, dec + (r - (grid - 1) / 2) * dec_step)
              for r in range(grid) for c in range(grid)]
    q0 = _parallactic_deg(hours[0], dec)
    n = int((hours[1] - hours[0]) * 3600 / _CADENCE_S)
    obj_ids = []
    for i in range(n):
        ha = hours[0] + i * _CADENCE_S / 3600
        k = i % len(panels)
        ra_h, dec_h = panels[k] if hints == "panel" else (ra0, dec)
        row = FrameRow(source_path=f"p{k}_{i}.fit", timestamp_utc=_stamp(i * _CADENCE_S),
                       ra_hint_deg=ra_h, dec_hint_deg=dec_h, accept=True)
        if k == 0:
            cx, cy = _object_mark(offset, _parallactic_deg(ha, dec) - q0)
            row = FrameRow(source_path=row.source_path, timestamp_utc=row.timestamp_utc,
                           ra_hint_deg=ra_h, dec_hint_deg=dec_h,
                           streak_detected=True, streak_count=1,
                           streak_cx=cx, streak_cy=cy,
                           accept=False, reject_reason="auto:streak")
            obj_ids.append(proj.add_frame(row))
        else:
            proj.add_frame(row)
    return proj, obj_ids


def _still_rejected(proj) -> int:
    return sum(1 for f in proj.iter_frames() if f.reject_reason == "auto:streak")


@pytest.mark.parametrize("grid,dec", [(2, -5.0), (2, 20.0), (3, -5.0), (3, 20.0)])
def test_the_object_panel_of_a_mosaic_comes_back_in_full_across_transit(tmp_path, grid, dec):
    """The Scout's probe, end to end: before this, 27–32 % of the object
    panel's subs stayed ``auto:streak`` across the meridian."""
    proj, obj = _mosaic(tmp_path, grid=grid, dec=dec, offset=(0.3, 0.15))
    try:
        restored = reconcile_streak_rejections(proj)
        assert sorted(restored) == sorted(obj)
        assert _still_rejected(proj) == 0
        for fid in obj:
            f = proj.get_frame(fid)
            assert f.accept and f.reject_reason is None
            assert f.streak_detected  # still counted as "N streaked" in the UI
            assert f.restored_utc
    finally:
        proj.close()


def test_hints_at_the_mosaic_centre_give_no_per_panel_verdict(tmp_path):
    """If the Seestar writes the mosaic's centre into every sub (the open
    question diagnostic ``mosaic_panel_hints`` v2 answers), there are no panels
    to split by and the guard behaves exactly as before — only the position
    guard acts, and it still loses part of the turning arc."""
    proj, obj = _mosaic(tmp_path, grid=2, dec=-5.0, offset=(0.3, 0.15), hints="centre")
    try:
        restored = reconcile_streak_rejections(proj)
        assert set(restored) < set(obj)
        assert _still_rejected(proj) > 0
    finally:
        proj.close()


def test_a_single_field_is_still_rescued_by_the_whole_target_tier(tmp_path):
    proj = Project.create(tmp_path / "p", name="NGC 891")
    try:
        ids = [proj.add_frame(FrameRow(
            source_path=f"s{i}.fit", timestamp_utc=_stamp(i * 60),
            ra_hint_deg=35.6, dec_hint_deg=42.3,
            streak_detected=True, streak_count=1, streak_cx=0.5, streak_cy=0.5,
            accept=False, reject_reason="auto:streak")) for i in range(30)]
        for i in range(10):
            proj.add_frame(FrameRow(source_path=f"c{i}.fit", timestamp_utc=_stamp(i * 60),
                                    ra_hint_deg=35.6, dec_hint_deg=42.3, accept=True))
        assert sorted(reconcile_streak_rejections(proj)) == sorted(ids)
    finally:
        proj.close()


def _two_panels_with_trails(tmp_path, *, trail_span_s: float):
    """Two panels of 20 subs; 11 of panel A's carry real trails, scattered over
    the frame and spread across ``trail_span_s``."""
    proj = Project.create(tmp_path / "p", name="M 31")
    spots = [(0.1 + 0.08 * i, 0.9 - 0.075 * i) if i % 2 else (0.9 - 0.07 * i, 0.12 + 0.08 * i)
             for i in range(11)]
    sats = []
    for i in range(20):
        proj.add_frame(FrameRow(source_path=f"b{i}.fit", timestamp_utc=_stamp(i * 300),
                                ra_hint_deg=12.0, dec_hint_deg=41.0, accept=True))
    for i in range(20):
        if i < 11:
            x, y = spots[i]
            sats.append(proj.add_frame(FrameRow(
                source_path=f"a{i}.fit", timestamp_utc=_stamp(i * trail_span_s / 10),
                ra_hint_deg=10.0, dec_hint_deg=41.0, streak_detected=True, streak_count=1,
                streak_cx=x, streak_cy=y, accept=False, reject_reason="auto:streak")))
        else:
            proj.add_frame(FrameRow(source_path=f"a{i}.fit", timestamp_utc=_stamp(i * 300),
                                    ra_hint_deg=10.0, dec_hint_deg=41.0, accept=True))
    return proj, sats


def test_a_short_burst_of_trails_in_one_panel_keeps_its_rejection(tmp_path):
    """A panel is a smaller population than a target, so its majority is also
    held to the hour-long span: a burst of real trails over twenty minutes of
    one panel is not a stationary object."""
    proj, sats = _two_panels_with_trails(tmp_path, trail_span_s=20 * 60)
    try:
        assert reconcile_streak_rejections(proj) == []
        assert _still_rejected(proj) == len(sats)
    finally:
        proj.close()


def test_the_same_panel_majority_over_hours_is_rescued(tmp_path):
    """The control for the burst: the same panel majority, spread over the
    night, is what an object in that panel looks like."""
    proj, sats = _two_panels_with_trails(tmp_path, trail_span_s=3 * 3600)
    try:
        assert sorted(reconcile_streak_rejections(proj)) == sorted(sats)
    finally:
        proj.close()


def test_a_user_override_in_the_object_panel_is_never_touched(tmp_path):
    proj, obj = _mosaic(tmp_path, grid=2, dec=-5.0, offset=(0.3, 0.15))
    try:
        held = obj[3]
        proj.update_frame(held, user_override=True)
        restored = reconcile_streak_rejections(proj)
        assert held not in restored
        f = proj.get_frame(held)
        assert not f.accept and f.reject_reason == "auto:streak"
    finally:
        proj.close()
