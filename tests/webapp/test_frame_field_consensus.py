"""The library-wide "which telescope?" answer is a consensus, not the first hit.

`webapp.frame_field.library_frame_field` feeds every catalogue row the Tonight
planner and the week plan badge — "will it fit in one frame?", "how many mosaic
panels?" — and `install_frame_field` keeps its answer for the life of the
process. It used to be the field of *whichever target the walk reached first*,
guarded only by `frame_field_from_solve`'s very wide 3'-1200' sanity band, which
a plate scale wrong by 2x passes untouched. The owner's own library carries 178
rows with an implausible solve (observer issue #965), so that was a real path
from one bad solve to a wrong number on every planner row until a restart.

`Project.solved_frame_geometry` already medians the newest 25 solves *within* a
target (v0.488.5); these tests pin the same idea *across* targets, and pin the
two places it deliberately does not move: fewer than three answers, and the
number of SQLite opens the probe pays.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from seestack.framing import FrameField
from seestack.io.library import Library
from seestack.io.project import FrameRow
from webapp.frame_field import (
    _FIELD_CONSENSUS_TARGETS,
    consensus_field,
    library_frame_field,
)

# 480 x 320 px, as the webapp fixtures use, at a scale that gives a plausible
# small-refractor field: 107.7' x 71.8'.
_W, _H = 480, 320
_GOOD_SCALE = 71.8 * 60.0 / _H
# The failure this is about: a solve wrong by 2x. 215' is still inside
# ``frame_field_from_solve``'s sanity band, which is the whole point.
_WRONG_SCALE = _GOOD_SCALE * 2.0


def _target_with_scale(lib: Library, name: str, scale: float,
                       *, n_frames: int = 30) -> None:
    """Add ``name`` to ``lib`` with ``n_frames`` solved frames at ``scale``.

    Thirty frames so the per-target median (the newest 25) is decided by this
    scale alone and never by a short sample.
    """
    entry, proj = lib.create_target(name)
    try:
        proj.add_frames([
            FrameRow(
                source_path=f"/incoming/{name}/frame_{i:03d}.fit",
                wcs_json="SIMPLE = T",
                pixscale_arcsec=scale, width_px=_W, height_px=_H,
            )
            for i in range(n_frames)
        ])
    finally:
        proj.close()
    lib.refresh_target_stats(entry.safe_name)


def _set_activity_order(root: Path, newest_first: list[str]) -> None:
    """Stamp ``last_activity_utc`` so the probe walks these targets in order.

    ``refresh_target_stats`` stamps "now" to the second, so a library built inside
    one test has ties the probe's sort cannot break. Written straight into the
    registry because that is the column the probe reads, and the state is one a
    real library reaches by being shot over several nights.
    """
    con = sqlite3.connect(root / "library" / "library.sqlite")
    try:
        for i, name in enumerate(newest_first):
            con.execute(
                "UPDATE targets SET last_activity_utc = ? WHERE name = ?",
                (f"2026-09-{28 - i:02d}T22:00:00Z", name),
            )
        con.commit()
    finally:
        con.close()


@pytest.fixture
def five_target_library(tmp_path: Path):
    """A library whose **newest** target carries a solve wrong by 2x."""
    root = tmp_path / "data"
    lib = Library.open_or_create(root / "library")
    try:
        _target_with_scale(lib, "Bad Newest", _WRONG_SCALE)
        for i in range(4):
            _target_with_scale(lib, f"Good {i}", _GOOD_SCALE)
    finally:
        lib.close()
    _set_activity_order(
        root, ["Bad Newest", "Good 0", "Good 1", "Good 2", "Good 3"],
    )
    return root


def test_one_wrong_solve_no_longer_decides_the_whole_librarys_field(
        five_target_library):
    """The regression: four targets agree, the newest does not, and the newest
    used to win because the walk stopped at it."""
    lib = Library.open_or_create(five_target_library / "library")
    try:
        field = library_frame_field(lib)
    finally:
        lib.close()
    assert field is not None
    assert field.long_arcmin == pytest.approx(107.7, abs=0.1)
    assert field.short_arcmin == pytest.approx(71.8, abs=0.1)


def test_two_answers_still_keep_the_newest_targets_field(tmp_path: Path):
    """Nothing moves below three answers — a pair cannot outvote anything, and
    preferring one of two arbitrarily would be a behaviour change for nothing."""
    root = tmp_path / "data"
    lib = Library.open_or_create(root / "library")
    try:
        _target_with_scale(lib, "Newest", _WRONG_SCALE)
        _target_with_scale(lib, "Older", _GOOD_SCALE)
    finally:
        lib.close()
    _set_activity_order(root, ["Newest", "Older"])

    lib = Library.open_or_create(root / "library")
    try:
        field = library_frame_field(lib)
    finally:
        lib.close()
    assert field is not None
    assert field.long_arcmin == pytest.approx(215.4, abs=0.2)


def test_the_probe_stops_as_soon_as_enough_targets_have_answered(
        tmp_path: Path, monkeypatch):
    """The cost pin. The walk's ceiling is unchanged (eight opens when nothing
    answers), and a library where every target answers pays five, not eight."""
    root = tmp_path / "data"
    names = [f"T {i}" for i in range(8)]
    lib = Library.open_or_create(root / "library")
    try:
        for name in names:
            _target_with_scale(lib, name, _GOOD_SCALE, n_frames=3)
    finally:
        lib.close()
    _set_activity_order(root, names)

    opened: list[str] = []
    import webapp.frame_field as ff

    real = ff._field_from_target

    def counting(lib_, entry):  # noqa: ANN001, ANN202
        opened.append(entry.safe_name)
        return real(lib_, entry)

    monkeypatch.setattr(ff, "_field_from_target", counting)

    lib = Library.open_or_create(root / "library")
    try:
        assert library_frame_field(lib) is not None
    finally:
        lib.close()
    assert len(opened) == _FIELD_CONSENSUS_TARGETS


def test_the_consensus_is_one_probed_targets_own_field_never_an_average():
    """A long edge from one telescope beside a short edge from another describes
    a frame neither had, so the answer is always an element of the input."""
    fields = [
        FrameField(100.0, 50.0),
        FrameField(108.0, 72.0),
        FrameField(110.0, 70.0),
    ]
    agreed = consensus_field(fields)
    assert agreed in fields
    assert agreed == FrameField(108.0, 72.0)


def test_no_answers_stays_none_and_one_answer_is_itself():
    """The two ends: an unsolved library keeps the module default (``None``), and
    a single answer is not second-guessed."""
    assert consensus_field([]) is None
    only = FrameField(90.0, 60.0)
    assert consensus_field([only]) is only
