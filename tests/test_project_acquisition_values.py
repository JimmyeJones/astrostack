"""`Project.iter_frame_columns` / `acquisition_values` — fields, not whole rows.

The two surfaces that match a calibration master to a target — the Stack form's
``calibration-suggestions`` and the Calibration page's coverage roll-up — each
read *every accepted frame of the target* to answer six questions: how long,
what gain, how warm, what size, what Bayer phase, how many. A ``FrameRow``
carries the frame's plate solution as well, which is a FITS header text of ~25
eighty-character cards, so the answer was dominated by the one field neither
surface reads.

Measured on a synthetic project the size of the owner's deepest target (35,894
subs, ~2 kB of ``wcs_json`` each): **1,132 ms / 146.4 MB peak** for the whole-row
read against **244 ms / 8.4 MB** for the six columns, with identical values. The
coverage roll-up pays it **per target**, across the whole library, which is the
reason memory rather than speed is the point here (AGENTS.md §10 — the OOM
history).

So what these tests pin is **equivalence** — the same values, in the same order,
as reading the rows — plus the memory property itself, which is the half that
would silently regress if a whole-table read came back.
"""

from __future__ import annotations

import pytest

from seestack.io.project import FrameRow, Project

#: The six columns, and the `AcquisitionValues` field each one lands in. Spelled
#: out here rather than derived, so a column quietly dropped from the read goes
#: red instead of simply not being compared.
COLUMNS = {
    "exposure_s": "exposures_s",
    "gain": "gains",
    "sensor_temp_c": "sensor_temps_c",
    "width_px": "widths_px",
    "height_px": "heights_px",
    "bayer_pattern": "bayer_patterns",
}


@pytest.fixture
def mixed_project(tmp_path) -> Project:
    """A target shot at two exposures, two gains and two sizes, across nights.

    Deliberately awkward in every way the callers care about: unrecorded values,
    a rejected sub, a blank Bayer card, a non-finite temperature, and an even
    split between two frame sizes so a modal tie has something to break.
    """
    proj = Project.create(tmp_path / "t", "T")
    rows = []
    for i in range(120):
        known = i % 9 != 0                     # ~1 in 9 recorded nothing
        rows.append(FrameRow(
            source_path=f"/incoming/T/sub_{i:04d}.fit",
            exposure_s=(10.0 if i % 3 else 30.0) if known else None,
            gain=(80.0 if i % 5 else 200.0) if known else None,
            sensor_temp_c=(-5.0 + (i % 40) * 0.1) if known else None,
            # An even split, so `modal_dim`'s tie-break — which takes whichever
            # candidate it met first — depends on the order these come back in.
            width_px=1080 if i % 2 else 1920,
            height_px=1920 if i % 2 else 1080,
            bayer_pattern=["GRBG", "RGGB", "", None][i % 4],
            # A solved frame's WCS is the bulk of the row, and the whole reason
            # this method exists — the fixture has to carry one.
            wcs_json="".join(f"CARD{c:02d}  = 1.2345678901E+02".ljust(80)
                             for c in range(25)),
            accept=i % 11 != 0,                # ~1 in 11 rejected
        ))
    proj.add_frames(rows)
    yield proj
    proj.close()


@pytest.mark.parametrize("accepted_only", [True, False])
def test_it_is_what_reading_the_rows_would_have_given(mixed_project,
                                                      accepted_only):
    """The equivalence claim, column by column and in order."""
    frames = list(mixed_project.iter_frames(accepted_only=accepted_only))
    acq = mixed_project.acquisition_values(accepted_only=accepted_only)
    assert acq.n_frames == len(frames)
    for column, attr in COLUMNS.items():
        assert getattr(acq, attr) == [getattr(f, column) for f in frames], column


def test_it_defaults_to_the_accepted_subs_only(mixed_project):
    """A rejected sub is not going into the stack a master would be applied to,
    and both callers have always filtered that way — so unlike `iter_frames`
    this one defaults to it, and getting that backwards would quietly widen
    every recommendation to frames the run will never see."""
    accepted = sum(1 for f in mixed_project.iter_frames(accepted_only=True))
    everything = sum(1 for f in mixed_project.iter_frames())
    assert accepted < everything, "fixture needs a rejected sub"
    assert mixed_project.acquisition_values().n_frames == accepted


def test_it_builds_no_frame_objects_at_all(mixed_project, monkeypatch):
    """The memory claim, in test form — and the one that would silently regress.

    Fail-before: the callers built a `FrameRow` for every accepted sub (35,894
    on the owner's deepest target) to read six small columns off it, and nothing
    anywhere would have noticed that coming back.
    """
    import seestack.io.project as project_module

    built = 0
    real = project_module._row_to_frame

    def counting(row):
        nonlocal built
        built += 1
        return real(row)

    monkeypatch.setattr(project_module, "_row_to_frame", counting)
    acq = mixed_project.acquisition_values()
    assert acq.n_frames > 0
    assert built == 0, f"built {built} FrameRow objects to read six columns"


def test_the_lists_are_parallel_and_in_id_order(mixed_project):
    """Parallel because a caller reads one column and then another off the same
    target; in `id` order because a modal value breaks a tie on whichever
    candidate it met first, so a different order could move `modal_dim`'s answer
    on a target evenly split between two frame sizes."""
    acq = mixed_project.acquisition_values()
    lengths = {len(getattr(acq, attr)) for attr in COLUMNS.values()}
    assert lengths == {acq.n_frames}
    ordered = [f.id for f in mixed_project.iter_frames(accepted_only=True)]
    assert ordered == sorted(ordered)
    # …and the values really do follow that order, not merely the count.
    assert acq.exposures_s == [
        f.exposure_s for f in mixed_project.iter_frames(accepted_only=True)]


def test_an_empty_target_answers_empty_rather_than_raising(tmp_path):
    """A freshly created target has no frames, and both callers reach this
    before anything has been ingested."""
    proj = Project.create(tmp_path / "empty", "E")
    try:
        acq = proj.acquisition_values()
        assert acq.n_frames == 0
        assert all(getattr(acq, attr) == [] for attr in COLUMNS.values())
    finally:
        proj.close()


def test_a_non_finite_temperature_round_trips_the_way_reading_a_row_does(tmp_path):
    """SQLite has no NaN: a non-finite REAL is stored as NULL and comes back as
    `None`, whichever way it is read. Pinned because the difference *would*
    matter — `_temperature_tally` and the engine's `_finite_temps` both take
    care to drop a non-finite reading rather than read a blank card as 0 °C —
    and because it is the one value where "same as reading the row" is not
    obvious from looking at the SQL."""
    proj = Project.create(tmp_path / "nan", "N")
    try:
        proj.add_frames([FrameRow(source_path="a.fit", sensor_temp_c=float("nan"),
                                  accept=True)])
        [row] = list(proj.iter_frames(accepted_only=True))
        [temp] = proj.acquisition_values().sensor_temps_c
        assert temp == row.sensor_temp_c is None
    finally:
        proj.close()


# ---------------------------------------------------------------------------
# `iter_frame_columns`, the primitive underneath — and the answer for any other
# caller that wants a handful of small fields off a deep target.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("accepted_only", [True, False])
def test_columns_are_the_values_reading_the_rows_would_have_given(
        mixed_project, accepted_only):
    """Equivalence, in the order `iter_frames` yields — which is the property
    every caller silently depends on and none of them would notice losing."""
    want = [(f.timestamp_utc, f.sky_adu_median, f.exposure_s, f.gain)
            for f in mixed_project.iter_frames(accepted_only=accepted_only)]
    got = list(mixed_project.iter_frame_columns(
        "timestamp_utc", "sky_adu_median", "exposure_s", "gain",
        accepted_only=accepted_only))
    assert got == want


def test_a_column_read_builds_no_frame_objects(mixed_project, monkeypatch):
    """The claim the two Target-page callers are for. Fail-before: both built a
    `FrameRow` per sub — 35,894 on the owner's deepest target — to read four
    small fields off it (`/sky-brightness`) and one (`/restack-gain`)."""
    import seestack.io.project as project_module

    built = 0
    real = project_module._row_to_frame

    def counting(row):
        nonlocal built
        built += 1
        return real(row)

    monkeypatch.setattr(project_module, "_row_to_frame", counting)
    rows = list(mixed_project.iter_frame_columns("timestamp_utc"))
    assert rows and built == 0, f"built {built} FrameRow objects to read one column"


def test_a_column_that_is_not_a_column_is_refused_not_interpolated(
        mixed_project):
    """Code-supplied today, but the check is free and turns a typo into a
    `ValueError` here instead of an `OperationalError` from inside a request —
    the rule `iter_frames_page` already follows."""
    for bad in ("fwhm", "FWHM_PX", "rowid", "id; DROP TABLE frames",
                "(SELECT 1)", ""):
        with pytest.raises(ValueError):
            list(mixed_project.iter_frame_columns(bad))
    # …including when it is hiding behind a good one.
    with pytest.raises(ValueError):
        list(mixed_project.iter_frame_columns("id", "nope"))
    # The table is still there, which a raised exception alone wouldn't prove.
    assert mixed_project.count() > 0


def test_asking_for_no_columns_is_refused_rather_than_selecting_nothing(
        mixed_project):
    """`SELECT  FROM frames` is a syntax error, and an empty `*columns` is far
    more likely to be an unpacking mistake than a request for empty tuples."""
    with pytest.raises(ValueError):
        list(mixed_project.iter_frame_columns())


def test_rows_are_plain_tuples_not_this_connections_row_factory(mixed_project):
    """A `sqlite3.Row`'s `repr` is its memory address, and these are values a
    caller compares, logs and puts in a test — the same reason
    `frames_fingerprint` drops the row factory."""
    [row] = list(mixed_project.iter_frame_columns("exposure_s"))[:1]
    assert type(row) is tuple
