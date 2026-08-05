"""The walk-away auto-stack honours a target's *saved* calibration-master picks.

"Save as defaults" on the Stack form persists the four master ids alongside the
engine options and promises they "drive auto-stacking for this target" — but the
unattended path used to drop them, so a beginner who chose their darks once still
got uncalibrated walk-away stacks (only the separate, off-by-default
``auto_bind_calibration`` applied any calibration, and that *auto-picks* masters,
ignoring the user's choice). These cover the explicit pick winning, the fail-soft
skips that keep a walk-away run from erroring, and the unchanged behaviour of an
install whose saved defaults carry no master ids.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from seestack.io.library import Library
from webapp import calibration, pipeline
from webapp.config import Settings
from webapp.jobs import Job
from webapp.schemas import STACK_DEFAULTS_META_KEY

from .conftest import FRAME_H, FRAME_W


class _FakeJM:
    """Minimal JobManager stand-in for progress flushing."""

    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _capture_opts(monkeypatch):
    """Patch run_stack to record the StackOptions it's called with."""
    captured = {}

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        captured["opts"] = opts
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=0, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    return captured


def _register(root, kind: str, *, name: str, width=FRAME_W, height=FRAME_H,
              exposure_s: float | None = 30.0) -> dict:
    from seestack.calibrate.masters import MasterMeta

    arr = np.full((height or 4, width or 4), 42.0, dtype=np.float32)
    meta = MasterMeta(kind, 5, width, height, "median", exposure_s=exposure_s)
    return calibration.register_master(root, name=name, array=arr, meta=meta)


def _stack_with_saved_defaults(data_root, saved: dict, monkeypatch, **kwargs):
    """Run the walk-away ``_stack_target`` (options=None) after saving *saved* as
    the target's per-target stack defaults. Returns the captured StackOptions."""
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(data_root / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        proj = lib.open_target(safe)
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY, json.dumps(saved))
        finally:
            proj.close()
        settings = Settings(data_root=str(data_root), **kwargs)
        pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="pipeline"),
                               lib=lib, safe=safe)
    finally:
        lib.close()
    return captured["opts"]


def test_walk_away_stack_applies_saved_calibration_masters(solved_library, monkeypatch):
    """The core fix: an explicitly saved dark/flat pick reaches the unattended run."""
    root = solved_library / "library"
    dark = _register(root, "dark", name="My Dark")
    flat = _register(root, "flat", name="My Flat", exposure_s=None)

    opts = _stack_with_saved_defaults(
        solved_library,
        {"sigma_kappa": 2.25, "dark_master_id": dark["id"],
         "flat_master_id": flat["id"]},
        monkeypatch,
    )

    assert opts.sigma_kappa == 2.25  # the ordinary options still flow through
    assert opts.dark_path and opts.dark_path.endswith(dark["filename"])
    assert opts.flat_path and opts.flat_path.endswith(flat["filename"])
    assert opts.bias_path is None
    assert opts.flat_dark_path is None


def test_saved_pick_beats_the_auto_picker(solved_library, monkeypatch):
    """``auto_bind_calibration`` auto-*picks* a master; the user's explicit saved
    choice must win over it, not the other way round."""
    root = solved_library / "library"
    # A closer-matching dark the auto-picker would prefer, plus the one the user
    # actually chose and saved.
    _register(root, "dark", name="Auto-pick Dark", exposure_s=1.0)
    chosen = _register(root, "dark", name="Chosen Dark", exposure_s=30.0)

    opts = _stack_with_saved_defaults(
        solved_library, {"dark_master_id": chosen["id"]}, monkeypatch,
        auto_bind_calibration=True,
    )

    assert opts.dark_path and opts.dark_path.endswith(chosen["filename"])


def test_deleted_saved_master_is_skipped_not_fatal(solved_library, monkeypatch):
    """A master deleted since it was saved must not fail the walk-away run — the
    stack just goes ahead uncalibrated, exactly as it did before the pick existed."""
    root = solved_library / "library"
    dark = _register(root, "dark", name="Doomed Dark")
    assert calibration.delete_master(root, dark["id"]) is True

    opts = _stack_with_saved_defaults(
        solved_library, {"dark_master_id": dark["id"]}, monkeypatch)

    assert opts.dark_path is None


def test_wrong_size_saved_master_is_skipped(solved_library, monkeypatch):
    """A master built for another camera/binning would make ``run_stack``
    hard-fail at ``CalibrationMasters.validate``, turning a walk-away stack into an
    error. A provable dimension conflict is skipped instead."""
    root = solved_library / "library"
    wrong = _register(root, "dark", name="Other Camera",
                      width=FRAME_W // 2, height=FRAME_H // 2)

    opts = _stack_with_saved_defaults(
        solved_library, {"dark_master_id": wrong["id"]}, monkeypatch)

    assert opts.dark_path is None


def test_saved_master_without_recorded_dims_still_binds(solved_library, monkeypatch):
    """The dimension gate only refuses on a *positive* conflict: an older master
    that never recorded its size is still the user's explicit pick, so it binds
    (the manual Stack form applies it too)."""
    root = solved_library / "library"
    dark = _register(root, "dark", name="Sizeless Dark")
    entries = calibration._read_registry(root)
    for e in entries:
        if e["id"] == dark["id"]:
            e["width_px"] = None
            e["height_px"] = None
    calibration._write_registry(root, entries)

    opts = _stack_with_saved_defaults(
        solved_library, {"dark_master_id": dark["id"]}, monkeypatch)

    assert opts.dark_path and opts.dark_path.endswith(dark["filename"])


def test_stray_scale_dark_to_light_is_dropped_when_no_dark_binds(
        solved_library, monkeypatch):
    """``scale_dark_to_light`` asks the engine to exposure-scale a dark against a
    bias. With no dark bound it's a no-op that misrepresents the run's calibration
    intent — mirror ``_auto_bind_calibration``'s handling of the same stray flag."""
    root = solved_library / "library"
    dark = _register(root, "dark", name="Gone Dark")
    calibration.delete_master(root, dark["id"])

    opts = _stack_with_saved_defaults(
        solved_library,
        {"dark_master_id": dark["id"], "scale_dark_to_light": True},
        monkeypatch,
    )

    assert opts.dark_path is None
    assert opts.scale_dark_to_light is False


def test_saved_defaults_without_master_ids_are_unchanged(solved_library, monkeypatch):
    """Upgrade-safety: an install whose saved defaults predate the master picks
    (or who never chose one) must stack byte-identically — uncalibrated."""
    root = solved_library / "library"
    _register(root, "dark", name="Unpicked Dark")  # exists but was never chosen

    opts = _stack_with_saved_defaults(
        solved_library, {"sigma_kappa": 2.5}, monkeypatch)

    assert opts.sigma_kappa == 2.5
    assert opts.dark_path is None
    assert opts.flat_path is None
    assert opts.bias_path is None


def test_manual_options_do_not_resolve_saved_master_ids(solved_library, monkeypatch):
    """The manual Stack form resolves its own picks server-side in the router, so
    the explicit-options path must not re-resolve the *saved* ones behind it."""
    captured = _capture_opts(monkeypatch)
    root = solved_library / "library"
    dark = _register(root, "dark", name="Saved Dark")
    lib = Library.open_or_create(root)
    try:
        safe = lib.list_targets()[0].safe_name
        proj = lib.open_target(safe)
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY,
                          json.dumps({"dark_master_id": dark["id"]}))
        finally:
            proj.close()
        settings = Settings(data_root=str(solved_library))
        pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="stack"),
                               lib=lib, safe=safe, options={"sigma_kappa": 4.0})
    finally:
        lib.close()

    assert captured["opts"].sigma_kappa == 4.0
    assert captured["opts"].dark_path is None


# --- The run records *why* a saved pick was skipped -------------------------
#
# The skips above are deliberately fail-soft, but they leave the user with a
# less-calibrated picture and the reason only in the server log — which a
# beginner will never read. ``_stack_target`` stamps the reasons on the run so
# History can say them out loud.


def _recorded_skips(data_root, run_id: int = 1) -> list[str]:
    """The plain-language skip reasons stamped on a run, as History reads them."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(lib.list_targets()[0].safe_name)
        try:
            raw = proj.get_meta(
                f"{pipeline.CALIBRATION_SKIPPED_META_PREFIX}{run_id}")
        finally:
            proj.close()
    finally:
        lib.close()
    return json.loads(raw) if raw else []


def test_deleted_saved_master_records_why_on_the_run(solved_library, monkeypatch):
    """A master deleted since it was saved: the run must say so, naming the slot."""
    root = solved_library / "library"
    dark = _register(root, "dark", name="Doomed Dark")
    calibration.delete_master(root, dark["id"])

    _stack_with_saved_defaults(
        solved_library, {"dark_master_id": dark["id"]}, monkeypatch)

    skips = _recorded_skips(solved_library)
    assert len(skips) == 1
    assert skips[0] == ("Your saved master dark wasn't used: it's no longer in "
                        "your calibration library.")


def test_wrong_size_saved_master_records_both_sizes(solved_library, monkeypatch):
    """A master built for another camera: the reason names both frame sizes, so a
    beginner can see *which* pick doesn't fit these subs."""
    root = solved_library / "library"
    wrong = _register(root, "flat", name="Other Camera",
                      width=FRAME_W // 2, height=FRAME_H // 2)

    _stack_with_saved_defaults(
        solved_library, {"flat_master_id": wrong["id"]}, monkeypatch)

    skips = _recorded_skips(solved_library)
    assert len(skips) == 1
    assert skips[0] == (
        f"Your saved master flat wasn't used: it's {FRAME_W // 2}×"
        f"{FRAME_H // 2} pixels, but this target's subs are {FRAME_W}×{FRAME_H}.")


def test_a_run_that_applies_every_saved_pick_records_nothing(
        solved_library, monkeypatch):
    """No skip, no key — so an ordinary run's History line is exactly as before."""
    root = solved_library / "library"
    dark = _register(root, "dark", name="Good Dark")

    opts = _stack_with_saved_defaults(
        solved_library, {"dark_master_id": dark["id"]}, monkeypatch)

    assert opts.dark_path  # it really did bind
    assert _recorded_skips(solved_library) == []


def test_only_the_skipped_slot_is_recorded_when_another_binds(
        solved_library, monkeypatch):
    """A bound flat is no excuse for silently dropping the dark the user picked:
    the surviving pick calibrates the run, and the dropped one still reports."""
    root = solved_library / "library"
    dark = _register(root, "dark", name="Gone Dark")
    calibration.delete_master(root, dark["id"])
    flat = _register(root, "flat", name="Fine Flat", exposure_s=None)

    opts = _stack_with_saved_defaults(
        solved_library,
        {"dark_master_id": dark["id"], "flat_master_id": flat["id"]},
        monkeypatch,
    )

    assert opts.dark_path is None
    assert opts.flat_path and opts.flat_path.endswith(flat["filename"])
    skips = _recorded_skips(solved_library)
    assert len(skips) == 1
    assert skips[0].startswith("Your saved master dark wasn't used:")


# --- The run also records a master that was applied but doesn't MATCH --------
#
# The mirror image of the skips above: the master binds and calibrates the run,
# so History happily reports "Calibrated with your master dark" — while a dark
# shot at another exposure over/under-subtracts its pedestal on every frame. The
# engine has always measured this; ``_stack_target`` stamps it so it is visible
# somewhere other than the server log.


def _recorded_warnings(data_root, run_id: int = 1) -> list[str]:
    """The mismatch sentences stamped on a run, as History reads them."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(lib.list_targets()[0].safe_name)
        try:
            raw = proj.get_meta(
                f"{pipeline.CALIBRATION_WARNINGS_META_PREFIX}{run_id}")
        finally:
            proj.close()
    finally:
        lib.close()
    return json.loads(raw) if raw else []


def _stack_returning_warnings(monkeypatch, warnings: list[str]):
    """Patch run_stack to return a result carrying ``warnings``."""
    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=3, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
            calibration_warnings=list(warnings),
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)


def _run_stack_target(data_root):
    lib = Library.open_or_create(data_root / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        settings = Settings(data_root=str(data_root))
        return pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="pipeline"),
                                      lib=lib, safe=safe)
    finally:
        lib.close()


def test_a_mismatched_master_is_recorded_on_the_run_and_the_job_result(
        solved_library, monkeypatch):
    warning = ("Master dark is 30s but your subs are 10s — its pedestal will be "
               "over-subtracted on every frame.")
    _stack_returning_warnings(monkeypatch, [warning])

    summary = _run_stack_target(solved_library)

    # Both surfaces the walk-away user actually looks at: the Jobs result that
    # lands when the unattended stack finishes, and History via the run record.
    assert summary["calibration_warnings"] == [warning]
    assert _recorded_warnings(solved_library) == [warning]


def test_a_matching_master_records_no_mismatch(solved_library, monkeypatch):
    """Nothing new appears on a healthy run: no key stamped, empty in the result."""
    _stack_returning_warnings(monkeypatch, [])

    summary = _run_stack_target(solved_library)

    assert summary["calibration_warnings"] == []
    assert _recorded_warnings(solved_library) == []


def test_an_older_result_without_the_field_degrades_to_no_warnings(
        solved_library, monkeypatch):
    """Upgrade-safety: a result object from before this existed (no attribute)
    must read as "nothing to say" rather than raise mid-job."""
    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=3, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)

    summary = _run_stack_target(solved_library)

    assert summary["calibration_warnings"] == []
    assert _recorded_warnings(solved_library) == []
