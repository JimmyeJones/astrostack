"""The acquisition nameplate finally has a date to show.

A nameplate's whole purpose is the traditional acquisition caption — target,
integration, sub count, **date**, gear — and the date was the one part that never
appeared: ``_nameplate_fields`` read a ``DATE-OBS`` card, and the stacker wrote no
capture time into the master at all (the module docstring claimed it did). So
every picture the owner shared with a baked caption said everything except when
it was taken.

These pin both halves: the master now carries the capture time, and the caption
prefers the app's own recorded window — named as the observing night, through the
same helper the Nights card uses, so a baked JPEG and a card cannot date one
session differently.
"""

from __future__ import annotations

import json

from seestack.io.project import StackRunRow
from webapp.pipeline import _nameplate_fields


class _Entry:
    name = "M 42"


def _run(**kw) -> StackRunRow:
    fields = dict(
        id=1, timestamp_utc="2026-08-30T12:00:00Z", output_basename="master",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=505,
        canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
        options_json=json.dumps({}), total_exposure_s=15150.0,
    )
    fields.update(kw)
    return StackRunRow(**fields)


def test_the_caption_names_the_night_the_subs_were_shot():
    plate = _nameplate_fields("", _Entry(), _run(
        capture_start_utc="2024-11-15T22:01:00Z",
        capture_end_utc="2024-11-15T23:40:00Z",
    ))
    assert plate.date_iso == "2024-11-15"
    assert plate.date_end_iso == "2024-11-15"
    # …and never the day the stack ran, which is the only date it used to have.
    assert "2026" not in (plate.date_iso or "")


def test_a_stack_built_over_several_nights_says_so():
    plate = _nameplate_fields("", _Entry(), _run(
        capture_start_utc="2024-11-15T22:01:00Z",
        capture_end_utc="2024-11-18T21:40:00Z",
    ))
    assert (plate.date_iso, plate.date_end_iso) == ("2024-11-15", "2024-11-18")

    from seestack.nameplate import nameplate_line
    assert "15-18 Nov 2024" in nameplate_line(plate)


def test_the_observers_own_night_is_the_one_captioned():
    """One evening in New Zealand straddles UTC noon, so without the observer's
    longitude it would read as two nights — and disagree with the Nights card
    about the same session."""
    kw = dict(capture_start_utc="2024-11-15T10:00:00Z",
              capture_end_utc="2024-11-15T18:00:00Z")
    utc = _nameplate_fields("", _Entry(), _run(**kw))
    assert (utc.date_iso, utc.date_end_iso) == ("2024-11-14", "2024-11-15")
    local = _nameplate_fields("", _Entry(), _run(**kw), 150.0)
    assert (local.date_iso, local.date_end_iso) == ("2024-11-15", "2024-11-15")


def test_a_run_with_no_window_falls_back_to_the_fits_card(tmp_path):
    """What a FITS from elsewhere — or one written before the stacker stamped a
    capture time — has to offer."""
    import numpy as np
    from astropy.io import fits

    path = tmp_path / "master.fits"
    hdu = fits.PrimaryHDU(data=np.zeros((3, 8, 8), dtype=np.float32))
    hdu.header["DATE-OBS"] = "2024-09-12T03:14:55"
    hdu.header["DATE-END"] = "2024-09-14T02:00:00"
    hdu.writeto(path)

    plate = _nameplate_fields(str(path), _Entry(), _run())
    assert plate.date_iso == "2024-09-12T03:14:55"
    assert plate.date_end_iso == "2024-09-14T02:00:00"


def test_a_recorded_window_beats_the_fits_card(tmp_path):
    """The run record is the app's own answer, bucketed the way every other night
    surface buckets — so it wins rather than a raw header stamp that isn't."""
    import numpy as np
    from astropy.io import fits

    path = tmp_path / "master.fits"
    hdu = fits.PrimaryHDU(data=np.zeros((3, 8, 8), dtype=np.float32))
    hdu.header["DATE-OBS"] = "2024-09-12T03:14:55"
    hdu.writeto(path)

    plate = _nameplate_fields(str(path), _Entry(), _run(
        capture_start_utc="2024-11-15T22:01:00Z",
        capture_end_utc="2024-11-15T23:40:00Z",
    ))
    assert plate.date_iso == "2024-11-15"


def test_nothing_known_still_builds_a_tidy_dateless_caption():
    plate = _nameplate_fields("", _Entry(), _run())
    assert plate.date_iso is None
    assert plate.date_end_iso is None

    from seestack.nameplate import nameplate_line
    line = nameplate_line(plate)
    assert line and "··" not in line and not line.endswith("·")


def test_the_master_carries_the_capture_time(client, solved_library):
    """The other half: a fresh stack's FITS now says when its light was
    collected, so the file self-documents in Siril/PixInsight too."""
    import time

    from astropy.io import fits

    from seestack.io.library import Library

    r = client.post(
        "/api/targets/M_42/stack",
        json={"output_name": "dated", "sigma_clip": False,
              "background_flatten": False, "suppress_hot_pixels": False,
              "max_workers": 2},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    deadline = time.time() + 120
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled"):
            break
        time.sleep(0.05)
    assert body["state"] == "done", body

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            run = next(iter(proj.iter_stack_runs()))
        finally:
            proj.close()
    finally:
        lib.close()

    with fits.open(run.fits_path) as hdul:
        # Every fixture sub carries the same DATE-OBS, so there is one capture
        # instant and no span to record.
        assert hdul[0].header["DATE-OBS"].startswith("2024-09-12T03:14:55")
        assert "DATE-END" not in hdul[0].header


def test_the_baked_caption_says_how_many_nights_it_took():
    """A span alone cannot: "15-18 Nov 2024" is equally consistent with two
    nights and with four, and the count is what says how much work it was."""
    plate = _nameplate_fields("", _Entry(), _run(
        capture_start_utc="2024-11-15T22:01:00Z",
        capture_end_utc="2024-11-18T21:40:00Z",
        capture_hours_json=json.dumps([
            "2024-11-15T22:00:00Z", "2024-11-16T22:00:00Z",
            "2024-11-17T22:00:00Z", "2024-11-18T21:00:00Z"]),
    ))
    assert plate.nights == 4

    from seestack.nameplate import nameplate_line
    assert "15-18 Nov 2024 (4 nights)" in nameplate_line(plate)


def test_a_run_with_no_recorded_hours_captions_exactly_as_before():
    """Every run on the owner's install predates the column: the span alone,
    with no invented count."""
    plate = _nameplate_fields("", _Entry(), _run(
        capture_start_utc="2024-11-15T22:01:00Z",
        capture_end_utc="2024-11-18T21:40:00Z",
    ))
    assert plate.nights is None

    from seestack.nameplate import nameplate_line
    assert "nights" not in nameplate_line(plate)


def test_the_captioned_count_is_bucketed_for_the_same_observer_as_the_dates():
    """Both facts go through one helper, so the caption cannot say "1 night"
    beside a two-date span, or the reverse."""
    kw = dict(capture_start_utc="2024-11-15T10:00:00Z",
              capture_end_utc="2024-11-15T18:00:00Z",
              capture_hours_json=json.dumps(
                  ["2024-11-15T10:00:00Z", "2024-11-15T18:00:00Z"]))
    utc = _nameplate_fields("", _Entry(), _run(**kw))
    assert (utc.date_iso, utc.date_end_iso, utc.nights) == (
        "2024-11-14", "2024-11-15", 2)
    local = _nameplate_fields("", _Entry(), _run(**kw), 150.0)
    assert (local.date_iso, local.date_end_iso, local.nights) == (
        "2024-11-15", "2024-11-15", 1)

    from seestack.nameplate import nameplate_line
    # One night: the date says it, so the count stays out of the caption.
    assert "nights" not in nameplate_line(local)
