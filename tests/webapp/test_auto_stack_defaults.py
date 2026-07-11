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


class _FakeJM:
    """Minimal JobManager stand-in for progress flushing."""

    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass
