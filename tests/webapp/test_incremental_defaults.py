""""Add new subs to the last stack" is a per-target choice that the walk-away
auto-stack honours, and an upgrade never turns it on by itself (AGENTS.md §9)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

from seestack.io.library import Library
from seestack.stack.stacker import StackOptions
from webapp import pipeline
from webapp.config import Settings, SettingsStore
from webapp.jobs import Job
from webapp.schemas import STACK_DEFAULTS_META_KEY, coerce_stack_options, stack_option_fields


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _capture(monkeypatch) -> dict:
    captured: dict = {}

    def fake_run_stack(proj, opts, **_kw):  # noqa: ANN001
        captured["opts"] = opts
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=0, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    return captured


def _save_defaults(lib: Library, safe: str, saved: dict) -> None:
    proj = lib.open_target(safe)
    try:
        proj.set_meta(STACK_DEFAULTS_META_KEY, json.dumps(saved))
    finally:
        proj.close()


def test_the_switch_is_off_by_default_and_lives_under_advanced():
    assert StackOptions().incremental is False
    field = next(f for f in stack_option_fields() if f.key == "incremental")
    assert field.group == "advanced" and field.type == "bool"
    assert field.default is False
    assert field.label == "Add new subs to the last stack (much faster)"
    assert "only the subs that are new" in (field.help or "")


def test_old_config_and_old_saved_options_load_with_it_off(tmp_path):
    # A config.json from before the option existed, carrying global stack defaults.
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "config.json").write_text(json.dumps({
        "auto_stack": True,
        "default_stack_options": {"sigma_kappa": 2.5, "quality_weighted": True},
    }))
    s = SettingsStore(str(tmp_path)).get()
    assert s.default_stack_options["sigma_kappa"] == 2.5
    opts = coerce_stack_options(dict(s.default_stack_options))
    assert opts.incremental is False and opts.sigma_kappa == 2.5
    # An old run record's options (reused by reprocess-all / "use these again").
    old_record = {k: v for k, v in vars(StackOptions()).items() if k != "incremental"}
    assert coerce_stack_options(old_record).incremental is False
    # …and a new run record's extra provenance keys are ignored when reused.
    new_record = dict(old_record, incremental=True, incremental_added=12,
                      incremental_base=300)
    assert coerce_stack_options(new_record).incremental is True


def test_auto_stack_without_a_saved_choice_stays_full(solved_library, monkeypatch):
    captured = _capture(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        _save_defaults(lib, safe, {"sigma_kappa": 2.25})  # saved before the option
        pipeline._stack_target(Settings(data_root=str(solved_library)), jm=_FakeJM(),
                               job=Job(kind="pipeline"), lib=lib, safe=safe, auto=True)
    finally:
        lib.close()
    assert captured["opts"].incremental is False


def test_auto_stack_honours_the_saved_per_target_choice(solved_library, monkeypatch):
    captured = _capture(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        _save_defaults(lib, safe, {"incremental": True})
        pipeline._stack_target(Settings(data_root=str(solved_library)), jm=_FakeJM(),
                               job=Job(kind="pipeline"), lib=lib, safe=safe, auto=True)
    finally:
        lib.close()
    assert captured["opts"].incremental is True
    assert captured["opts"].unattended is True


def test_walk_away_stacks_add_tonights_subs_and_never_touch_incoming(solved_library):
    """End to end through the walk-away chain's own entry point: the saved
    per-target choice reaches the engine, the second run adds the one new sub to
    the saved sums, the job summary says so, and ``incoming/`` is untouched."""
    incoming = solved_library / "incoming"

    def snapshot() -> dict:
        out = {}
        for root, _dirs, files in os.walk(incoming):
            for name in files:
                st = os.stat(os.path.join(root, name))
                out[os.path.join(root, name)] = (st.st_size, st.st_mtime_ns)
        return out

    before = snapshot()
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        _save_defaults(lib, safe, {"incremental": True, "sigma_clip": False,
                                   "background_flatten": False, "max_workers": 2})
        proj = lib.open_target(safe)
        try:
            frames = list(proj.iter_frames())
            assert len(frames) == 3
            proj.update_frame(frames[-1].id, accept=False)  # "tonight's" sub
        finally:
            proj.close()
        settings = Settings(data_root=str(solved_library))
        first = pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="pipeline"),
                                       lib=lib, safe=safe, auto=True)
        assert first["incremental_added"] is None
        assert "no saved state" in first["incremental_reason"]
        proj = lib.open_target(safe)
        try:
            proj.update_frame(frames[-1].id, accept=True)
            sidecar = proj.project_dir / "output" / "master_incremental.npz"
            assert sidecar.is_file()
        finally:
            proj.close()
        second = pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="pipeline"),
                                        lib=lib, safe=safe, auto=True)
    finally:
        lib.close()
    assert second["incremental_added"] == 1, second.get("incremental_reason")
    assert second["n_frames_used"] == 3
    assert snapshot() == before
