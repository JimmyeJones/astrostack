"""The row counter the "reads columns, not whole rows" tests are built on.

Its whole job is to be *attributable*: ``_row_to_frame`` is a module global, so
a patch of it sees every thread in the process, and a webapp test shares its
process with a ``job-worker`` an earlier test left running. See
``tests/framerows.py`` for the incident this comes from.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from framerows import frame_rows_built_by  # noqa: E402

from seestack.io.project import FrameRow, Project  # noqa: E402


def _project_with_frames(project_dir, n: int = 3) -> Project:
    proj = Project.create(project_dir, name=project_dir.name)
    for i in range(n):
        proj.add_frame(FrameRow(source_path=f"/x/{i}.fit", accept=True))
    return proj


def _read_whole_rows(proj: Project) -> int:
    """A stand-in for a surface that reads whole rows — the thing under test."""
    return len(list(proj.iter_frames()))


def _read_one_column(proj: Project) -> int:
    """…and one that reads a column, which is what the real fixes do."""
    return len(list(proj.iter_health_frames()))


def test_rows_built_under_the_named_call_are_counted(tmp_path):
    proj = _project_with_frames(tmp_path / "t")
    try:
        with frame_rows_built_by(_read_whole_rows) as built:
            assert _read_whole_rows(proj) == 3
        assert built() == 3
    finally:
        proj.close()


def test_a_column_read_under_the_same_call_counts_nothing(tmp_path):
    proj = _project_with_frames(tmp_path / "t")
    try:
        with frame_rows_built_by(_read_one_column) as built:
            assert _read_one_column(proj) == 3
        assert built() == 0
    finally:
        proj.close()


def test_a_row_built_on_another_thread_is_not_this_calls_row(tmp_path):
    """The regression: a leftover ``job-worker`` building rows against another
    library, while the call under test reads only columns, used to be counted as
    the call's own — which is how CI run 2294 failed on an innocent read.
    """
    proj = _project_with_frames(tmp_path / "t")
    _project_with_frames(tmp_path / "other", n=2).close()
    stray_rows: list[int] = []
    try:
        with frame_rows_built_by(_read_one_column) as built:
            def interloper() -> None:
                # Deliberately *not* under the call being measured — a whole-row
                # read on a thread of its own, against another library, exactly
                # as the leaked worker does. The connection is opened *here*:
                # sqlite3 refuses one made on another thread, and a stray row
                # that never got built would make this test prove nothing.
                other = Project.open(tmp_path / "other")
                try:
                    stray_rows.append(_read_whole_rows(other))
                finally:
                    other.close()

            t = threading.Thread(target=interloper, name="job-worker")
            t.start()
            t.join(timeout=30)
            assert not t.is_alive()
            assert _read_one_column(proj) == 3
        assert stray_rows == [2], "the interloper must really have built rows"
        assert built() == 0
    finally:
        proj.close()


def test_naming_no_call_is_refused_rather_than_counting_everything(tmp_path):
    """A counter with no anchor would count the whole process, which is the bug
    this module exists to remove — so it is an error, not a default."""
    import pytest

    with pytest.raises(ValueError), frame_rows_built_by():
        pass


def test_the_seam_is_restored_even_when_the_block_raises(tmp_path):
    import seestack.io.project as project_module

    before = project_module._row_to_frame
    try:
        with frame_rows_built_by(_read_whole_rows):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert project_module._row_to_frame is before
