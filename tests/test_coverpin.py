"""Who pinned the cover — the owner, or the app on his behalf?

``seestack/coverpin.py`` records the app's own cover pins in ``project_meta``
so a pin placed by a Combine or a bulk restack can be lifted by the app later,
while a pin the owner placed is never touched. The record is valid only while it
names the run actually pinned, which is what retires it the moment the owner
pins something else — with no code on his path having to know about it.
"""

from __future__ import annotations

from seestack.coverpin import (
    APP_COVER_PIN_META_KEY,
    PIN_REASON_KEPT_FINISHED,
    PIN_REASON_MERGE,
    app_pin_reason,
    clear_app_pin,
    mark_app_pin,
)
from seestack.io.project import Project


def test_a_record_answers_only_for_the_run_it_names(tmp_path):
    proj = Project.create(tmp_path / "t", name="T")
    try:
        assert app_pin_reason(proj, None) is None
        assert app_pin_reason(proj, 7) is None            # no record: his pin
        mark_app_pin(proj, 7, PIN_REASON_MERGE)
        assert app_pin_reason(proj, 7) == PIN_REASON_MERGE
        # The owner pins another run by hand: the record is stale and says so
        # without anyone having cleared it.
        assert app_pin_reason(proj, 8) is None
        # …or clears the pin altogether.
        assert app_pin_reason(proj, None) is None
        mark_app_pin(proj, 8, PIN_REASON_KEPT_FINISHED)
        assert app_pin_reason(proj, 8) == PIN_REASON_KEPT_FINISHED
        clear_app_pin(proj)
        assert app_pin_reason(proj, 8) is None
    finally:
        proj.close()


def test_every_doubt_reads_as_the_owners_pin(tmp_path):
    """The safe answer is "his": a broken record must never let the app lift a
    pin it cannot prove it placed."""
    proj = Project.create(tmp_path / "t", name="T")
    try:
        for junk in ("", "not json", "[]", '{"run_id": "7", "reason": "merge"}',
                     '{"run_id": true, "reason": "merge"}', '{"run_id": 7}',
                     '{"run_id": 7, "reason": ""}'):
            proj.set_meta(APP_COVER_PIN_META_KEY, junk)
            assert app_pin_reason(proj, 7) is None, junk
    finally:
        proj.close()
