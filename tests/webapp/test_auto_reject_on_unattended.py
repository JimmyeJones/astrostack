"""The opt-in that lets a hands-off stack pick its own outlier removal.

The unattended chain already picks a method when nobody chose one — but a saved
choice is honoured verbatim, and that is a decision made **once, at one depth**,
then applied to every night after it. κ-σ dispatches from 4 subs and is blind to
a lone satellite trail until ``kappa_min_frames`` (11 at the default κ=3), so an
owner who once saved ``sigma_clip`` gets plain κ-σ on every walk-away stack,
removing nothing on any night — or, for a mosaic, any panel — thinner than that.

``Settings.auto_reject_on_unattended`` is the opt-in that hands the choice back
to ``auto_reject``, which picks per stack from the real per-pixel depth. It is
**off by default**: overruling a setting the user took control of is a pixel
change on the hot path, so it only ever happens because they asked.

These pin all three halves — the option-blob rule, the config's default and its
upgrade, and the fact that the "before the night" surfaces stay honest once it
is on (with the app choosing again, ``user_chose`` goes false and the Target
page's warning and the Stack form's save clause both correctly fall silent).
"""

from __future__ import annotations

from dataclasses import replace

from seestack.io.library import Library
from webapp.walkaway import apply_unattended_rejection


# --- the option-blob rule ------------------------------------------------


def test_off_by_default_a_saved_method_is_still_honoured_verbatim():
    """The guarantee that makes this safe to ship: with the flag off, the built
    options are byte-for-byte what they have always been."""
    opts = {"sigma_clip": True}
    assert apply_unattended_rejection(dict(opts)) == opts
    assert apply_unattended_rejection(dict(opts), override_saved_choice=False) == opts


def test_on_it_hands_a_saved_method_back_to_auto():
    out = apply_unattended_rejection({"sigma_clip": True}, override_saved_choice=True)
    assert out["auto_reject"] is True
    # The stale pick is dropped, not left to contradict the record.
    # ``_resolve_auto_reject`` overwrites both from the frame count anyway, so no
    # pixel moves — but the run record must not claim a method the run didn't use.
    assert "sigma_clip" not in out
    assert "min_max_reject" not in out


def test_on_it_also_supersedes_a_saved_min_max_pick():
    out = apply_unattended_rejection(
        {"min_max_reject": True}, override_saved_choice=True)
    assert out["auto_reject"] is True
    assert "min_max_reject" not in out


def test_on_it_supersedes_an_explicit_no_rejection_too():
    """``sigma_clip: false`` is a choice, and the flag's whole meaning is "choose
    for me on the hands-off path" — so it is superseded like any other. This is
    exactly why the flag is opt-in rather than a widening of the existing guard.
    """
    out = apply_unattended_rejection(
        {"sigma_clip": False, "min_max_reject": False}, override_saved_choice=True)
    assert out["auto_reject"] is True
    assert "sigma_clip" not in out


def test_on_it_changes_nothing_for_a_target_that_never_chose():
    """Nothing saved → the existing injection already did this. The flag must not
    make a second, different decision for the majority of targets."""
    plain = apply_unattended_rejection({})
    forced = apply_unattended_rejection({}, override_saved_choice=True)
    assert plain == forced == {"auto_reject": True}


def test_the_drizzle_gate_is_untouched_either_way():
    """``drizzle_reject`` has its own rule; the flag is about method choice only."""
    for override in (False, True):
        out = apply_unattended_rejection(
            {"drizzle": True, "sigma_clip": True, "drizzle_reject": False},
            override_saved_choice=override)
        assert out["drizzle_reject"] is False, override
    out = apply_unattended_rejection(
        {"drizzle": True, "sigma_clip": True}, override_saved_choice=True)
    assert out["drizzle_reject"] is True


# --- the setting itself --------------------------------------------------


def test_the_setting_defaults_off(client):
    assert client.get("/api/settings").json()["auto_reject_on_unattended"] is False


def test_the_setting_round_trips(client):
    client.put("/api/settings", json={"auto_reject_on_unattended": True})
    assert client.get("/api/settings").json()["auto_reject_on_unattended"] is True


def test_an_old_config_without_the_key_still_loads_and_reads_off(tmp_path):
    """§9: a ``config.json`` written before this setting existed must load, and
    must reproduce today's behaviour rather than opting the owner in."""
    import json

    from webapp.config import SettingsStore

    state = tmp_path / "state"
    state.mkdir()
    (state / "config.json").write_text(json.dumps({
        "auto_stack": True, "auto_stack_min_frames": 5, "watcher_enabled": False,
    }))
    settings = SettingsStore(str(tmp_path)).get()
    assert settings.auto_reject_on_unattended is False
    # And the pre-existing keys survive untouched.
    assert settings.auto_stack is True
    assert settings.auto_stack_min_frames == 5


# --- the "before the night" surfaces stay honest --------------------------


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


def _frames_at(data_root, safe: str, ra: float, dec: float, count: int) -> None:
    """Re-point the target's frames, cloning rows until the pointing has N."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            rows = list(proj.iter_frames())
            template = rows[0]
            for r in rows:
                proj.update_frame(r.id, accept=False)
            for i in range(count):
                proj.add_frame(replace(
                    template, id=None, accept=True,
                    source_path=f"{template.source_path}.{i:03d}",
                    ra_center_deg=ra, dec_center_deg=dec,
                ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_the_outlook_stops_warning_once_the_app_is_choosing_again(
        client, solved_library):
    """The same 6-sub target with sigma clipping saved. Off: the app says the
    saved setting is blind, and calls it the user's. On: the app is choosing
    again, so it reaches, and ``user_chose`` goes false — which is what makes
    both the Target-page note and the Stack form's save clause fall silent
    instead of warning about a setting that is no longer in force.
    """
    safe = _safe(client)
    _frames_at(solved_library, safe, 83.6, -5.4, 6)
    client.put(f"/api/targets/{safe}/stack-defaults", json={"sigma_clip": True})

    before = client.get(f"/api/targets/{safe}/rejection-outlook").json()
    assert before["method"] == "sigma-clip"
    assert before["reaches"] is False
    assert before["user_chose"] is True

    client.put("/api/settings", json={"auto_reject_on_unattended": True})
    after = client.get(f"/api/targets/{safe}/rejection-outlook").json()
    # ``auto_reject`` resolves to min/max down here, which does drop a lone trail.
    assert after["method"] == "min-max-reject"
    assert after["reaches"] is True
    assert after["user_chose"] is False


# --- the setting actually reaches the stack -------------------------------


def _capture_opts(monkeypatch):
    """Patch ``run_stack`` to record the ``StackOptions`` it is called with.
    Mirrors the harness in ``test_auto_stack_defaults.py``."""
    from types import SimpleNamespace

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


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _stack_with(solved_library, monkeypatch, *, on: bool, auto: bool,
                saved: dict | None = None, options=None):
    """One ``_stack_target`` run, returning the ``StackOptions`` the engine
    would have got. ``saved`` is the target's "Save as defaults" blob."""
    import json

    from webapp import pipeline
    from webapp.config import Settings
    from webapp.jobs import Job
    from webapp.schemas import STACK_DEFAULTS_META_KEY

    captured = _capture_opts(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        proj = lib.open_target(safe)
        try:
            proj.set_meta(STACK_DEFAULTS_META_KEY, json.dumps(saved or {}))
        finally:
            proj.close()
        settings = Settings(data_root=str(solved_library),
                            auto_reject_on_unattended=on)
        pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="pipeline"),
                               lib=lib, safe=safe, auto=auto, options=options)
    finally:
        lib.close()
    return captured["opts"]


def test_off_the_walk_away_stack_still_gets_the_saved_sigma_clip(
        solved_library, monkeypatch):
    opts = _stack_with(solved_library, monkeypatch, on=False, auto=True,
                       saved={"sigma_clip": True})
    assert opts.sigma_clip is True
    assert opts.auto_reject is False


def test_on_a_saved_min_max_pick_is_handed_back_to_auto(
        solved_library, monkeypatch):
    """The clearest case, because ``min_max_reject``'s engine default is False:
    with the flag on the saved pick is gone from the built options and
    ``auto_reject`` decides instead."""
    opts = _stack_with(solved_library, monkeypatch, on=True, auto=True,
                       saved={"min_max_reject": True})
    assert opts.auto_reject is True
    assert opts.min_max_reject is False
    # …and the guard that skips quality weighting for a rank-based min/max
    # combine now reads the live answer, so the run gets weighting back.
    assert opts.quality_weighted is True


def test_on_a_saved_choice_builds_exactly_what_never_choosing_builds(
        solved_library, monkeypatch):
    """The flag's whole meaning, asserted as an identity rather than field by
    field: a hands-off stack of a target that saved a method is built exactly
    like one whose owner never chose. (``sigma_clip``'s own engine default is
    True, so a field-by-field check would read as "the pick survived" when what
    actually happens is that ``_resolve_auto_reject`` decides both booleans from
    the frame count.)"""
    chose = _stack_with(solved_library, monkeypatch, on=True, auto=True,
                        saved={"sigma_clip": True})
    never = _stack_with(solved_library, monkeypatch, on=True, auto=True, saved={})
    assert chose == never
    assert chose.auto_reject is True


def test_on_the_manual_stack_form_is_still_honoured_verbatim(
        solved_library, monkeypatch):
    """The flag says *hands-off*. A stack a human set up and submitted keeps
    exactly what they picked, however the setting is left."""
    opts = _stack_with(solved_library, monkeypatch, on=True, auto=False,
                       saved={"sigma_clip": True},
                       options={"sigma_clip": True})
    assert opts.sigma_clip is True
    assert opts.auto_reject is False
