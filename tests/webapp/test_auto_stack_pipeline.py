"""Auto-stack pipeline pass: fires for eligible targets, non-fatal, idempotent."""

from __future__ import annotations

from types import SimpleNamespace

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root) -> Settings:
    # Only auto_stack on, so the run goes straight to the auto-stack pass.
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


def test_auto_stack_runs_for_solved_targets(solved_library, monkeypatch):
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        job = Job(kind="pipeline")
        summary = pipeline._pipeline_body(_settings(solved_library), _FakeJM(), job, root=None)
    finally:
        lib.close()
    # Every solved target with no prior stack should have been stacked.
    assert len(calls) >= 1
    assert summary["auto_stacked"]
    assert not summary.get("stack_errors")


def _first_stackable(lib) -> str | None:
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            if pipeline._solved_accepted_count(proj) > 0:
                return entry.safe_name
        finally:
            proj.close()
    return None


def _capture_opts(monkeypatch):
    captured: dict = {}

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        captured["opts"] = opts
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=3, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
            n_offered=3, n_align_failed=0,
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    return captured


def test_walk_away_stack_turns_on_auto_reject(solved_library, monkeypatch):
    # A walk-away stack (watcher / Process target) where the user made no rejection
    # choice should hand the engine ``auto_reject=True`` so a small stack gets
    # order-statistic min/max — the only method that removes a lone satellite/plane
    # trail below the ~11-frame κ-σ threshold — with zero user decisions.
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        pipeline._stack_target(
            _settings(solved_library), _FakeJM(), Job(kind="stack"), lib, safe,
            auto=True)
    finally:
        lib.close()
    assert captured["opts"].auto_reject is True


def test_manual_stack_leaves_auto_reject_off(solved_library, monkeypatch):
    # The manual Stack form (auto=False, explicit options) must be honoured verbatim:
    # no auto_reject is injected, so the engine runs the default κ-σ path unchanged.
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        pipeline._stack_target(
            _settings(solved_library), _FakeJM(), Job(kind="stack"), lib, safe,
            options={})
    finally:
        lib.close()
    assert captured["opts"].auto_reject is False
    assert captured["opts"].sigma_clip is True


def test_walk_away_respects_an_explicit_saved_rejection_default(solved_library, monkeypatch):
    # If the user saved a per-target default with an explicit rejection method, the
    # walk-away path must respect it and NOT override with auto_reject.
    import json

    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            proj.set_meta(
                pipeline.STACK_DEFAULTS_META_KEY,
                json.dumps({"min_max_reject": True, "sigma_clip": False}),
            )
        finally:
            proj.close()
        pipeline._stack_target(
            _settings(solved_library), _FakeJM(), Job(kind="stack"), lib, safe,
            auto=True)
    finally:
        lib.close()
    assert captured["opts"].auto_reject is False
    assert captured["opts"].min_max_reject is True
    assert captured["opts"].sigma_clip is False


def test_auto_stack_skips_already_stacked(solved_library, monkeypatch):
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        # Give every target a recent stack run covering all its solved frames.
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                n = sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=n,
                    canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=n,
                    options_json="{}",
                ))
            finally:
                proj.close()
        job = Job(kind="pipeline")
        summary = pipeline._pipeline_body(_settings(solved_library), _FakeJM(), job, root=None)
    finally:
        lib.close()
    assert calls == []                       # nothing new to stack
    assert summary["auto_stacked"] == []
    assert summary["auto_stack_skipped"]


def test_stack_marks_solved_count_so_watcher_skips_align_dropped_target(
    solved_library, monkeypatch,
):
    # Regression: a *manual* stack (Stack form / Process target / reprocess) that
    # legitimately drops some subs at alignment records n_frames_used < the number
    # of solved+accepted subs. The watcher's "already stacked?" guard compared the
    # current solved+accepted count to that align-reduced n_frames_used, so it read
    # the gap as "new work" and re-stacked the target once on the next scan — a
    # surprise duplicate run + a full expensive stack on the walk-away path, even
    # though nothing new arrived. _stack_target now stamps the solved+accepted count
    # it covered, so the watcher correctly skips the unchanged target.
    lib = Library.open_or_create(solved_library / "library")
    try:
        settings = _settings(solved_library)
        job = Job(kind="stack")
        checked = 0
        for entry in lib.list_targets():
            safe = entry.safe_name
            proj = lib.open_target(safe)
            try:
                n = pipeline._solved_accepted_count(proj)
            finally:
                proj.close()
            if n == 0:
                continue
            checked += 1
            # A manual stack that dropped one sub at alignment: it records a run
            # whose n_frames_used is n-1, and writes no crash-loop marker of its own.
            def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                               memory_budget_gb=None, app_version=None, _n=n):  # noqa: ANN001
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=_n - 1,
                    canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=_n - 1,
                    options_json="{}",
                ))
                return SimpleNamespace(
                    output_dir="/tmp/x", run_id=1, n_frames_used=_n - 1,
                    canvas_shape=(10, 10, 3), cancelled=False, errors=[],
                    excluded_frames=[], n_offered=_n, n_align_failed=1,
                )

            monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
            pipeline._stack_target(settings, _FakeJM(), job, lib, safe)
            # The watcher must now treat this target as fully stacked, not re-stack
            # it (before the fix this returned n — a redundant re-stack).
            assert pipeline._auto_stack_frame_count(lib, safe) is None
        assert checked >= 1
    finally:
        lib.close()


def test_auto_stack_fallback_ignores_a_small_channel_combine_run(solved_library):
    # Regression: the "already stacked?" fallback used the *newest* stack run's
    # n_frames_used. A channel-combine (or editor-export) run records a tiny count
    # (a couple of source stacks), is not a genuine full stack, and does not write
    # the AUTO_STACK_ATTEMPT_META_KEY marker. So on pre-marker/upgrade data whose
    # newest run is such a small-count run, the guard compared the target's full
    # solved+accepted count against that tiny count and wrongly re-stacked unchanged
    # data. The fallback now compares against the largest coverage any prior run
    # reached, so a small channel-combine on top of a genuine full stack no longer
    # lowers the bar.
    lib = Library.open_or_create(solved_library / "library")
    try:
        checked = 0
        for entry in lib.list_targets():
            safe = entry.safe_name
            proj = lib.open_target(safe)
            try:
                n = pipeline._solved_accepted_count(proj)
                if n == 0:
                    continue
                # A genuine full stack covering every solved+accepted sub…
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=n,
                    canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=n,
                    options_json="{}",
                ))
                # …then a *newer* small-count channel-combine run (no marker), the
                # exact pre-marker/upgrade shape that tripped the old fallback.
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-02T00:00:00Z",
                    output_basename="rgb", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=2,
                    canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=2,
                    options_json="{}", notes="channel combine",
                ))
            finally:
                proj.close()
            checked += 1
            # No new solved+accepted frames arrived, so nothing to re-stack.
            # (Before the fix: 2 < n → returned n → a redundant full re-stack.)
            assert pipeline._auto_stack_frame_count(lib, safe) is None
        assert checked >= 1
    finally:
        lib.close()


def test_auto_stack_failure_is_non_fatal(solved_library, monkeypatch):
    def boom(proj, opts, *, progress=None, cancel=None,
             memory_budget_gb=None, app_version=None):  # noqa: ANN001
        raise ValueError("No accepted frames are plate-solved yet")

    monkeypatch.setattr("seestack.stack.stacker.run_stack", boom)
    lib = Library.open_or_create(solved_library / "library")
    try:
        job = Job(kind="pipeline")
        # Must NOT raise — the pipeline records the error and carries on.
        summary = pipeline._pipeline_body(_settings(solved_library), _FakeJM(), job, root=None)
    finally:
        lib.close()
    assert summary["stack_errors"]
    assert summary["auto_stacked"] == []


def test_auto_stack_process_crash_marker_prevents_reloop(solved_library):
    # The genuine crash-loop guard: a stack that kills the *whole process* (OOM
    # SIGKILL) can't run its cleanup, so the attempt marker is written *before*
    # the stack and survives in the DB. On restart the next scan must see that
    # persisted marker and skip the target — otherwise a process-crashing stack
    # plus the watcher re-trigger would loop forever. We assert the guard itself:
    # once the marker is at the current solved+accepted count, the frame-count
    # selector returns None (skip) for that unchanged data.
    lib = Library.open_or_create(solved_library / "library")
    try:
        checked = 0
        for entry in lib.list_targets():
            safe = entry.safe_name
            proj = lib.open_target(safe)
            try:
                count = pipeline._solved_accepted_count(proj)
            finally:
                proj.close()
            if count == 0:
                continue
            checked += 1
            # Marker persisted by the pre-stack mark (what a real crash leaves).
            pipeline._mark_auto_stack_attempt(lib, safe, count)
            assert pipeline._auto_stack_frame_count(lib, safe) is None
        assert checked >= 1
    finally:
        lib.close()


def test_auto_stack_clears_marker_when_cancelled(solved_library, monkeypatch):
    # A user cancel mid-stack is a survivable, non-crash outcome: run_stack returns
    # cancelled=True with no run recorded and raises nothing, so it never reaches
    # the except handler. The pre-stack crash-loop marker must still be cleared —
    # otherwise the cancelled target is stranded (skipped on every future scan until
    # brand-new frames arrive) — and a cancelled stack must not be reported as
    # stacked. (Contrast the process-crash case, which keeps its marker.)
    calls: list[str] = []

    def run_pipeline():
        lib = Library.open_or_create(solved_library / "library")
        try:
            job = Job(kind="pipeline")

            def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                               memory_budget_gb=None, app_version=None):  # noqa: ANN001
                calls.append(getattr(proj, "name", "?"))
                job._cancel.set()  # the user cancels while this target is stacking
                return SimpleNamespace(
                    output_dir="/tmp/x", run_id=None, n_frames_used=0,
                    canvas_shape=(1, 1, 3), cancelled=True, errors=[],
                    excluded_frames=[],
                )

            monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
            return pipeline._pipeline_body(
                _settings(solved_library), _FakeJM(), job, root=None
            )
        finally:
            lib.close()

    summary = run_pipeline()
    assert len(calls) == 1                  # cancel breaks the loop after one target
    assert summary["auto_stacked"] == []    # a cancelled stack isn't "stacked"

    # No target may be left carrying the pre-stack crash-loop marker after a cancel:
    # before the fix the one attempted target kept its marker and was stranded.
    lib = Library.open_or_create(solved_library / "library")
    try:
        markers = []
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                markers.append(proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY))
            finally:
                proj.close()
    finally:
        lib.close()
    assert all(m is None for m in markers)


def test_auto_stack_retries_after_a_recoverable_failure(solved_library, monkeypatch):
    # A *recoverable* exception (transient I/O off a flapping mount, a momentary
    # lock) is caught — the process survives — so the pre-stack marker must be
    # cleared, letting the next scan retry instead of stranding the target's
    # auto-stack forever. (Contrast the process-crash case above, which never
    # reaches the handler and keeps its marker.)
    calls: list[str] = []

    def boom(proj, opts, *, progress=None, cancel=None,
             memory_budget_gb=None, app_version=None):  # noqa: ANN001
        calls.append(getattr(proj, "name", "?"))
        raise ValueError("simulated transient read error")

    monkeypatch.setattr("seestack.stack.stacker.run_stack", boom)

    def run_pipeline():
        lib = Library.open_or_create(solved_library / "library")
        try:
            return pipeline._pipeline_body(
                _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None
            )
        finally:
            lib.close()

    first = run_pipeline()
    attempted = len(calls)
    assert attempted >= 1            # tried each eligible target once
    assert first["stack_errors"]

    second = run_pipeline()          # same data, transient error → must RETRY
    assert len(calls) == 2 * attempted   # every eligible target tried again
    assert second["stack_errors"]
