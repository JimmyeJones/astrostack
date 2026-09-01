"""The baked caption stops printing a folder name under a shared picture.

A beginner who drops loose FITS in gets a target called ``Unsorted`` (the app's
own catch-all) or whatever their folder was called — and ``_nameplate_fields``
took the caption's title straight from that, so the keepsake, the share JPEG and
the print all read ``MyWorks_2026-08-14`` in serif under the picture the user
was about to post. Meanwhile the app already knew what the object was, from the
plate-solved centre it uses for the "What am I looking at?" card.

These pin both directions: a name that says nothing is replaced by the catalog's
own, and a name that means something is never overruled.
"""

from __future__ import annotations

import json

from seestack.io.project import StackRunRow
from webapp.pipeline import _nameplate_fields

# The bundled catalog's own numbers, so the test moves with the data.
M31_RA, M31_DEC = 10.685, 41.269


class _Entry:
    """A library entry, with the solved centre the Target page's object card reads."""

    def __init__(self, name: str, ra_deg=None, dec_deg=None) -> None:
        self.name = name
        self.ra_deg = ra_deg
        self.dec_deg = dec_deg


def _run(**kw) -> StackRunRow:
    fields = dict(
        id=1, timestamp_utc="2026-08-30T12:00:00Z", output_basename="master",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=505,
        canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
        options_json=json.dumps({}), total_exposure_s=15150.0,
    )
    fields.update(kw)
    return StackRunRow(**fields)


def test_a_folder_named_target_is_captioned_with_what_it_actually_is():
    plate = _nameplate_fields(
        "", _Entry("MyWorks_2026-08-14", M31_RA, M31_DEC), _run())
    assert plate.target == "Andromeda Galaxy"


def test_the_unsorted_catch_all_is_captioned_too():
    from seestack.io.library import UNSORTED_TARGET_NAME

    plate = _nameplate_fields(
        "", _Entry(UNSORTED_TARGET_NAME, M31_RA, M31_DEC), _run())
    assert plate.target == "Andromeda Galaxy"


def test_a_name_that_means_something_is_never_overruled():
    """The user's own words win whenever they identify the object — the caption
    must not "correct" M 31 into Andromeda Galaxy."""
    plate = _nameplate_fields("", _Entry("M 31", M31_RA, M31_DEC), _run())
    assert plate.target == "M 31"


def test_a_target_with_no_solved_centre_is_left_alone():
    plate = _nameplate_fields("", _Entry("MyWorks_2026-08-14"), _run())
    assert plate.target == "MyWorks_2026-08-14"


def test_a_field_that_is_not_on_a_catalog_object_is_left_alone():
    """Half a degree off is a neighbour, not the object — and this name is going
    into pixels the user shares."""
    plate = _nameplate_fields(
        "", _Entry("MyWorks_2026-08-14", M31_RA, M31_DEC + 0.5), _run())
    assert plate.target == "MyWorks_2026-08-14"


def test_the_fits_object_card_still_wins_when_it_says_something():
    """``OBJECT`` remains the first source; it is only replaced when it, too,
    identifies nothing."""
    plate = _nameplate_fields(
        "", _Entry("Unsorted", M31_RA, M31_DEC), _run())
    assert plate.target == "Andromeda Galaxy"


def test_nothing_is_written_back_to_the_target():
    """Display-time only: the entry the caption was built from is untouched."""
    entry = _Entry("MyWorks_2026-08-14", M31_RA, M31_DEC)
    _nameplate_fields("", entry, _run())
    assert entry.name == "MyWorks_2026-08-14"
