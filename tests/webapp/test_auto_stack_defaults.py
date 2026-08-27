"""Auto-stack honors per-target 'Save as defaults' (web_stack_defaults meta)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from seestack.io.library import Library
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job
from webapp.schemas import STACK_DEFAULTS_META_KEY


def _capture_opts(monkeypatch):
    """Patch run_stack to record the StackOptions it's called with."""
    captured = {}

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        captured["opts"] = opts
        captured["memory_budget_gb"] = memory_budget_gb
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=0, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    return captured


def test_auto_stack_uses_per_target_defaults(solved_library, monkeypatch):
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        proj = lib.open_target(safe)
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY,
                          json.dumps({"sigma_kappa": 2.25, "output_name": "auto"}))
        finally:
            proj.close()

        settings = Settings(data_root=str(solved_library))
        job = Job(kind="pipeline")
        # options=None → auto-stack path, should pick up the per-target meta.
        pipeline._stack_target(settings, jm=_FakeJM(), job=job, lib=lib, safe=safe)
    finally:
        lib.close()

    assert captured["opts"].sigma_kappa == 2.25
    assert captured["opts"].output_name == "auto"


def test_manual_options_override_saved_defaults(solved_library, monkeypatch):
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        proj = lib.open_target(safe)
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY, json.dumps({"sigma_kappa": 2.25}))
        finally:
            proj.close()

        settings = Settings(data_root=str(solved_library))
        job = Job(kind="stack")
        # Explicit options (manual stack) win over the saved per-target defaults.
        pipeline._stack_target(settings, jm=_FakeJM(), job=job, lib=lib, safe=safe,
                               options={"sigma_kappa": 4.0})
    finally:
        lib.close()

    assert captured["opts"].sigma_kappa == 4.0


def test_malformed_saved_defaults_meta_falls_back_not_crash(
        solved_library, monkeypatch):
    """A valid-JSON *non-dict* web_stack_defaults row must not crash the auto-stack.

    The Stack form's writer only ever stores a dict, but a live install upgraded
    in place could carry a legacy / hand-edited / foreign-version meta row holding
    a JSON list or scalar. That survives json.loads, so before the guard
    ``opts_dict.update(saved)`` raised TypeError and failed the whole walk-away
    stack for that target. It must instead fall back to the plain defaults.
    """
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        proj = lib.open_target(safe)
        try:
            # A JSON array — valid JSON, not a dict.
            proj.set_meta(STACK_DEFAULTS_META_KEY, json.dumps([1, 2, 3]))
        finally:
            proj.close()

        settings = Settings(data_root=str(solved_library))
        job = Job(kind="pipeline")
        # options=None → auto-stack path; must not raise on the malformed row.
        pipeline._stack_target(settings, jm=_FakeJM(), job=job, lib=lib, safe=safe)
    finally:
        lib.close()

    # It ran (run_stack was reached) with plain-default options rather than dying.
    assert "opts" in captured


def test_global_default_calibration_paths_never_reach_the_stacker(
        solved_library, monkeypatch):
    """A calibration master *path* in the global default_stack_options must not
    reach run_stack: those paths are resolved server-side from master ids, so a
    raw path there is a leaked client value (schemas.NON_FORM_KEYS). This guards
    both a maliciously-crafted settings PUT and an already-persisted config."""
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        # Simulate a config that (via an old/crafted settings PUT) carries raw
        # calibration paths in its global defaults, alongside a normal setting.
        settings = Settings(
            data_root=str(solved_library),
            default_stack_options={
                "dark_path": "/etc/shadow",
                "flat_path": "/evil.fits",
                "flat_dark_path": "/x",
                "bias_path": "/y",
                "sigma_kappa": 2.5,
            },
        )
        job = Job(kind="pipeline")
        pipeline._stack_target(settings, jm=_FakeJM(), job=job, lib=lib, safe=safe)
    finally:
        lib.close()

    # The legitimate form field flows through; every NON_FORM_KEYS path is dropped.
    assert captured["opts"].sigma_kappa == 2.5
    assert captured["opts"].dark_path is None
    assert captured["opts"].flat_path is None
    assert captured["opts"].flat_dark_path is None
    assert captured["opts"].bias_path is None


def test_unattended_posture_is_set_only_by_the_walk_away_path(
        solved_library, monkeypatch):
    """``StackOptions.unattended`` says "nobody is watching this run" and nothing
    else. It must be True exactly when ``_stack_target`` was called with
    ``auto=True`` (the watcher auto-stack / Process target), and False for the
    manual Stack form and reprocess-all — the engine decides between "refuse with
    a fix a human can click" and "degrade quietly and still make a picture" on it.
    """
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        settings = Settings(data_root=str(solved_library))
        pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="pipeline"),
                               lib=lib, safe=safe, auto=True)
        assert captured["opts"].unattended is True
        pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="stack"),
                               lib=lib, safe=safe, options={"sigma_kappa": 4.0})
        assert captured["opts"].unattended is False
    finally:
        lib.close()


def test_unattended_cannot_be_spoofed_by_stored_or_posted_options(
        solved_library, monkeypatch):
    """Only the server knows whether a human is watching, so every route a
    ``StackOptions`` dict can arrive by must lose its ``unattended`` value: a
    crafted POST body, a saved per-target default, the global config blob (which
    ``strip_non_form_keys`` drops), and the prior-run option blob reprocess-all
    replays. The posture is written last, so all four resolve to this run's own.
    """
    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        proj = lib.open_target(safe)
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY,
                          json.dumps({"unattended": True, "sigma_kappa": 2.25}))
        finally:
            proj.close()
        settings = Settings(
            data_root=str(solved_library),
            default_stack_options={"unattended": True, "sigma_kappa": 2.5},
        )
        # Manual stack: a posted body and a poisoned saved default both lose.
        pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="stack"),
                               lib=lib, safe=safe,
                               options={"unattended": True, "sigma_kappa": 4.0})
        assert captured["opts"].unattended is False
        assert captured["opts"].sigma_kappa == 4.0   # the real knob still flows
        # Auto-stack reading the poisoned per-target meta: still exactly the
        # posture of *this* run, which here happens to agree.
        pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="pipeline"),
                               lib=lib, safe=safe, auto=True)
        assert captured["opts"].unattended is True
        assert captured["opts"].sigma_kappa == 2.25
    finally:
        lib.close()


class _FakeJM:
    """Minimal JobManager stand-in for progress flushing."""

    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass
