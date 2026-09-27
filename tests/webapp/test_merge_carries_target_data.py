"""Combining folders keeps what the owner *said* about them, not only their subs.

``POST /api/targets/merge`` ends in an ``rmtree`` of every source target's
folder, under a nudge that promises *"keeps every sub — and every picture you've
already made of it. Nothing is deleted."* v0.460.0 made that true of the
pictures; the target itself still arrived empty-handed. A note the owner typed
about a night, the tags he filed it under, the integration goal he set for it and
the Stack settings he saved for it were all destroyed with the folder.

These are the rest of that sentence, as tests. The conflict rule everywhere is
the same: **the destination's own decision wins**, and the source only ever fills
a blank — except for notes, which are additive because two notes about two nights
are both worth keeping.
"""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow, Project


def _library_with_two_nights(tmp_path: Path) -> Library:
    lib = Library.create(tmp_path / "lib")
    for name in ("M 31", "M 31 second night"):
        entry, proj = lib.create_target(name)
        try:
            proj.add_frame(FrameRow(
                source_path=str(tmp_path / f"{entry.safe_name}_light.fit"),
                width_px=8, height_px=8, bayer_pattern="RGGB", exposure_s=10.0,
            ))
        finally:
            proj.close()
    return lib


def test_the_source_note_and_tags_survive_the_merge(tmp_path):
    lib = _library_with_two_nights(tmp_path)
    try:
        lib.update_target("M 31", notes="best of the three nights",
                          tags=["galaxy", "keep"])
        lib.update_target("M 31 second night", notes="thin cloud after 1am",
                          tags=["galaxy", "windy"])

        lib.merge_targets("M_31", ["M_31_second_night"])

        kept = lib.find_target("M_31")
        assert kept is not None
        # The destination's own note stays first; the source's arrives under a
        # heading, so the owner can tell which night it was about.
        assert kept.notes is not None
        assert kept.notes.startswith("best of the three nights")
        assert "thin cloud after 1am" in kept.notes
        assert "M 31 second night" in kept.notes
        # Tags are a union, in the destination's order, with no duplicates.
        assert kept.tags == ["galaxy", "keep", "windy"]
    finally:
        lib.close()


def test_a_source_note_reaches_a_destination_that_had_none(tmp_path):
    lib = _library_with_two_nights(tmp_path)
    try:
        lib.update_target("M 31 second night", notes="thin cloud after 1am")
        lib.merge_targets("M_31", ["M_31_second_night"])
        kept = lib.find_target("M_31")
        assert kept is not None and kept.notes is not None
        assert "thin cloud after 1am" in kept.notes
        assert "M 31 second night" in kept.notes
    finally:
        lib.close()


def test_a_merge_with_nothing_to_carry_invents_nothing(tmp_path):
    """A merge of two plain folders must not invent notes or tags."""
    lib = _library_with_two_nights(tmp_path)
    try:
        lib.merge_targets("M_31", ["M_31_second_night"])
        kept = lib.find_target("M_31")
        assert kept is not None
        assert kept.notes is None
        assert kept.tags == []
    finally:
        lib.close()


def _set_prefs(lib: Library, safe: str, *, goal: str | None = None,
               defaults: str | None = None, auto_edit: str | None = None) -> None:
    proj = lib.open_target(safe)
    try:
        if goal is not None:
            proj.set_meta("integration_goal_s", goal)
        if defaults is not None:
            proj.set_meta("web_stack_defaults", defaults)
        if auto_edit is not None:
            proj.set_meta("auto_edit_on_autostack", auto_edit)
    finally:
        proj.close()


def _pref(lib: Library, safe: str, key: str) -> str | None:
    proj = lib.open_target(safe)
    try:
        return proj.get_meta(key)
    finally:
        proj.close()


def test_the_sources_saved_preferences_fill_blanks_in_the_destination(tmp_path):
    lib = _library_with_two_nights(tmp_path)
    try:
        _set_prefs(lib, "M_31_second_night", goal="7200.0",
                   defaults='{"drizzle": true}', auto_edit="0")
        lib.merge_targets("M_31", ["M_31_second_night"])

        assert _pref(lib, "M_31", "integration_goal_s") == "7200.0"
        assert _pref(lib, "M_31", "web_stack_defaults") == '{"drizzle": true}'
        assert _pref(lib, "M_31", "auto_edit_on_autostack") == "0"
    finally:
        lib.close()


def test_the_destinations_own_preferences_win(tmp_path):
    lib = _library_with_two_nights(tmp_path)
    try:
        _set_prefs(lib, "M_31", goal="36000.0", defaults='{"drizzle": false}',
                   auto_edit="1")
        _set_prefs(lib, "M_31_second_night", goal="7200.0",
                   defaults='{"drizzle": true}', auto_edit="0")
        lib.merge_targets("M_31", ["M_31_second_night"])

        assert _pref(lib, "M_31", "integration_goal_s") == "36000.0"
        assert _pref(lib, "M_31", "web_stack_defaults") == '{"drizzle": false}'
        assert _pref(lib, "M_31", "auto_edit_on_autostack") == "1"
    finally:
        lib.close()


def test_automation_state_is_not_carried(tmp_path):
    """Only decisions travel. ``web_auto_stack_*`` is the machinery's own record
    of what it already tried; carrying one into a target that has none could
    suppress the auto-stack of the deeper canvas the merge just created."""
    lib = _library_with_two_nights(tmp_path)
    try:
        proj = lib.open_target("M_31_second_night")
        try:
            proj.set_meta("web_auto_stack_attempt", "31")
            proj.set_meta("suggested_bg_mode", "poly")
        finally:
            proj.close()
        lib.merge_targets("M_31", ["M_31_second_night"])

        assert _pref(lib, "M_31", "web_auto_stack_attempt") is None
        assert _pref(lib, "M_31", "suggested_bg_mode") is None
    finally:
        lib.close()


def test_every_carried_key_is_the_one_the_web_layer_writes():
    """The drift guard. The engine may not import ``webapp`` (AGENTS.md §6), so
    :data:`seestack.io.merge._CARRIED_TARGET_META` spells those keys by value —
    which only stays correct while the values match the constants the web layer
    actually writes."""
    from seestack.io.merge import _CARRIED_TARGET_META
    from webapp.auto_edit_pref import AUTO_EDIT_META_KEY
    from webapp.goals import GOAL_META_KEY
    from webapp.schemas import STACK_DEFAULTS_META_KEY

    assert set(_CARRIED_TARGET_META) == {
        GOAL_META_KEY, STACK_DEFAULTS_META_KEY, AUTO_EDIT_META_KEY,
    }


def test_a_carried_frame_keeps_every_column_it_had(tmp_path):
    """The columns the merge used to drop, and the reason it dropped them.

    ``_frame_without_id`` listed the columns to copy by hand, so every column
    added to ``FrameRow`` after it was written — ``restored_utc``,
    ``source_size_bytes``, ``source_mtime``, ``streak_cx``/``streak_cy`` — was
    silently left behind. It now copies the row and resets only the three fields
    that are *about this project*: the id and the two cache paths. Driven off
    ``FrameRow``'s own fields, so a column added tomorrow is covered too.
    """
    from dataclasses import fields

    from seestack.io.merge import merge_projects

    src = Project.create(tmp_path / "src", name="src")
    try:
        full = FrameRow(
            source_path=str(tmp_path / "light.fit"),
            source_size_bytes=123456, source_mtime=1700000000.5,
            timestamp_utc="2026-09-01T22:00:00Z", exposure_s=10.0, gain=80.0,
            sensor_temp_c=-3.5, width_px=1080, height_px=1920,
            bayer_pattern="GRBG", ra_hint_deg=10.68, dec_hint_deg=41.27,
            wcs_json="CTYPE1", ra_center_deg=10.7, dec_center_deg=41.3,
            pixscale_arcsec=2.9, rotation_deg=12.5, fwhm_px=3.4, star_count=812,
            sky_adu_median=410.0, eccentricity_median=0.41,
            transparency_score=0.72, streak_detected=True, streak_count=2,
            streak_cx=511.5, streak_cy=233.0, mosaic_panel_id=3,
            accept=False, reject_reason="satellite streak", user_override=True,
            restored_utc="2026-09-02T09:00:00Z",
        )
        src.add_frame(full)
    finally:
        src.close()
    dst = Project.create(tmp_path / "dst", name="dst")
    try:
        list(merge_projects(dst, [src.project_dir], copy_cached_files=False))
        landed = next(iter(dst.iter_frames(accepted_only=False)))
    finally:
        dst.close()

    reset = {"id", "cached_path", "aligned_cache_path"}
    for f in fields(FrameRow):
        if f.name in reset:
            continue
        assert getattr(landed, f.name) == getattr(full, f.name), f.name
    # And the three that are deliberately about this project, not that one.
    assert landed.id is not None and landed.id != full.id
    assert landed.cached_path is None
    assert landed.aligned_cache_path is None
