"""The per-target "finish my pictures for me?" override.

The owner approved auto-editing the walk-away picture on 2026-09-08 with a
condition — *"yes, but should be easy to override with manual settings"* — and a
library-wide switch is not an override for **one** target. These pin the store
itself; ``tests/webapp/test_pipeline.py`` pins that the unattended pass obeys it.
"""

from __future__ import annotations

from seestack.io.library import Library
from webapp.auto_edit_pref import (
    AUTO_EDIT_META_KEY,
    read_auto_edit_pref,
    wants_auto_edit,
    write_auto_edit_pref,
)


def _project(tmp_path):
    lib = Library.open_or_create(tmp_path / "lib")
    _entry, proj = lib.open_or_create_target("M 42")
    return lib, proj


def test_an_untouched_target_follows_the_library_setting(tmp_path):
    """Every existing project has no key, and must behave exactly as it did
    before this override existed — in both directions."""
    lib, proj = _project(tmp_path)
    try:
        assert read_auto_edit_pref(proj) is None
        assert wants_auto_edit(proj, True) is True
        assert wants_auto_edit(proj, False) is False
    finally:
        proj.close()
        lib.close()


def test_the_override_wins_over_the_setting_both_ways(tmp_path):
    lib, proj = _project(tmp_path)
    try:
        write_auto_edit_pref(proj, False)
        assert read_auto_edit_pref(proj) is False
        assert wants_auto_edit(proj, True) is False

        write_auto_edit_pref(proj, True)
        assert read_auto_edit_pref(proj) is True
        assert wants_auto_edit(proj, False) is True
    finally:
        proj.close()
        lib.close()


def test_clearing_deletes_the_key_rather_than_storing_the_settings_value(tmp_path):
    """"Follow the setting" and "someone chose what the setting happens to say"
    must not be the same state on disk: if clearing wrote a value, a later change
    to the library setting would silently not reach this target."""
    lib, proj = _project(tmp_path)
    try:
        write_auto_edit_pref(proj, True)
        write_auto_edit_pref(proj, None)
        assert proj.get_meta(AUTO_EDIT_META_KEY) is None
        assert read_auto_edit_pref(proj) is None
        assert wants_auto_edit(proj, False) is False
    finally:
        proj.close()
        lib.close()


def test_a_garbled_value_means_nobody_expressed_a_preference(tmp_path):
    """A hand-edited or stale value reads as *unset*, never as "off". The
    alternative is a typo silently turning a target's auto-finishing off, which
    is exactly the invisible behaviour change this feature must not have."""
    lib, proj = _project(tmp_path)
    try:
        for junk in ("", "  ", "maybe", "2", "null", "[]"):
            proj.set_meta(AUTO_EDIT_META_KEY, junk)
            assert read_auto_edit_pref(proj) is None, junk
            assert wants_auto_edit(proj, True) is True, junk
    finally:
        proj.close()
        lib.close()


def test_the_spellings_a_hand_edit_would_plausibly_use_are_understood(tmp_path):
    lib, proj = _project(tmp_path)
    try:
        for raw, want in (("1", True), ("true", True), (" TRUE ", True),
                          ("yes", True), ("on", True),
                          ("0", False), ("false", False), ("No", False),
                          ("off", False)):
            proj.set_meta(AUTO_EDIT_META_KEY, raw)
            assert read_auto_edit_pref(proj) is want, raw
    finally:
        proj.close()
        lib.close()
