"""`Project.iter_night_frames` — when a sub landed and how that night went.

Four surfaces group a target's subs into nights and summarise them: the Target
page's "Last session" card (`session_recap`), its sharpness sparkline
(`focus_trend`), its Nights card (`nights_breakdown`), and the Dashboard's
combined "Last night" (`library_session_recap`, over *every* target in the
library). Between them they read five small fields off each sub — and they were
reading whole `FrameRow`s to do it, which is `SELECT *`: on a solved sub the
plate solution is a FITS header text of ~25 eighty-character cards, i.e. almost
all of what the read moves, for a field not one of the four ever looks at.

Measured on a synthetic project the size of the owner's deepest target (35,894
subs over 300 nights, ~2 kB of `wcs_json` each, best of 3) — see
`Project.iter_night_frames` for the per-surface table. Memory is the point
rather than the milliseconds (AGENTS.md §10, this box has an OOM history), and
three of the four sit on the page the owner opens most.

So what these tests pin is **equivalence** (the same values, in the same order,
as reading the rows) plus the memory property itself, measured against the row
read on the same frames — that is the half that would silently regress if a
whole-row read came back.
"""

from __future__ import annotations

import pytest

from seestack.io.project import (
    _NIGHT_COLUMNS,
    FrameNight,
    FrameRow,
    Project,
)

#: Every field of `FrameNight`, and the `FrameRow` expression that must equal
#: it. Spelled out rather than derived, so a field quietly dropped from the read
#: goes red instead of simply not being compared.
FIELDS = {
    "timestamp_utc": lambda f: f.timestamp_utc,
    "accept": lambda f: f.accept,
    "exposure_s": lambda f: f.exposure_s,
    "reject_reason": lambda f: f.reject_reason,
    "fwhm_px": lambda f: f.fwhm_px,
}

#: A solved sub's WCS: the bulk of the row, and the whole reason this method
#: exists — a fixture has to carry one, or it is measuring nothing.
WCS = "".join(f"CARD{c:02d}  = 1.2345678901E+02".ljust(80) for c in range(25))


@pytest.fixture
def nightly_project(tmp_path) -> Project:
    """A target shot over several nights, every way a night can go.

    Deliberately awkward in each of them: subs QC set aside with three different
    reasons, subs whose stars were never measured, two exposure lengths, and a
    sub carrying no capture time at all — the one row every surface here drops
    before it counts anything.
    """
    proj = Project.create(tmp_path / "t", "T")
    rows = []
    for i in range(240):
        night, k = divmod(i, 40)
        set_aside = i % 13 == 0
        rows.append(FrameRow(
            source_path=f"/incoming/T/sub_{i:04d}.fit",
            # Undated on one sub only: datable-ness is what the session split
            # keys on, so it must not be the whole fixture's shape.
            timestamp_utc=(None if i == 7 else
                           f"2026-03-{10 + night:02d}T2{k // 30}:{k % 30:02d}:00Z"),
            wcs_json=WCS,
            accept=not set_aside,
            reject_reason=(["auto:grade:fwhm_px", "qc_error:boom", "user"][i % 3]
                           if set_aside else None),
            fwhm_px=None if i % 11 == 0 else 2.4 + (night % 5) * 0.2 + (i % 7) * 0.05,
            exposure_s=10.0 if i % 3 else 30.0,
            gain=80.0,
        ))
    proj.add_frames(rows)
    yield proj
    proj.close()


@pytest.mark.parametrize("accepted_only", [True, False])
def test_it_is_what_reading_the_rows_would_have_given(nightly_project,
                                                      accepted_only):
    """The equivalence claim, field by field and in order."""
    rows = list(nightly_project.iter_frames(accepted_only=accepted_only))
    nights = list(nightly_project.iter_night_frames(accepted_only=accepted_only))
    assert len(nights) == len(rows) > 0
    for want, got in zip(rows, nights, strict=True):
        for name, read in FIELDS.items():
            assert read(got) == read(want), f"{name} differs on {want.source_path}"


def test_every_field_of_the_record_is_compared_above(nightly_project):
    """The equivalence test is only worth what its field list covers, and a
    field added to the record without a line in `FIELDS` would be read by nobody
    — including by the test that exists to catch it being read wrongly."""
    assert set(FIELDS) == set(FrameNight.__dataclass_fields__)
    assert set(FIELDS) == set(_NIGHT_COLUMNS)


def test_the_records_come_back_in_id_order(nightly_project):
    """`iter_frames`' own order, kept deliberately: the callers cut the stream
    into sessions and take medians, and a median is one member of the set chosen
    by position."""
    got = [(f.timestamp_utc, f.fwhm_px) for f in nightly_project.iter_night_frames()]
    assert got == [(f.timestamp_utc, f.fwhm_px)
                   for f in nightly_project.iter_frames()]


def test_reading_them_builds_no_frame_objects(nightly_project, monkeypatch):
    """The claim the four surfaces are for. Fail-before: each built a `FrameRow`
    per sub — 35,894 of them on the owner's deepest target — to read five small
    fields."""
    import seestack.io.project as project_module

    built = 0
    real = project_module._row_to_frame

    def counting(row):
        nonlocal built
        built += 1
        return real(row)

    monkeypatch.setattr(project_module, "_row_to_frame", counting)
    got = list(nightly_project.iter_night_frames())
    assert got and built == 0, f"built {built} FrameRow objects"


def test_holding_the_whole_target_costs_a_fraction_of_holding_the_rows(tmp_path):
    """The memory claim in its own right, measured rather than reasoned.

    The plate solution is not skipped by the SQL — it simply is not selected —
    so what this pins is the retained set, against the row read on the same
    frames, which is the comparison the four surfaces actually made.
    """
    import tracemalloc

    n = 1000
    proj = Project.create(tmp_path / "deep", "D")
    try:
        proj.add_frames([
            FrameRow(source_path=f"/incoming/D/sub_{i:04d}.fit", wcs_json=WCS,
                     timestamp_utc=f"2026-03-01T2{i // 1000}:00:00Z",
                     fwhm_px=3.0, exposure_s=10.0, gain=80.0)
            for i in range(n)])

        def peak_of(read):
            tracemalloc.start()
            got = read()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert len(got) == n
            return peak

        rows = peak_of(lambda: list(proj.iter_frames()))
        nights = peak_of(lambda: list(proj.iter_night_frames()))

        # A quarter is a deliberately wide bar: the point is the order of the
        # cost, not a byte count that would drift with a field.
        assert nights < rows / 4, (
            f"{n} night records peaked at {nights / 1024:.0f} KiB against "
            f"{rows / 1024:.0f} KiB for the same frames as rows")
    finally:
        proj.close()


def test_an_empty_target_answers_empty_rather_than_raising(tmp_path):
    """A freshly created target has no frames, and the Dashboard's card reaches
    every target in the library before anything has been ingested."""
    proj = Project.create(tmp_path / "empty", "E")
    try:
        assert list(proj.iter_night_frames()) == []
    finally:
        proj.close()
