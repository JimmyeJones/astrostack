"""``webapp.incominglag`` — the diff between what is on disk and what is in the
library, and the three rules that keep it from crying wolf."""

from __future__ import annotations

from seestack.io.scanner import PlannedUnit
from webapp.incominglag import LAG_MIN_AGE_S, incoming_lag

NOW = 1_700_000_000.0
LONG_AGO = NOW - 11 * 24 * 3600.0     # the observer's eleven days
JUST_NOW = NOW - 60.0


def _unit(folder: str, n: int, mtime: float = LONG_AGO,
          target: str = "") -> PlannedUnit:
    return PlannedUnit(target_name=target or folder, folder=folder,
                       n_files=n, newest_mtime=mtime)


def test_it_names_the_folder_and_counts_what_is_missing() -> None:
    (lag,) = incoming_lag([_unit("IC 360_sub", 2572, target="IC 360")],
                          {"IC 360_sub": 313}, NOW)

    assert (lag.folder, lag.target_name) == ("IC 360_sub", "IC 360")
    assert (lag.n_on_disk, lag.n_imported, lag.n_waiting) == (2572, 313, 2259)
    assert lag.still_hours == 264.0
    assert lag.newest_utc.endswith("+00:00")


def test_a_fully_imported_folder_says_nothing() -> None:
    assert incoming_lag([_unit("M 42_sub", 40)], {"M 42_sub": 40}, NOW) == []


def test_a_folder_still_being_written_is_not_behind() -> None:
    """A night arriving over SMB is *supposed* to be ahead of the library. The
    note waits for the folder to stop moving before it says anything."""
    assert incoming_lag([_unit("M 42_sub", 40, JUST_NOW)], {}, NOW) == []

    just_over = NOW - LAG_MIN_AGE_S - 1
    (lag,) = incoming_lag([_unit("M 42_sub", 40, just_over)], {}, NOW)
    assert lag.n_waiting == 40


def test_an_unknown_mtime_is_never_called_lag() -> None:
    """Silence is the safe answer when the evidence is missing — a listing with
    no usable mtime must not read as "sitting there since 1970"."""
    assert incoming_lag([_unit("M 42_sub", 40, 0.0)], {}, NOW) == []


def test_frames_registered_deeper_than_the_unit_folder_still_count() -> None:
    """A unit folder is scanned recursively, so a frame at
    ``M 42_sub/night2/x.fit`` is reported under the deeper folder. Summing by
    prefix is what stops a fully-imported target reading as never-imported."""
    assert incoming_lag(
        [_unit("M 42_sub", 40)],
        {"M 42_sub": 10, "M 42_sub/night2": 30}, NOW) == []


def test_a_sibling_folder_sharing_a_prefix_does_not_count() -> None:
    """``M 42_sub2`` starts with ``M 42_sub`` as a string but is a different
    folder — the roll-up is by path component, not by characters."""
    (lag,) = incoming_lag([_unit("M 42_sub", 40)],
                          {"M 42_sub2": 40}, NOW)
    assert lag.n_waiting == 40


def test_the_unsorted_root_unit_does_not_swallow_every_folder() -> None:
    """Loose files sit *directly* in the root, so the one unit whose folder is
    the empty string matches exactly — rolling every folder into it would make
    the whole library read as imported into ``Unsorted``."""
    assert incoming_lag([_unit("", 5, target="Unsorted")],
                        {"M 42_sub": 400}, NOW)[0].n_waiting == 5
    assert incoming_lag([_unit("", 5, target="Unsorted")],
                        {"": 5}, NOW) == []


def test_a_double_registered_folder_can_only_ever_read_as_imported() -> None:
    """Issue #878's mosaic double-registration means one folder's frames are
    counted under two targets, and the caller sums them. That can overshoot the
    files on disk — which must floor at "nothing waiting", never go negative."""
    assert incoming_lag([_unit("M 42_mosaic_sub", 100)],
                        {"M 42_mosaic_sub": 200}, NOW) == []


def test_the_worst_folder_is_first_and_the_order_is_stable() -> None:
    found = incoming_lag(
        [_unit("a_sub", 10), _unit("b_sub", 100), _unit("c_sub", 10)],
        {}, NOW)
    assert [f.folder for f in found] == ["b_sub", "a_sub", "c_sub"]
