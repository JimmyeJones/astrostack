"""Hold a target whose drop folder is still copying: the arrival re-look.

Every guard on the walk-away path counts frames the library has **already
ingested**, and the scan's own ``TargetScanResult.n_frames_found`` is what the
walk *saw* — so nothing between the walk and the stack re-asked how many files
the folder now holds. A drop folder caught mid-copy therefore read as a
complete, settled target all the way down, and the owner's ``C_9`` was published
**and auto-edited from 6 of its 742 subs** (observer issue #1090), then
re-stacked from 609 seventy minutes later.

``_auto_stack_settle_hold`` is the obvious place to expect this and cannot cover
it, which the observer measured rather than assumed: that folder's copy finished
**35.9 min** before its stack started, because the job spent 39 min stacking the
other target first, so the 20-minute window had honestly expired. Every test
here therefore ages the subs well past the settle window — the settle hold is
*silent* in all of them, and the arrival hold is the only thing that can speak.

The discipline is the other three holds': no attempt marker, so the next scan
ingests the rest and stacks it once, on the whole folder. Delayed, never
stranded — and ``AUTO_STACK_ARRIVAL_META_KEY`` is what makes "never stranded"
structural rather than a hope.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from seestack.io.library import Library
from webapp import pipeline
from webapp.config import Settings

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synth import write_seestar_fits  # noqa: E402
from webapp.jobs import Job  # noqa: E402

FRAME_W, FRAME_H = 480, 320


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root) -> Settings:
    """Auto-stack only: the extra files the tests drop into ``incoming/`` must
    stay *un*-ingested, which is the whole state under test (the walk that saw
    them has not happened yet)."""
    return Settings(
        data_root=str(root), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True,
    )


def _patch_run_stack(monkeypatch):
    calls: list[str] = []

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        calls.append(getattr(proj, "name", "?"))
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=3, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    return calls


def _settle_the_night(lib: Library, seconds: float = 6 * 3600) -> None:
    """Put every sub well outside the settle window, on both stored times and the
    file — so :func:`_auto_stack_settle_hold` returns ``None`` everywhere and
    cannot be mistaken for the guard under test. This is the owner's measured
    situation: the copy had finished 35.9 min before the stack began."""
    when = time.time() - seconds
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            proj._conn.execute(  # noqa: SLF001 — reaching for the stored fact
                "UPDATE frames SET source_mtime = ?, ingested_at = ?", (when, when))
            proj._conn.commit()  # noqa: SLF001
            for row in proj.iter_frames():
                if row.source_path and os.path.exists(row.source_path):
                    os.utime(row.source_path, (when, when))
        finally:
            proj.close()


def _still_copying(incoming: Path, folder: str, n: int) -> None:
    """Land ``n`` more FITS files in a drop folder the library has rows in,
    without ingesting them — a folder mid-copy, exactly as the scan's walk left
    it. Create-new only: nothing existing is touched (AGENTS.md §10)."""
    d = incoming / folder
    for i in range(n):
        write_seestar_fits(
            d / f"arriving_{i:03d}.fit", width=FRAME_W, height=FRAME_H,
            n_stars=30, seed=900 + i, add_wcs=True,
            ra_center_deg=83.6, dec_center_deg=-5.0,
        )


def _prefix(root) -> str:
    return os.path.join(str(Settings(data_root=str(root)).resolved_incoming_dir), "")


# --- the incident ------------------------------------------------------------


def test_a_target_whose_folder_is_still_copying_is_not_published_from_a_fraction(
        solved_library, monkeypatch):
    """**Fails before:** ``M_42`` has 3 ingested subs and 20 more sitting in its
    own drop folder with no library row, and the walk-away chain stacked — and
    would have auto-edited — the 3. That is the owner's 6-of-742 incident at
    fixture scale, and no guard on `main` says a word about it."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _settle_the_night(lib)
        _still_copying(solved_library / "incoming", "M_42", 20)

        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)

        # The mid-copy target is held; its settled sibling still stacks, so the
        # guard is about *this* folder and not a blanket pause.
        assert summary["auto_stacked"] == ["NGC_7000"], summary["auto_stacked"]
        assert len(calls) == 1, calls

        held = summary.get("auto_stack_held_settling")
        assert held, "expected the mid-copy target to be held"
        mine = [h for h in held if h["target"] == "M_42"]
        assert len(mine) == 1, held
        assert mine[0]["waiting"] == 20
        assert mine[0]["on_disk"] == 23          # 3 ingested + 20 still arriving
        # The settle window is silent here — the subs are hours old — so this is
        # the arrival re-look speaking and nothing else.
        assert "quiet_min" not in mine[0], mine[0]

        # Held, not stamped: nothing about this target has been decided, so the
        # next scan re-checks it — the same discipline as the other three holds.
        proj = lib.open_target("M_42")
        try:
            assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
        finally:
            proj.close()
    finally:
        lib.close()


def test_once_the_folder_is_fully_imported_the_next_scan_stacks_it(
        solved_library, monkeypatch):
    """Delayed, never skipped: the hold is released by the files arriving, which
    is what the next scan's ingest does. Simulated by removing the un-ingested
    files — the folder and the library agree again."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _settle_the_night(lib)
        _still_copying(solved_library / "incoming", "M_42", 20)
        first = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert "M_42" not in first["auto_stacked"], first["auto_stacked"]

        for f in (solved_library / "incoming" / "M_42").glob("arriving_*.fit"):
            f.unlink()
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)

        assert "M_42" in summary["auto_stacked"], summary["auto_stacked"]
        assert not summary.get("auto_stack_held_settling")
        assert len(calls) == 2, calls          # the sibling once, then M_42
    finally:
        lib.close()


# --- it must never strand a target ------------------------------------------


def test_a_file_that_can_never_be_imported_costs_one_poll_not_the_target(
        solved_library, monkeypatch):
    """The trap the fix spec names, and the reason for the marker. A folder
    holding a file no scan can **ever** import — an unreadable header; the
    owner's library has ~147 such rows (issue #880) — makes an unbounded count
    comparison hold for ever, which would silently switch auto-stack off for that
    target. One observed on-disk shape buys one hold, so the cost is a single
    extra poll and the target always stacks."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _settle_the_night(lib)
        _still_copying(solved_library / "incoming", "M_42", 2)

        # Poll one: the shape is new, so the benefit of the doubt goes to "still
        # copying" — which is the right answer the overwhelming majority of the
        # time.
        first = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert "M_42" not in first["auto_stacked"], first["auto_stacked"]

        # Poll two: the folder has not moved, so nothing is arriving into it and
        # the target stacks — without the files ever becoming importable.
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert "M_42" in summary["auto_stacked"], summary["auto_stacked"]
        assert len(calls) == 2, calls
    finally:
        lib.close()


def test_a_file_the_scan_already_failed_to_read_does_not_cost_even_one_poll(
        solved_library, monkeypatch):
    """Step (4) of the spec, and why the bound is *evidence* rather than a timer:
    what the last whole-library scan opened and could not read is subtracted
    before anything is held. On the owner's five such folders the hold is
    therefore completely silent — not even the one poll above."""
    from webapp.unreadablesubs import remember_unreadable

    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _settle_the_night(lib)
        _still_copying(solved_library / "incoming", "M_42", 4)
        remember_unreadable(lib, {"M_42": 4})

        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert "M_42" in summary["auto_stacked"], summary["auto_stacked"]
        assert not summary.get("auto_stack_held_settling")
    finally:
        lib.close()


# --- the hold in isolation ---------------------------------------------------


def test_a_nested_calibration_folder_is_not_counted_as_missing_lights(
        solved_library):
    """Non-recursive, deliberately: the Calibration page's ``MAX_DEPTH = 2``
    invites darks one directory down (``M_42/Darks/``), and a recursive count
    would read them as this target's own subs still copying in — holding the
    target for ever on files that are not its lights at all."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        darks = solved_library / "incoming" / "M_42" / "Darks"
        darks.mkdir(parents=True, exist_ok=True)
        for i in range(8):
            write_seestar_fits(
                darks / f"dark_{i:03d}.fit", width=FRAME_W, height=FRAME_H,
                n_stars=0, seed=500 + i)
        prefix = _prefix(solved_library)
        state = pipeline._incoming_import_state(lib, prefix)
        assert pipeline._auto_stack_arrival_hold(
            lib, "M_42", prefix, state) is None
    finally:
        lib.close()


def test_a_drop_folder_that_has_gone_away_holds_nothing(solved_library):
    """A share that unmounted or a folder that was archived says nothing about
    what is still arriving, and "0 files on disk" must never read as "742
    waiting". The readability hold is the guard for files that have *left*."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        prefix = _prefix(solved_library)
        state = pipeline._incoming_import_state(lib, prefix)
        for p in (solved_library / "incoming" / "M_42").glob("*.fit"):
            p.unlink()
        (solved_library / "incoming" / "M_42").rmdir()
        assert pipeline._auto_stack_arrival_hold(
            lib, "M_42", prefix, state) is None
    finally:
        lib.close()


def test_no_import_tally_means_no_hold(solved_library):
    """The safe failure, and its direction is the point: an *absent* import tally
    would make every folder read as entirely unimported, so a swallowed error
    must hold nothing rather than pause the whole library."""
    lib = Library.open_or_create(solved_library / "library")
    try:
        _still_copying(solved_library / "incoming", "M_42", 20)
        assert pipeline._auto_stack_arrival_hold(
            lib, "M_42", _prefix(solved_library), None) is None
    finally:
        lib.close()


def test_a_folder_two_targets_share_is_counted_by_distinct_subs(
        solved_library, monkeypatch):
    """Why the tally is the library-wide **distinct** one and never this target's
    own row count: 76 % of the owner's frames are registered in *two* targets
    each (issue #878's mosaic double-registration). Counted per target, a shared
    folder reads as half-imported on each of them and holds both for ever."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _settle_the_night(lib)
        # Register M_42's three subs in NGC_7000 as well, by the same row copy
        # the mosaic path uses, which is the shape issue #878 describes. Nothing
        # new lands on disk, so nothing is genuinely waiting.
        from seestack.io.merge import _frame_without_id

        src = lib.open_target("M_42")
        try:
            rows = list(src.iter_frames())
        finally:
            src.close()
        dest = lib.open_target("NGC_7000")
        try:
            for row in rows:
                dest.add_frame(_frame_without_id(row))
        finally:
            dest.close()

        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert not summary.get("auto_stack_held_settling"), summary
        assert "M_42" in summary["auto_stacked"], summary["auto_stacked"]
    finally:
        lib.close()
