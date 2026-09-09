"""``Project.source_folders_under`` — which folder under ``incoming/`` a target's
subs actually came from.

The upload form needs this to offer a destination, and it has to be answered
from the ``frames`` rows alone: ``incoming/`` is the owner's only copy of every
sub and is strictly read-only (AGENTS.md §10), so nothing here may walk, open or
``stat`` it. The folder name and the *target* name are also not interchangeable
(``M 31_sub/`` → *M 31*), which is exactly why the folder has to be read rather
than reconstructed from the name.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from seestack.io.project import FrameRow, Project

PREFIX = os.path.join(os.sep + os.path.join("data", "incoming"), "")


@pytest.fixture
def proj(tmp_path: Path):
    p = Project.create(tmp_path / "t", "M 31")
    yield p
    p.close()


def _add(p: Project, *rel: str) -> None:
    p.add_frames([FrameRow(source_path=PREFIX + r.replace("/", os.sep))
                  for r in rel])


def test_the_folder_a_targets_subs_came_from_is_reported_with_its_count(proj):
    _add(proj, "M 31_sub/Light_1.fit", "M 31_sub/Light_2.fit",
         "M 31_sub/Light_3.fit")
    assert proj.source_folders_under(PREFIX) == [("M 31_sub", 3)]


def test_folders_come_back_busiest_first(proj):
    _add(proj, "A_sub/1.fit", "B_sub/1.fit", "B_sub/2.fit")
    assert proj.source_folders_under(PREFIX) == [("B_sub", 2), ("A_sub", 1)]


def test_a_sub_loose_in_incoming_reports_the_empty_folder(proj):
    """The scanner's ``Unsorted`` catch-all. Reported as ``""`` rather than
    dropped, so a caller can tell "loose in incoming" from "no rows at all"."""
    _add(proj, "stray.fit", "M 31_sub/1.fit")
    # Ties break on the folder name, so the empty one sorts first here.
    assert proj.source_folders_under(PREFIX) == [("", 1), ("M 31_sub", 1)]


def test_a_nested_drop_reports_the_whole_relative_folder(proj):
    """``incoming/MyWorks/M 31_sub/`` — the whole-device container shape. It must
    NOT collapse to ``MyWorks``: the upload endpoint writes one folder level, so
    a first-component answer would look exactly like a folder you *could* upload
    into, and offering it would land the subs a level above their own target."""
    _add(proj, "MyWorks/M 31_sub/1.fit", "MyWorks/M 31_sub/2.fit")
    assert proj.source_folders_under(PREFIX) == [
        (os.path.join("MyWorks", "M 31_sub"), 2)]


def test_a_sibling_directory_sharing_the_prefixs_first_characters_does_not_match(proj):
    """``incoming2/`` must not read as ``incoming/`` — the trailing separator in
    the prefix is what stops it, the same guard ``source_frames_under`` carries."""
    _add(proj, "M 31_sub/1.fit")
    proj.add_frames([FrameRow(
        source_path=os.sep + os.path.join("data", "incoming2", "M 31_sub", "9.fit"))])
    assert proj.source_folders_under(PREFIX) == [("M 31_sub", 1)]


def test_a_target_with_no_frames_under_the_prefix_reports_nothing(proj):
    proj.add_frames([FrameRow(
        source_path=os.sep + os.path.join("elsewhere", "x.fit"))])
    assert proj.source_folders_under(PREFIX) == []


def test_it_never_touches_the_folder_it_reports_on(proj, monkeypatch):
    """AGENTS.md §10: ``incoming/`` is read-only and holds the only copy of the
    owner's subs, so the honest way to report on it is not to touch it. Arm the
    trap *and prove it is armed* before trusting the silence."""
    _add(proj, "M 31_sub/1.fit")

    def boom(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("source_folders_under touched the filesystem")

    monkeypatch.setattr(os, "scandir", boom)
    monkeypatch.setattr(os, "listdir", boom)
    monkeypatch.setattr(os, "stat", boom)
    with pytest.raises(AssertionError):
        os.stat(".")           # the trap is real, not a no-op
    assert proj.source_folders_under(PREFIX) == [("M 31_sub", 1)]
