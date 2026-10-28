"""Auto-stack pipeline pass: fires for eligible targets, non-fatal, idempotent."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from seestack.io.library import Library
from seestack.io.project import FrameRow, StackRunRow
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root) -> Settings:
    # Only auto_stack on, so the run goes straight to the auto-stack pass.
    # ``auto_stack_settle_min=0``: this fixture's subs were written seconds
    # ago, so the settle hold (v0.390.1) would legitimately hold every target
    # as "still being shot". These tests are about other things; the settle
    # window has its own tests in ``test_autostack_settle.py``.
    return Settings(
        data_root=str(root), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True, auto_stack_settle_min=0,
    )


def _patch_run_stack(monkeypatch):
    calls: list[str] = []

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None, **_kw):  # noqa: ANN001
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


def test_the_shipped_defaults_stack_a_target_with_nobody_watching(
        solved_library, monkeypatch):
    """v0.391.0: ``auto_stack`` is deliberately *not* named here.

    Every other test in this file turns it on by hand, so none of them could tell
    whether a fresh install actually walks the whole chain — which is the entire
    promise of "drop your subs in and come back to a picture". This one takes the
    flag off the shipped default and fails before the flip (the auto-stack pass is
    skipped, ``calls`` stays empty and ``auto_stacked`` is absent).

    The other three automation flags stay off because this fixture's frames are
    already ingested, QC'd and solved; the settle window is zeroed for the reason
    given in ``_settings`` above.
    """
    calls = _patch_run_stack(monkeypatch)
    settings = Settings(
        data_root=str(solved_library), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack_settle_min=0,
    )
    assert settings.auto_stack is True  # the shipped default, not set above
    job = Job(kind="pipeline")
    summary = pipeline._pipeline_body(settings, _FakeJM(), job, root=None)
    assert calls, "a fresh install did not stack anything"
    assert summary["auto_stacked"]
    assert not summary.get("stack_errors")


def _reject_down_to(lib, keep: int) -> None:
    """Reject frames in every target until only ``keep`` accepted+solved remain."""
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            solved = [f for f in proj.iter_frames() if f.accept and f.wcs_json]
            for f in solved[keep:]:
                proj.update_frame(f.id, accept=False,
                                  reject_reason="test:thin", user_override=True)
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)


def _reaccept_all(lib) -> None:
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            for f in proj.iter_frames():
                if not f.accept:
                    proj.update_frame(f.id, accept=True, reject_reason=None,
                                      user_override=True)
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)


def test_auto_stack_holds_back_a_thin_solved_target(solved_library, monkeypatch):
    """A walk-away auto-stack must NOT publish a 1-2 frame speckle "master".

    The owner-reported gibberish is a faint field where ASTAP solves ~1 sub, so
    the hands-off pipeline auto-stacks (and auto-edits) a single-frame result
    that is pure per-pixel colour noise. With the default ``auto_stack_min_frames``
    floor the target is held back instead — and stacked the moment enough subs
    solve. Fail-before: two solved frames were auto-stacked as a finished picture.
    """
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _reject_down_to(lib, keep=2)  # 2 accepted+solved per target < floor of 3
        # Default settings: auto_stack_min_frames == 3.
        job = Job(kind="pipeline")
        summary = pipeline._pipeline_body(_settings(solved_library), _FakeJM(), job, root=None)
        # Nothing was stacked — every eligible target was held back as thin.
        assert calls == []
        assert summary["auto_stacked"] == []
        held = summary.get("auto_stack_held_thin")
        assert held, "expected the thin targets to be reported as held back"
        assert all(h["frames"] == 2 and h["min"] == 3 for h in held)
        # A held target is NOT marked attempted, so the next scan re-checks it.
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
            finally:
                proj.close()

        # More subs solve → now at the floor → it stacks on the next scan.
        _reaccept_all(lib)  # back to 3 accepted+solved per target
        summary2 = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert calls, "target should auto-stack once enough subs are located"
        assert summary2["auto_stacked"]
        assert not summary2.get("auto_stack_held_thin")
    finally:
        lib.close()


def test_auto_stack_skips_a_legacy_mixed_drop_target(solved_library, monkeypatch):
    """A target flagged as a legacy whole-device / mixed-folder drop must be
    skipped by the walk-away auto-stack — it holds several objects' subs jumbled
    together, so stacking it just makes mixed-pointing gibberish and burns compute,
    and the correct per-target versions already exist. Fail-before: the flagged
    giant target was auto-stacked like any other. Other targets still stack."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        targets = lib.list_targets()
        assert len(targets) >= 2, "fixture should have multiple targets to compare"
        flagged = targets[0]
        lib.flag_legacy_mixed_drop(flagged.safe_name)

        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        # The flagged target is reported skipped and never handed to run_stack.
        assert flagged.safe_name in summary.get("auto_stack_legacy_skipped", [])
        assert flagged.safe_name not in summary.get("auto_stacked", [])
        # It's skipped cheaply — no attempt marker written, so removing it (or a
        # user re-accept) is the only state change.
        proj = lib.open_target(flagged.safe_name)
        try:
            assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
        finally:
            proj.close()
        # The other (unflagged) targets still auto-stack as normal.
        assert summary["auto_stacked"], "unflagged targets should still stack"
        assert calls, "unflagged targets should reach run_stack"
    finally:
        lib.close()


def _spread_across_panels(lib, n_side: int, step_deg: float = 0.5) -> None:
    """Re-point every target's subs over an ``n_side × n_side`` mosaic grid.

    The fixture's subs all sit on one pointing (a single field). A Seestar
    mosaic walks its panels, so its subs are spread across them — which is the
    whole point: the target's *count* stays what it was while the depth at any
    one pixel drops by the number of panels.
    """
    for entry in lib.list_targets():
        proj = lib.open_target(entry.safe_name)
        try:
            frames = list(proj.iter_frames())
            for k, f in enumerate(frames):
                i, j = k % n_side, (k // n_side) % n_side
                proj.update_frame(f.id, ra_center_deg=83.6 + i * step_deg,
                                  dec_center_deg=-5.4 + j * step_deg)
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)


def test_auto_stack_holds_back_a_mosaic_that_is_one_sub_deep_everywhere(
    solved_library, monkeypatch,
):
    """The minimum-frames floor must judge a *pixel*, not a frame count.

    The owner is a heavy mosaic user (AGENTS.md §1). A mosaic one pass in has
    one sub per panel, so its picture is single-frame colour speckle at every
    pixel — but its *count* clears the floor, so the walk-away scan published it
    (and the auto-edit adopted it) as the target's newest picture: exactly the
    gibberish the floor was added to prevent, through the door it left open.

    Fail-before: the mosaic was auto-stacked at depth 1. After: held back, with
    no attempt marker, so the next scan stacks it the moment the panels deepen.
    """
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _spread_across_panels(lib, n_side=2)   # 3 subs -> 3 panels, 1 deep each
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert calls == [], "a one-sub-deep mosaic must not be published"
        assert summary["auto_stacked"] == []
        held = summary.get("auto_stack_held_thin")
        assert held, "expected the mosaic to be reported as held back"
        for h in held:
            # The count that used to wave it through is still reported honestly
            # beside the depth that actually describes the picture.
            assert h["frames"] >= h["min"]
            assert h["panel_depth"] == 1
            assert h["panels"] >= 2
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
            finally:
                proj.close()
    finally:
        lib.close()


def test_auto_stack_still_fires_for_a_single_field_at_the_floor(
    solved_library, monkeypatch,
):
    """The no-regression half: a single field is judged exactly as before — the
    depth check contributes nothing because there are no panels to divide by."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert calls, "a single-field target at the floor still stacks"
        assert summary["auto_stacked"]
        assert not summary.get("auto_stack_held_thin")
    finally:
        lib.close()


def test_a_mosaic_stacks_once_its_panels_reach_the_floor(
    solved_library, monkeypatch,
):
    """Self-clearing, like every other hold: deepen the panels and it goes."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        # Two panels, and every sub on one of them — 3 subs -> panels of 2 and 1,
        # so a typical sub sits 2 deep. Below the floor of 3: held.
        _spread_across_panels(lib, n_side=2)
        settings = _settings(solved_library).model_copy(
            update={"auto_stack_min_frames": 2})
        # Depth 1 < floor 2 → still held even with the floor lowered to 2.
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert calls == []
        assert summary.get("auto_stack_held_thin")
        # Floor of 1 is the documented opt-out — it restores stacking from the
        # first frame, and must not be re-armed by the depth check.
        opt_out = _settings(solved_library).model_copy(
            update={"auto_stack_min_frames": 1})
        summary2 = pipeline._pipeline_body(
            opt_out, _FakeJM(), Job(kind="pipeline"), root=None)
        assert calls, "floor=1 must still stack a one-sub-deep mosaic"
        assert summary2["auto_stacked"]
        assert not summary2.get("auto_stack_held_thin")
    finally:
        lib.close()


def test_auto_stack_min_frames_one_restores_stacking_from_first_frame(
    solved_library, monkeypatch,
):
    """Setting the floor to 1 opts back into the old stack-a-thin-set behaviour."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        _reject_down_to(lib, keep=1)  # 1 accepted+solved per target
        settings = _settings(solved_library).model_copy(
            update={"auto_stack_min_frames": 1})
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert calls, "floor=1 should stack even a single-frame target"
        assert summary["auto_stacked"]
        assert not summary.get("auto_stack_held_thin")
    finally:
        lib.close()


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
                       memory_budget_gb=None, app_version=None, **_kw):  # noqa: ANN001
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


def test_walk_away_stack_turns_on_quality_weighting(solved_library, monkeypatch):
    # Same walk-away path, same "user made no choice" guard: weight each sub by the
    # QC metrics already measured, so an unattended stack across variable nights
    # doesn't trust a soft / cloud-thinned sub as much as a sharp one.
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
    assert captured["opts"].quality_weighted is True


def test_manual_stack_leaves_quality_weighting_off(solved_library, monkeypatch):
    # The manual Stack form is honoured verbatim — the engine default (off) stands,
    # so an existing manual stack is byte-for-byte unchanged.
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
    assert captured["opts"].quality_weighted is False


@pytest.mark.parametrize("saved", [True, False])
def test_walk_away_respects_an_explicit_saved_quality_weighting_choice(
    solved_library, monkeypatch, saved,
):
    # A per-target "Save as defaults" that names quality weighting either way wins:
    # the walk-away path must not override an explicit choice — including an
    # explicit *off*, which is the one a blind ``= True`` would trample.
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
                json.dumps({"quality_weighted": saved}),
            )
        finally:
            proj.close()
        pipeline._stack_target(
            _settings(solved_library), _FakeJM(), Job(kind="stack"), lib, safe,
            auto=True)
    finally:
        lib.close()
    assert captured["opts"].quality_weighted is saved


def test_walk_away_skips_quality_weighting_when_saved_defaults_pick_min_max(
    solved_library, monkeypatch,
):
    # A saved default of explicit min/max rejection combines by *rank* and ignores
    # per-frame weights, so injecting quality weighting there would change nothing
    # in the picture while making the run stamp WGTSKIP with auto=False — which
    # History renders as "use sigma clipping instead", advice to undo a setting the
    # user never chose. Leave it off and say nothing.
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
    assert captured["opts"].min_max_reject is True
    assert captured["opts"].quality_weighted is False


def test_walk_away_still_weights_a_drizzle_stack_that_names_min_max(
    solved_library, monkeypatch,
):
    # Drizzle is the exemption: it honours per-frame weights and runs its own
    # two-pass rejection, so a stray min_max_reject in the saved defaults is inert
    # there and must not suppress the weighting.
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
                json.dumps({"min_max_reject": True, "drizzle": True}),
            )
        finally:
            proj.close()
        pipeline._stack_target(
            _settings(solved_library), _FakeJM(), Job(kind="stack"), lib, safe,
            auto=True)
    finally:
        lib.close()
    assert captured["opts"].drizzle is True
    assert captured["opts"].quality_weighted is True


def test_walk_away_drizzle_stack_turns_on_drizzle_rejection(
    solved_library, monkeypatch,
):
    # Drizzle accumulates in one shot, so ``auto_reject`` — and every method it
    # resolves to — is a no-op there; drizzle has its own two-pass rejection
    # instead, and nothing ever turned it on. A drizzled walk-away stack therefore
    # combined completely unfiltered, keeping every satellite and plane trail that
    # slipped past frame-level QC.
    import json

    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            proj.set_meta(
                pipeline.STACK_DEFAULTS_META_KEY, json.dumps({"drizzle": True}))
        finally:
            proj.close()
        pipeline._stack_target(
            _settings(solved_library), _FakeJM(), Job(kind="stack"), lib, safe,
            auto=True)
    finally:
        lib.close()
    assert captured["opts"].drizzle is True
    assert captured["opts"].drizzle_reject is True


def test_walk_away_respects_an_explicit_drizzle_rejection_choice(
    solved_library, monkeypatch,
):
    # A user who saved "drizzle, no rejection" as this target's default meant it —
    # the two-pass rejection costs a second pass over every frame, so choosing to
    # skip it is a legitimate choice the walk-away path must not overrule.
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
                json.dumps({"drizzle": True, "drizzle_reject": False}))
        finally:
            proj.close()
        pipeline._stack_target(
            _settings(solved_library), _FakeJM(), Job(kind="stack"), lib, safe,
            auto=True)
    finally:
        lib.close()
    assert captured["opts"].drizzle_reject is False


def test_walk_away_without_drizzle_leaves_drizzle_rejection_alone(
    solved_library, monkeypatch,
):
    # The flag means nothing off the drizzle path, and a run record that carries a
    # setting the run never used is a small lie. The ordinary walk-away stack's
    # options must come out exactly as they always have.
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
    assert captured["opts"].drizzle is False
    assert captured["opts"].drizzle_reject is False


def test_manual_drizzle_stack_leaves_drizzle_rejection_off(
    solved_library, monkeypatch,
):
    # The manual Stack form is honoured verbatim, drizzle included: the user sees
    # the "Drizzle outlier rejection" checkbox and its answer is theirs.
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        pipeline._stack_target(
            _settings(solved_library), _FakeJM(), Job(kind="stack"), lib, safe,
            options={"drizzle": True})
    finally:
        lib.close()
    assert captured["opts"].drizzle is True
    assert captured["opts"].drizzle_reject is False


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
                               memory_budget_gb=None, app_version=None, _n=n, **_kw):  # noqa: ANN001
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
             memory_budget_gb=None, app_version=None, **_kw):  # noqa: ANN001
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
                               memory_budget_gb=None, app_version=None, **_kw):  # noqa: ANN001
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
             memory_budget_gb=None, app_version=None, **_kw):  # noqa: ANN001
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


# --- Readability preflight: a walk-away stack must never publish a picture made
# --- worse by subs whose files are temporarily off-line (the owner's
# --- "my images turned out worse" regression, 2026-08-17).


def _unread(proj, frame_ids: list[int]) -> None:
    """Make frames unreadable *without touching a byte on disk* — repoint their
    recorded paths at a file that isn't there, which is exactly what the app
    sees when a share unmounts, a folder is archived, or a drive drops out.
    (Never move the real files: ``incoming/`` is strictly read-only, AGENTS §10.)"""
    for fid in frame_ids:
        f = proj.get_frame(fid)
        assert f is not None
        proj.update_frame(
            fid,
            source_path=f"{f.source_path}.__gone__",
            cached_path=None if not f.cached_path else f"{f.cached_path}.__gone__",
        )


def _reread(proj, frame_ids: list[int]) -> None:
    """Undo :func:`_unread` — the share came back."""
    for fid in frame_ids:
        f = proj.get_frame(fid)
        assert f is not None
        fields = {}
        for col in ("source_path", "cached_path"):
            val = getattr(f, col)
            if val and val.endswith(".__gone__"):
                fields[col] = val[: -len(".__gone__")]
        if fields:
            proj.update_frame(fid, **fields)


def _solved_ids(proj) -> list[int]:
    return [f.id for f in proj.iter_frames(accepted_only=True) if f.wcs_json]


def _record_run(proj, n_frames_used: int) -> None:
    proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc="2026-05-01T00:00:00Z",
        output_basename="master", fits_path=None, tiff_path=None,
        preview_path=None, n_frames_used=n_frames_used,
        canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=n_frames_used,
        options_json="{}",
    ))


def test_auto_stack_holds_back_when_subs_are_unreadable(solved_library, monkeypatch):
    """The owner-reported regression: a growing target's walk-away stack must NOT
    publish a thinner, noisier picture just because some subs' files went briefly
    off-line.

    Before the fix ``_auto_stack_frame_count`` decided purely from the DB's
    accepted+solved count, never asking whether those frames could actually be
    *read*; ``run_stack`` then silently dropped the unreadable ones and the
    result was published as the target's newest picture — 787 → 271 frames
    across one growing night, with the noise measurably worse. Fail-before: the
    target auto-stacked with only 1 of its 3 subs readable, over a run that had
    already used 2.
    """
    calls = _patch_run_stack(monkeypatch)
    # Floor of 1 so the *thin* guard can't be what holds the target back — this
    # asserts the "don't publish something worse than what already stands" half.
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 1})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            assert len(ids) >= 3
            _record_run(proj, n_frames_used=len(ids) - 1)  # a better run exists
            _unread(proj, ids[:-1])                        # only one still readable
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe not in summary["auto_stacked"], (
            "must not publish a stack made thin by missing files")
        assert summary["auto_stacked"], (
            "the library's other, healthy targets must still stack")
        held = summary.get("auto_stack_held_unreadable") or []
        entry = next((h for h in held if h["target"] == safe), None)
        assert entry is not None, "the hold should be reported, not silent"
        assert entry["unreadable"] == len(ids) - 1
        assert entry["readable"] == 1
        assert entry["prior_best"] == len(ids) - 1

        # …and it is held WITHOUT marking the attempt, so the next scan retries.
        proj = lib.open_target(safe)
        try:
            assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
            _reread(proj, ids)          # the share comes back
        finally:
            proj.close()

        summary2 = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary2["auto_stacked"], (
            "once the files are readable again it must stack the full set")
        assert not summary2.get("auto_stack_held_unreadable")
    finally:
        lib.close()


def test_the_readability_preflight_never_builds_a_frame_row_per_sub(solved_library):
    """The preflight asks two path columns and a bit; it must not read the header.

    ``_solved_accepted_unreadable`` is on the walk-away path and is asked of a
    target with thousands of subs, where a ``FrameRow`` per sub meant reading each
    one's plate solution to test *whether it has one*. It now asks
    ``Project.count_unreadable_frames(accepted_only=True, solved_only=True)``,
    whose solved bar is that same truthiness test in SQL — pinned here by making
    the whole-row read fail, which the expression it replaced could not survive.
    """
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            assert len(ids) >= 2, "fixture must carry solved subs to lose"
            _unread(proj, ids[:1])
            assert pipeline._solved_accepted_unreadable(proj) == 1

            def _boom(*_a, **_k):
                raise AssertionError("the preflight must not read whole rows")

            proj.iter_frames = _boom  # type: ignore[method-assign]
            assert pipeline._solved_accepted_unreadable(proj) == 1
            del proj.iter_frames
            _reread(proj, ids[:1])
            assert pipeline._solved_accepted_unreadable(proj) == 0
        finally:
            proj.close()
    finally:
        lib.close()


def test_auto_stack_still_fires_when_every_sub_is_readable(solved_library, monkeypatch):
    """The guard is gated on there being unreadable files at all, so a healthy
    target — every install with its subs on disk — behaves exactly as before,
    including the case where a prior run legitimately dropped subs at alignment
    (which must still be recognised as coverable work, not held back)."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            _record_run(proj, n_frames_used=1)  # an old, much thinner run
        finally:
            proj.close()
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary["auto_stacked"]
        assert calls, "run_stack must be reached for a healthy target"
        assert not summary.get("auto_stack_held_unreadable")
    finally:
        lib.close()


def _two_panels(proj, ids: list[int], step_deg: float = 0.5) -> None:
    """Put every sub but the last on one panel and the last on a second.

    A deliberately *lopsided* mosaic: the target's typical panel depth is the
    deep panel's, so the whole-target depth guard upstream is satisfied, while
    losing a single file from that panel leaves one sub on each panel — which is
    the state this fixture exists to build.
    """
    for k, fid in enumerate(ids):
        proj.update_frame(
            fid, ra_center_deg=83.6 + (step_deg if k == len(ids) - 1 else 0.0),
            dec_center_deg=-5.4)


def test_a_mosaic_held_because_its_readable_subs_are_one_deep_per_panel(
    solved_library, monkeypatch,
):
    """The readability floor must judge a *pixel* too, not a frame count.

    ``_auto_stack_panel_depth`` corrects the minimum-frames floor for a mosaic —
    but it measures the subs the **database** lists, which is the right question
    only while their files are there. With some of them off-line the picture that
    actually gets combined is made of the readable ones, and on a mosaic those
    can clear every count in the chain while lying one deep on each panel.

    Fail-before: the target auto-stacked with two readable subs on two different
    panels — a picture that is single-frame colour speckle everywhere, published
    (and auto-edited) as the target's newest, which is the exact harm the whole
    hold family exists to prevent. After: held, with the depth reported beside
    the count that waved it through, and no attempt marker — so the next scan
    stacks it the moment the files come back.
    """
    calls = _patch_run_stack(monkeypatch)
    # Floor of 2: the readable count (2) clears it, so only the depth can hold.
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 2})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            assert len(ids) >= 3
            _two_panels(proj, ids)      # 2 subs on one panel, 1 on the other
            _unread(proj, ids[:1])      # one of the deep panel's two is away
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe not in summary["auto_stacked"], (
            "a mosaic one readable sub deep per panel must not be published")
        assert summary["auto_stacked"], "the healthy targets must still stack"
        held = summary.get("auto_stack_held_unreadable") or []
        entry = next((h for h in held if h["target"] == safe), None)
        assert entry is not None, "the hold should be reported, not silent"
        # The count that used to wave it through is still reported honestly,
        # beside the depth that actually describes the picture.
        assert entry["readable"] >= settings.auto_stack_min_frames
        assert entry["unreadable"] == 1
        assert entry["prior_best"] is None, "no earlier picture is being protected"
        assert entry["panel_depth"] == 1
        assert entry["panels"] == 2
        assert "panel" in (entry["reason"] or "")

        proj = lib.open_target(safe)
        try:
            assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
            _reread(proj, ids)          # the share comes back
        finally:
            proj.close()
        calls.clear()
        summary2 = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary2["auto_stacked"], (
            "with every file back the mosaic's panels are deep enough again")
        assert not summary2.get("auto_stack_held_unreadable")
    finally:
        lib.close()


def test_the_readability_floor_is_unchanged_on_a_single_field(
    solved_library, monkeypatch,
):
    """The no-regression half: on a single field the depth *is* the count, so the
    new question can never hold a target the old one would have let through."""
    calls = _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 2})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            _unread(proj, _solved_ids(proj)[:1])   # one away, two readable
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary["auto_stacked"]
        assert calls, "a single field with two readable subs still stacks"
        assert not summary.get("auto_stack_held_unreadable")
    finally:
        lib.close()


def test_the_readability_floors_depth_question_honours_the_floor_of_one(
    solved_library, monkeypatch,
):
    """``auto_stack_min_frames = 1`` is the documented opt-out back to stacking
    from the first frame, and the depth question must not re-arm it — the same
    rule ``_auto_stack_panel_depth`` already follows."""
    calls = _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 1})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            _two_panels(proj, ids)
            _unread(proj, ids[:1])
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary["auto_stacked"], "floor=1 must still stack"
        assert calls
        assert not summary.get("auto_stack_held_unreadable")
    finally:
        lib.close()


def test_auto_stack_holds_a_first_stack_only_when_below_the_floor(
    solved_library, monkeypatch,
):
    """A target with no prior stack has no good picture to protect, and the loss
    may be permanent (originals deleted, cache cleared) — so it is held back only
    when too few subs are readable to make anything but speckle, never merely
    because *some* are missing. Otherwise the guard would strand first stacks."""
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            _unread(proj, ids[:1])   # one missing, no prior run
        finally:
            proj.close()
        # Floor of 1: two readable subs clear it, so this must still stack.
        settings = _settings(solved_library).model_copy(
            update={"auto_stack_min_frames": 1})
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary["auto_stacked"]

        # Below the floor, though, it is held — the same "don't publish speckle"
        # rule as held_thin, now honest about which subs actually exist.
        calls.clear()
        proj = lib.open_target(safe)
        try:
            proj.delete_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY)
            proj.delete_meta(pipeline.AUTO_STACK_UNREADABLE_META_KEY)
            _reread(proj, ids)
            _unread(proj, ids[1:])   # now only one readable, floor is 3
        finally:
            proj.close()
        summary2 = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe not in summary2["auto_stacked"]
        held = summary2.get("auto_stack_held_unreadable") or []
        entry = next((h for h in held if h["target"] == safe), None)
        assert entry is not None and entry["readable"] == 1
    finally:
        lib.close()


def test_auto_stack_retries_a_stack_crippled_by_missing_files(
    solved_library, monkeypatch,
):
    """The second half of the regression: once a crippled stack *has* fired, the
    attempt marker recorded the DB-level count — blind to what was readable — so
    the trigger never fired again and the degraded picture stood indefinitely.

    Fail-before: after a stack that could read only 1 of 3 subs, restoring the
    files left ``_auto_stack_frame_count`` returning ``None`` forever.
    """
    _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            n = len(ids)
            _unread(proj, ids[:-1])
            # The state a crippled stack leaves behind: "covered n" + "n-1 of
            # them were missing at the time".
            proj.set_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY, str(n))
            proj.set_meta(pipeline.AUTO_STACK_UNREADABLE_META_KEY, str(n - 1))
        finally:
            proj.close()
        # Still missing → must NOT loop, re-stacking the same thin data forever.
        assert pipeline._auto_stack_frame_count(lib, safe) is None

        proj = lib.open_target(safe)
        try:
            _reread(proj, ids)
        finally:
            proj.close()
        # Files are back → the same data is worth stacking again, properly.
        assert pipeline._auto_stack_frame_count(lib, safe) == n
    finally:
        lib.close()


def test_stack_records_how_many_subs_were_unreadable(solved_library, monkeypatch):
    """Every stack stamps the missing-file count next to its attempt marker, so
    the retry above has something to compare against — and a run where nothing
    was missing writes no key at all, leaving a healthy target's meta untouched
    and never letting a stale count outlive its outage."""
    _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            _unread(proj, ids[:1])
        finally:
            proj.close()
        settings = _settings(solved_library).model_copy(
            update={"auto_stack_min_frames": 1})
        pipeline._pipeline_body(settings, _FakeJM(), Job(kind="pipeline"), root=None)
        proj = lib.open_target(safe)
        try:
            assert proj.get_meta(pipeline.AUTO_STACK_UNREADABLE_META_KEY) == "1"
            _reread(proj, ids)
            proj.delete_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY)
        finally:
            proj.close()
        pipeline._pipeline_body(settings, _FakeJM(), Job(kind="pipeline"), root=None)
        proj = lib.open_target(safe)
        try:
            assert proj.get_meta(pipeline.AUTO_STACK_UNREADABLE_META_KEY) is None
        finally:
            proj.close()
    finally:
        lib.close()


def _record_genuine_run(proj, n_frames_used: int, when: str,
                        *, options_json: str | None = None) -> None:
    """A stack run that reads as a *genuine* integration (its ``options_json``
    parses as real ``StackOptions``), unlike ``_record_run``'s bare ``{}``.
    ``when`` orders it — ``iter_stack_runs`` is newest-first by timestamp."""
    proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc=when,
        output_basename=f"master_{when}", fits_path=None, tiff_path=None,
        preview_path=None, n_frames_used=n_frames_used,
        canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=n_frames_used,
        options_json=options_json or '{"sigma_clip": true, "sigma_kappa": 3.0}',
    ))


def test_auto_stack_heals_a_target_left_on_a_degraded_picture(
    solved_library, monkeypatch,
):
    """The owner's live install: a walk-away stack made thin by a storage hiccup
    was published *before* the readability preflight existed, so the target's
    newest picture is much worse than one it already made (787 → 271 frames on
    the real data) and the frame-count trigger correctly answers "already
    covered" forever after.

    Once every sub is readable again, the scan must re-stack it **once** —
    and then stay quiet, however many scans follow.

    Fail-before: no heal path at all, so the degraded run stood and the target
    was reported as skipped.
    """
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            n = len(ids)
            assert n >= 3
            _record_genuine_run(proj, n, "2026-05-01T00:00:00Z")       # the good one
            _record_genuine_run(proj, 1, "2026-05-02T00:00:00Z")       # the thin one
            # The state that stack left behind: "covered n" and nothing missing.
            proj.set_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY, str(n))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary["auto_stacked"], (
            "the degraded picture must be re-stacked from the full set")
        healed = summary.get("auto_stack_healed") or []
        entry = next((h for h in healed if h["target"] == safe), None)
        assert entry is not None, "the heal should be reported, not silent"
        assert entry["newest"] == 1
        assert entry["best"] == n
        assert entry["frames"] == n

        # …and it fires exactly once: the marker holds even though the stubbed
        # stacker recorded no new run, so the situation still looks degraded.
        calls.clear()
        summary2 = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe not in summary2["auto_stacked"]
        assert not summary2.get("auto_stack_healed")
        assert safe in summary2["auto_stack_skipped"]
    finally:
        lib.close()


def test_heal_leaves_a_deliberately_thinner_newest_stack_alone(
    solved_library, monkeypatch,
):
    """A user who rejected most of a target's subs and re-stacked has a
    legitimately thinner newest picture — that's their decision, not damage.
    The discriminator is the accepted+solved population: if it's still as big as
    the best run's, the frames went missing; if it shrank, the user shrank it."""
    _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            n = len(ids)
            _record_genuine_run(proj, n, "2026-05-01T00:00:00Z")
            _record_genuine_run(proj, 1, "2026-05-02T00:00:00Z")
            # The user rejected all but one sub, then re-stacked.
            for fid in ids[1:]:
                proj.update_frame(fid, accept=False, reject_reason="user",
                                  user_override=True)
            proj.set_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY, "1")
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        assert pipeline._auto_stack_degraded_recheck(lib, safe) is None
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe not in summary["auto_stacked"]
        assert not summary.get("auto_stack_healed")
    finally:
        lib.close()


def test_heal_waits_until_the_missing_subs_are_actually_back(
    solved_library, monkeypatch,
):
    """Mid-outage the heal must stand down: re-stacking now would just reproduce
    the thin picture, and the readability preflight already owns that case."""
    _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            n = len(ids)
            _record_genuine_run(proj, n, "2026-05-01T00:00:00Z")
            _record_genuine_run(proj, 1, "2026-05-02T00:00:00Z")
            proj.set_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY, str(n))
            _unread(proj, ids[:1])          # still off-line
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        assert pipeline._auto_stack_degraded_recheck(lib, safe) is None

        proj = lib.open_target(safe)
        try:
            _reread(proj, ids)              # the share comes back
        finally:
            proj.close()
        heal = pipeline._auto_stack_degraded_recheck(lib, safe)
        assert heal is not None and heal[0] == n
    finally:
        lib.close()


def test_heal_never_reads_an_editor_export_as_a_collapse(solved_library, monkeypatch):
    """Editor-export and channel-combine runs live in ``stack_runs`` too, with a
    tiny ``n_frames_used``. Counting one as "the newest stack" would make every
    edited target look catastrophically degraded and re-stack it."""
    _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            n = len(_solved_ids(proj))
            _record_genuine_run(proj, n, "2026-05-01T00:00:00Z")
            _record_genuine_run(
                proj, 1, "2026-05-02T00:00:00Z",
                options_json='{"editor_recipe": {"ops": []}, "derived_from": 1}')
            _record_genuine_run(
                proj, 1, "2026-05-03T00:00:00Z",
                options_json='{"channel_combine": [], "weights": {}}')
            proj.set_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY, str(n))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        assert pipeline._auto_stack_degraded_recheck(lib, safe) is None
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
        assert not summary.get("auto_stack_healed")
    finally:
        lib.close()


def test_heal_ignores_an_ordinary_handful_of_align_drops(solved_library, monkeypatch):
    """A stack that loses a sub or two at alignment is normal and run-to-run
    consistent — both the ratio and the absolute-loss rail must be cleared before
    the app spends a whole re-stack on it."""
    _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            n = len(_solved_ids(proj))
            _record_genuine_run(proj, n, "2026-05-01T00:00:00Z")
            _record_genuine_run(proj, n - 1, "2026-05-02T00:00:00Z")
            proj.set_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY, str(n))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        assert pipeline._auto_stack_degraded_recheck(lib, safe) is None
    finally:
        lib.close()


def test_setting_the_missing_subs_aside_ends_a_hold_that_never_lifts(
        solved_library, monkeypatch):
    """A8. The hold is right while the files are coming back and a dead end when
    they never do: the owner deletes a session from ``incoming/`` (his folder,
    his right), the DB rows stay, ``unreadable`` never drops, and every scan for
    the rest of time reports the same hold over data that cannot improve. He was
    told, and offered nothing to do.

    Fail-before: re-scanning re-reports the hold, unchanged, for ever. With the
    gone subs set aside — a database-only, reversible flag, nothing on disk
    touched — the hold is gone, the target's accepted count stops claiming subs
    that do not exist, and it goes back to the ordinary "stack when there is more
    than last time" rule.
    """
    _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 1})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            assert len(ids) >= 3
            _record_run(proj, n_frames_used=len(ids))
            # One brand-new sub, so the frame-count trigger fires and the hold is
            # what actually stops the stack (rather than "nothing new to do").
            extra = proj.add_frame(FrameRow(
                source_path=str(Path(proj.project_dir) / "extra.fit"),
                wcs_json="WCS", ra_center_deg=83.6, dec_center_deg=-5.4))
            (Path(proj.project_dir) / "extra.fit").write_bytes(b"x")
            _unread(proj, ids[:-1])  # deleted for good — never coming back
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        # Held, and re-scanning changes nothing: this is the dead end.
        for _ in range(2):
            summary = pipeline._pipeline_body(
                settings, _FakeJM(), Job(kind="pipeline"), root=None)
            assert safe not in summary["auto_stacked"]
            held = summary.get("auto_stack_held_unreadable") or []
            assert any(h["target"] == safe for h in held)

        proj = lib.open_target(safe)
        try:
            assert set(proj.set_missing_frames_aside()) == set(ids[:-1])
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        held = summary.get("auto_stack_held_unreadable") or []
        assert not any(h["target"] == safe for h in held), (
            "the hold must be over once the missing subs are set aside")

        # …and the target now counts only subs that exist.
        proj = lib.open_target(safe)
        try:
            remaining = {f.id for f in proj.iter_frames(accepted_only=True)}
            assert remaining == {ids[-1], extra}
        finally:
            proj.close()
    finally:
        lib.close()


def test_a_scan_puts_set_aside_subs_back_when_their_files_return(
        solved_library, monkeypatch):
    """The other half, and the reason the button is safe to offer: plugging the
    drive back in undoes it with no action from the owner at all — including on a
    target the QC pass never touched, which is exactly the state a target sits in
    while its files are away."""
    _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 1})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _solved_ids(proj)
            _unread(proj, ids[:-1])
            assert set(proj.set_missing_frames_aside()) == set(ids[:-1])
            assert proj.count_frames_set_aside_as_missing() == len(ids) - 1
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        proj = lib.open_target(safe)
        try:
            _reread(proj, ids)  # the share comes back
        finally:
            proj.close()

        pipeline._pipeline_body(settings, _FakeJM(), Job(kind="pipeline"), root=None)

        proj = lib.open_target(safe)
        try:
            assert proj.count_frames_set_aside_as_missing() == 0
            assert set(_solved_ids(proj)) == set(ids)
        finally:
            proj.close()
    finally:
        lib.close()


def test_a_healthy_scan_sets_nothing_aside_and_reports_nothing(
        solved_library, monkeypatch):
    """Every file present — every healthy install — so the new pass is invisible:
    no frame changes, and the scan summary gains no key."""
    _patch_run_stack(monkeypatch)
    settings = _settings(solved_library)
    lib = Library.open_or_create(solved_library / "library")
    try:
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert "missing_files_restored" not in summary
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                assert proj.count_frames_set_aside_as_missing() == 0
            finally:
                proj.close()
    finally:
        lib.close()


# ---- what a poll costs per target, which is a number nobody was watching ----


def test_the_scan_loops_stack_decision_builds_no_frame_objects(
    solved_library,
):
    """Every question the auto-stack trigger asks of a target is a column, and
    it is asked of every target on every poll.

    Fail-before: `_solved_accepted_count` summed a generator over
    `iter_frames`; `_detect_mixed_pointings`, `_auto_stack_panel_depth` and
    `_auto_stack_readability_hold` each read the same rows again for two
    coordinates and two paths. So a five-minute poll built a `FrameRow` per
    accepted sub, per target, *per question* — each one carrying the plate-solve
    header whose existence was all that was being asked. Measured on a synthetic
    project the size of the owner's deepest target (35,894 subs): the count
    **935 ms → 54 ms** and the pointing read **993 ms → 254 ms**, identical
    answers.

    All four are driven here rather than one, because the docstring the whole
    change is against is `_auto_stack_degraded_recheck`'s promise that a healthy,
    up-to-date target "pays nothing but a couple of DB reads" — a claim about the
    decision as a whole, not about any one of its steps.
    """
    from framerows import frame_rows_built_by

    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        settings = _settings(solved_library).model_copy(
            update={"auto_bind_calibration": True})

        # Each of the six decisions is named, so a row is counted only if the
        # decision that asked for it is on its own stack — see
        # `tests/framerows.py` for the leaked `job-worker` this used to count.
        with frame_rows_built_by(
            pipeline._auto_stack_frame_count,
            pipeline._auto_stack_calibration_recheck,
            pipeline._auto_stack_degraded_recheck,
            pipeline._detect_mixed_pointings,
            pipeline._auto_stack_panel_depth,
            pipeline._auto_stack_readability_hold,
        ) as built:
            offered = pipeline._auto_stack_frame_count(lib, safe)
            # The two rechecks behind it, which the scan reaches on every target
            # that has *no* new subs — i.e. on most targets, most polls.
            recheck = pipeline._auto_stack_calibration_recheck(settings, lib, safe)
            heal = pipeline._auto_stack_degraded_recheck(lib, safe)
            proj = lib.open_target(safe)
            try:
                mixed = pipeline._detect_mixed_pointings(proj)
            finally:
                proj.close()
            depth = pipeline._auto_stack_panel_depth(lib, safe, 3)
            hold = pipeline._auto_stack_readability_hold(lib, safe, offered or 0, 3)
    finally:
        lib.close()

    # The decision really was taken — otherwise the zero below means nothing.
    assert offered and offered > 0
    assert recheck is None and heal is None  # nothing stacked yet on this target
    assert mixed is None and depth is None and hold is None
    assert built() == 0, (
        f"built {built()} FrameRow objects deciding whether to auto-stack")


def _two_by_two(root, proj) -> list[int]:
    """Make the fixture target a two-panel mosaic of two subs each.

    ``pointing_groups`` calls a target a mosaic only when two groups each carry
    two subs, and the fixture has three — so a fourth row is added whose file is
    a *copy* outside ``incoming/`` (nothing the owner owns is touched). Returns
    the ids with panel A first: ``[A, B, B, A]``, the panels 1.5° apart.
    """
    import shutil
    from dataclasses import replace

    ids = _solved_ids(proj)
    assert len(ids) == 3, "fixture shape changed — rebuild the 2+2 below"
    first = proj.get_frame(ids[0])
    assert first is not None
    elsewhere = root / "elsewhere"
    elsewhere.mkdir()
    twin = elsewhere / Path(first.source_path).name
    shutil.copy2(first.source_path, twin)
    ids.append(proj.add_frame(replace(
        first, id=None, source_path=str(twin), cached_path=None)))
    for k, fid in enumerate(ids):
        proj.update_frame(
            fid, ra_center_deg=83.6 + (1.5 if k in (0, 3) else 0.0),
            dec_center_deg=-5.4)
    return ids


def test_a_mosaic_panel_with_no_readable_sub_holds_the_walk_away_stack(
    solved_library, monkeypatch,
):
    """A panel whose files are *all* off-line must not be stacked away.

    The two count questions in the readability hold are whole-target
    (``readable < prior_best``) or typical-panel ones, and neither sees a panel
    that is simply absent: here panel A's two subs are both unreadable while
    panel B's two make up the best run's count of 2 at a depth of 2, so — before
    the fix — the hold returned ``None`` and the target's newest picture lost
    part of the mosaic. Owner-scale shape: a grown 2x2 stacked at 400, a newer
    night adding 150 to three panels while the fourth's 100 files are away.

    After: held, with ``panels_missing`` and the panel count reported, and
    without an attempt marker — so the scan after the files return stacks it.
    """
    calls = _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 2})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _two_by_two(solved_library, proj)
            _record_run(proj, n_frames_used=2)   # a picture of A + B stands
            _unread(proj, [ids[0], ids[3]])      # every file on panel A is away
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe not in summary["auto_stacked"], (
            "a stack missing a whole panel of the mosaic must not be published")
        assert summary["auto_stacked"], "the healthy targets must still stack"
        held = summary.get("auto_stack_held_unreadable") or []
        entry = next((h for h in held if h["target"] == safe), None)
        assert entry is not None, "the hold should be reported, not silent"
        # Every count that used to wave it through is still reported honestly.
        assert entry["readable"] == 2 and entry["prior_best"] == 2
        assert entry["unreadable"] == 2
        assert "panel_depth" not in entry
        assert entry["panels_missing"] == 1
        assert entry["panels"] == 2
        assert "part of the mosaic" in (entry["reason"] or "")

        proj = lib.open_target(safe)
        try:
            assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
            _reread(proj, ids)          # the share comes back
        finally:
            proj.close()
        calls.clear()
        summary2 = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary2["auto_stacked"], (
            "with panel A's files back the whole mosaic stacks")
        assert not summary2.get("auto_stack_held_unreadable")
    finally:
        lib.close()


def _panel_rows(root, proj, n_a: int, n_b: int) -> tuple[list[int], list[int]]:
    """Make the fixture target a two-panel mosaic of ``n_a`` + ``n_b`` subs (panels
    1.5° apart), padding with rows whose files are *copies* outside ``incoming/``
    (nothing the owner owns is touched). Returns ``(panel A ids, panel B ids)``."""
    import shutil
    from dataclasses import replace

    ids = _solved_ids(proj)
    first = proj.get_frame(ids[0])
    assert first is not None
    elsewhere = root / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    while len(ids) < n_a + n_b:
        twin = elsewhere / f"{len(ids)}_{Path(first.source_path).name}"
        shutil.copy2(first.source_path, twin)
        ids.append(proj.add_frame(replace(
            first, id=None, source_path=str(twin), cached_path=None)))
    a, b = ids[:n_a], ids[n_a:n_a + n_b]
    for fid in a:
        proj.update_frame(fid, ra_center_deg=85.1, dec_center_deg=-5.4)
    for fid in b:
        proj.update_frame(fid, ra_center_deg=83.6, dec_center_deg=-5.4)
    return a, b


def test_a_mosaic_panel_left_with_a_few_readable_subs_holds_the_walk_away_stack(
    solved_library, monkeypatch,
):
    """v0.503.5 held a panel with *no* readable sub; one left with a handful went
    straight through (Scout 2026-10-28, sweep 2: panel D 510 → 10 subs, σ ×7).

    Here panel A has 4 subs and only 1 readable, panel B 6, all readable, and the
    standing picture used 6: readable 7 ≥ 6 passes the count rule, the typical
    depth is B's, and A still has *something* readable — so before the fix the
    hold returned ``None`` and A was published at a quarter of its depth.
    """
    calls = _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 2})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            a, b = _panel_rows(solved_library, proj, 4, 6)
            _record_run(proj, n_frames_used=6)
            _unread(proj, a[1:])                 # A keeps 1 of its 4
        finally:
            proj.close()
        lib.refresh_target_stats(safe)

        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe not in summary["auto_stacked"], (
            "a panel left with a quarter of its subs must not be published")
        held = summary.get("auto_stack_held_unreadable") or []
        entry = next((h for h in held if h["target"] == safe), None)
        assert entry is not None, "the hold should be reported, not silent"
        assert entry["readable"] == 7 and entry["prior_best"] == 6
        assert entry["panels_missing"] == 0
        assert entry["panels_thinned"] == 1
        assert entry["panels"] == 2
        assert "much thinner" in (entry["reason"] or "")

        proj = lib.open_target(safe)
        try:
            assert proj.get_meta(pipeline.AUTO_STACK_ATTEMPT_META_KEY) is None
            _reread(proj, a)
        finally:
            proj.close()
        calls.clear()
        summary2 = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary2["auto_stacked"]
    finally:
        lib.close()


def test_a_mosaic_panel_keeping_half_its_subs_is_not_held(
    solved_library, monkeypatch,
):
    """The line is *under* half: a panel keeping 2 of its 4 (σ ×√2 exactly) is a
    picture the count rule already judges, not one this question holds."""
    _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 2})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            a, _b = _panel_rows(solved_library, proj, 4, 6)
            _record_run(proj, n_frames_used=6)
            _unread(proj, a[2:])                 # A keeps 2 of its 4
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary["auto_stacked"]
        assert not summary.get("auto_stack_held_unreadable")
    finally:
        lib.close()


def _stamp_ingested(proj, frame_ids: list[int], iso: str) -> None:
    """Say when the app first saw these rows (``frames.ingested_at``), around the
    ``2026-05-01`` picture :func:`_record_run` records."""
    from datetime import datetime

    when = datetime.fromisoformat(iso).timestamp()
    for fid in frame_ids:
        proj._conn.execute(  # noqa: SLF001 — reaching for the stored fact
            "UPDATE frames SET ingested_at = ? WHERE id = ?", (when, fid))
    proj._conn.commit()  # noqa: SLF001


_BEFORE_PICTURE = "2026-04-30T00:00:00+00:00"
_AFTER_PICTURE = "2026-05-02T00:00:00+00:00"


def _stacks_without_a_hold(solved_library, monkeypatch, n_a, n_b, shape) -> None:
    _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 2})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            a, b = _panel_rows(solved_library, proj, n_a, n_b)
            shape(proj, a, b)
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        held = [h for h in summary.get("auto_stack_held_unreadable") or []
                if h["target"] == safe]
        assert not held, f"held for a picture it would not make worse: {held}"
        assert safe in summary["auto_stacked"]
    finally:
        lib.close()


def test_an_off_line_newest_night_on_one_panel_does_not_hold_a_deeper_stack(
    solved_library, monkeypatch,
):
    """Scout 2026-10-28, sweep 2, repro A. The picture used A 4 + B 6 = 10; since
    then A gained 6 (newest night, off-line) and B 3 (readable). A still has the
    4 the picture had and B goes 6 → 9 — strictly better — but counted against
    every sub on record A read as "under half readable" and the stack was held
    with "much thinner than in the picture this target already has"."""
    def shape(proj, a, b):
        _stamp_ingested(proj, a[:4] + b[:6], _BEFORE_PICTURE)
        _record_run(proj, n_frames_used=10)
        _stamp_ingested(proj, a[4:] + b[6:], _AFTER_PICTURE)
        _unread(proj, a[4:])
    _stacks_without_a_hold(solved_library, monkeypatch, 10, 9, shape)


def test_a_brand_new_off_line_panel_is_not_missing_from_the_picture(
    solved_library, monkeypatch,
):
    """Sweep 2, repro B: the picture used 10 on A; since then a brand-new panel B
    of 4 subs (all off-line) and +2 on A. B was never in the picture, so it can't
    be "out of the picture this target already has"."""
    def shape(proj, a, b):
        _stamp_ingested(proj, a[:10], _BEFORE_PICTURE)
        _record_run(proj, n_frames_used=10)
        _stamp_ingested(proj, a[10:] + b, _AFTER_PICTURE)
        _unread(proj, b)
    _stacks_without_a_hold(solved_library, monkeypatch, 12, 4, shape)


def test_a_panel_losing_the_subs_the_picture_had_still_holds_with_stamps(
    solved_library, monkeypatch,
):
    """With honest stamps the hold still asks the v0.503.16 question: A had 6 at
    the picture and 5 of those are off-line, so it keeps 2 readable (1 old, 1
    newer) of 6 and is held — the newer sub does not make up the loss."""
    _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 2})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            a, b = _panel_rows(solved_library, proj, 7, 7)
            _stamp_ingested(proj, a[:6] + b[:4], _BEFORE_PICTURE)
            _record_run(proj, n_frames_used=10)
            _stamp_ingested(proj, a[6:] + b[4:], _AFTER_PICTURE)
            _unread(proj, a[1:6])                # A: 1 old + 1 new readable of 6
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe not in summary["auto_stacked"]
        held = summary.get("auto_stack_held_unreadable") or []
        entry = next((h for h in held if h["target"] == safe), None)
        assert entry is not None and entry["panels_thinned"] == 1
    finally:
        lib.close()


def test_subs_on_record_at_picture_falls_back_when_the_stamps_cannot_say():
    """Unstamped rows count as on record; a picture said to combine more subs than
    existed at its own timestamp (a moved clock, rows written again) and a run
    with no readable timestamp both give ``None`` — every sub counts, as before."""
    run = StackRunRow(
        id=None, timestamp_utc="2026-05-01T00:00:00Z", output_basename="m",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=3,
        canvas_h=1, canvas_w=1, coverage_min=1, coverage_max=3, options_json="{}")
    from datetime import datetime
    before = datetime.fromisoformat(_BEFORE_PICTURE).timestamp()
    after = datetime.fromisoformat(_AFTER_PICTURE).timestamp()
    got = pipeline._subs_on_record_at_picture(
        [run], 3, [before, None, before, after])
    assert got == [True, True, True, False]
    assert pipeline._subs_on_record_at_picture([run], 3, [before, after, after]) is None
    from dataclasses import replace
    bad = replace(run, timestamp_utc="not a time")
    assert pipeline._subs_on_record_at_picture([bad], 3, [before] * 4) is None


def test_panels_with_nothing_readable_counts_a_panel_left_a_few_subs():
    """The Scout's owner-scale shape through the per-panel question itself: an S30
    2x2, panel D 510 deep of which 10 are readable, A-C fully readable."""
    centres = [(180.0, 30.0), (181.1, 30.0), (180.0, 31.0), (181.1, 31.0)]
    radecs, ok = [], []
    for k, (ra, dec) in enumerate(centres):
        n = 510 if k == 3 else 550
        radecs += [(ra, dec)] * n
        ok += ([True] * 10 + [False] * 500) if k == 3 else [True] * n
    got = pipeline._panels_with_nothing_readable(radecs, ok, 8)
    assert got == {"missing": 0, "thinned": 1, "panels": 4}
    # A single field never splits, so the count rule alone still decides it.
    assert pipeline._panels_with_nothing_readable(
        [(180.0, 30.0)] * 100, [True] * 10 + [False] * 90, 8) is None


def test_a_missing_panel_never_holds_a_targets_first_stack(
    solved_library, monkeypatch,
):
    """No picture stands, so there is nothing to protect: the first-stack rule
    the hold's docstring promises still holds for the per-panel question."""
    _patch_run_stack(monkeypatch)
    settings = _settings(solved_library).model_copy(
        update={"auto_stack_min_frames": 2})
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = _first_stackable(lib)
        assert safe is not None
        proj = lib.open_target(safe)
        try:
            ids = _two_by_two(solved_library, proj)
            _unread(proj, [ids[0], ids[3]])   # panel A away, no prior run
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None)
        assert safe in summary["auto_stacked"]
        assert not summary.get("auto_stack_held_unreadable")
    finally:
        lib.close()
