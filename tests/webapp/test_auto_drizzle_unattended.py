"""The posture that lets a hands-off stack drizzle itself, and its gates.

The owner noticed his finished pictures come out at the sensor's own resolution
and asked whether drizzle is ever used. It never was: ``StackOptions.drizzle``
defaults off and no unattended path set it, so super-resolution needed a box
ticked on the Stack form before every run. Asked what he wanted instead, he
chose **"Auto, when worth it"**.

The *decision* lives in the engine (``seestack.stack.autodrizzle``, pinned by
``tests/test_auto_drizzle.py``) because it needs the real output canvas. What is
pinned here is everything around it: the posture only reaches a run nobody is
watching, an explicit ``drizzle`` in the owner's own saved defaults always wins
(on **or** off), the manual Stack form is never touched, and the new setting
upgrades a live install the way §9 requires.
"""

from __future__ import annotations

import json

from seestack.io.library import Library
from webapp.walkaway import apply_auto_drizzle, drizzle_choice_expressed

# --- the option-blob rule ------------------------------------------------


def test_an_unattended_run_that_chose_nothing_gets_the_posture():
    assert apply_auto_drizzle({}, enabled=True, unattended=True) == {
        "auto_drizzle": True}


def test_the_setting_off_is_a_no_op_beyond_saying_so():
    """With the setting off every built blob is what it has always been — the
    posture is written ``False``, which is ``StackOptions``' own default, so no
    run changes."""
    assert apply_auto_drizzle({}, enabled=False, unattended=True) == {
        "auto_drizzle": False}


def test_an_attended_run_never_gets_it():
    """A stack a human set up uses exactly what they ticked, whatever the
    setting says — the same rule ``auto_reject_on_unattended`` follows."""
    assert apply_auto_drizzle({}, enabled=True, unattended=False) == {
        "auto_drizzle": False}


def test_a_saved_drizzle_wins_whichever_way_it_points():
    """Presence, not truthiness. An explicitly saved ``drizzle: false`` is as
    much a choice as a ``true`` one, and neither may be overruled."""
    for value in (True, False):
        out = apply_auto_drizzle({"drizzle": value}, enabled=True, unattended=True)
        assert out == {"drizzle": value, "auto_drizzle": False}


def test_the_posture_is_always_written_so_a_crafted_body_cannot_keep_one():
    """Written last and unconditionally, like ``unattended``: a stale saved
    default or a crafted POST carrying ``auto_drizzle: true`` on an attended run
    is overwritten, not honoured."""
    out = apply_auto_drizzle({"auto_drizzle": True}, enabled=True,
                             unattended=False)
    assert out["auto_drizzle"] is False


def test_the_presence_test_is_its_own_function_so_both_halves_read_one_rule():
    assert drizzle_choice_expressed({"drizzle": False}) is True
    assert drizzle_choice_expressed({"drizzle_scale": 2.0}) is False
    assert drizzle_choice_expressed({}) is False


def test_the_posture_is_not_a_form_field():
    """It says whether the *app* may choose, which only the server that started
    the job knows — so a settings PUT or a persisted ``default_stack_options``
    must not be able to carry it in. Same treatment as ``unattended`` and the
    calibration master paths."""
    from webapp.schemas import NON_FORM_KEYS, describable_keys, strip_non_form_keys

    assert "auto_drizzle" in NON_FORM_KEYS
    assert "auto_drizzle" not in describable_keys()
    assert strip_non_form_keys({"auto_drizzle": True, "drizzle": True}) == {
        "drizzle": True}


# --- the setting itself --------------------------------------------------


def test_the_setting_defaults_on(client):
    """Owner-approved default (2026-10-12): "Auto, when worth it" is the answer
    he chose, so a fresh install drizzles its deep dithered targets without
    anybody finding a switch."""
    assert client.get("/api/settings").json()["auto_drizzle"] is True


def test_the_setting_round_trips(client):
    client.put("/api/settings", json={"auto_drizzle": False})
    assert client.get("/api/settings").json()["auto_drizzle"] is False


def test_an_old_config_without_the_key_loads_and_comes_up_on(tmp_path):
    """§9's first clause: a ``config.json`` written before this setting existed
    must still load, keeping everything it holds. It comes up **on** — which is
    a deliberate behaviour change on a live install and is exactly what the
    owner signed off."""
    from webapp.config import SettingsStore

    state = tmp_path / "state"
    state.mkdir()
    (state / "config.json").write_text(json.dumps({
        "auto_stack": True, "auto_stack_min_frames": 5, "watcher_enabled": False,
    }))
    settings = SettingsStore(str(tmp_path)).get()
    assert settings.auto_drizzle is True
    assert settings.auto_stack is True
    assert settings.auto_stack_min_frames == 5


def test_a_stored_false_survives_the_upgrade(tmp_path):
    """And the other half: once he turns it off it stays off, through the
    full-model re-save the store does on every boot."""
    from webapp.config import Settings, SettingsStore

    state = tmp_path / "state"
    state.mkdir()
    (state / "config.json").write_text(json.dumps({"auto_drizzle": False}))
    settings = SettingsStore(str(tmp_path)).get()
    assert settings.auto_drizzle is False
    assert settings.auto_drizzle is not Settings().auto_drizzle
    assert SettingsStore(str(tmp_path)).get().auto_drizzle is False
    assert json.loads(
        (state / "config.json").read_text())["auto_drizzle"] is False


# --- the posture actually reaches the stack -------------------------------


def _capture_opts(monkeypatch):
    """Patch ``run_stack`` to record the ``StackOptions`` it is called with.
    Mirrors the harness in ``test_auto_reject_on_unattended.py``."""
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
                saved: dict | None = None, options=None, unattended=None):
    """One ``_stack_target`` run, returning the ``StackOptions`` the engine
    would have got."""
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
        settings = Settings(data_root=str(solved_library), auto_drizzle=on)
        pipeline._stack_target(settings, jm=_FakeJM(), job=Job(kind="pipeline"),
                               lib=lib, safe=safe, auto=auto, options=options,
                               unattended=unattended)
    finally:
        lib.close()
    return captured["opts"]


def test_the_walk_away_stack_carries_the_posture(solved_library, monkeypatch):
    opts = _stack_with(solved_library, monkeypatch, on=True, auto=True)
    assert opts.auto_drizzle is True
    # …and nothing else about the drizzle was decided here: the engine does that.
    assert opts.drizzle is False


def test_with_the_setting_off_it_does_not(solved_library, monkeypatch):
    opts = _stack_with(solved_library, monkeypatch, on=False, auto=True)
    assert opts.auto_drizzle is False


def test_a_target_that_saved_drizzle_off_keeps_its_own_answer(
        solved_library, monkeypatch):
    opts = _stack_with(solved_library, monkeypatch, on=True, auto=True,
                       saved={"drizzle": False})
    assert opts.auto_drizzle is False
    assert opts.drizzle is False


def test_the_manual_stack_form_is_never_given_the_posture(
        solved_library, monkeypatch):
    opts = _stack_with(solved_library, monkeypatch, on=True, auto=False,
                       options={"drizzle_scale": 1.5})
    assert opts.auto_drizzle is False


def test_reprocess_all_stands_down_on_its_own_replayed_options(
        solved_library, monkeypatch):
    """"Bring my pictures up to date" replays each target's prior run options,
    and ``StackOptions`` is persisted whole — so every replayed blob carries an
    explicit ``drizzle`` and the posture is never written. That is deliberate: a
    library-wide batch is the wrong place to start re-rendering every deep
    target at 2.25× the pixels, and it is the same reasoning that keeps ``auto``
    off there ("the reused options are the owner's own and must not be
    re-defaulted"). No special case implements it — the presence gate does."""
    from dataclasses import asdict

    from seestack.stack.stacker import StackOptions

    replayed = asdict(StackOptions())
    assert "drizzle" in replayed
    opts = _stack_with(solved_library, monkeypatch, on=True, auto=False,
                       options=replayed, unattended=True)
    assert opts.auto_drizzle is False


# --- the finished picture says what was decided ---------------------------


def _run_with_cards(solved_library, safe: str, cards: dict):
    """One stack run whose master FITS carries ``cards``, and its run id.

    Borrows ``test_stack_render``'s fixture helper so the row and the file this
    endpoint reads are the real ones, then stamps the provenance by hand — the
    engine's own stamping is pinned in ``tests/test_auto_drizzle_run.py``, and
    what is being tested here is the *reading*.
    """
    from astropy.io import fits

    from .test_stack_render import _make_run_with_fits

    _, run_id = _make_run_with_fits(solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            with fits.open(run.fits_path, mode="update") as hdul:
                hdul[0].header.update(cards)
        finally:
            proj.close()
    finally:
        lib.close()
    return run_id


def test_the_run_info_panel_is_told_what_auto_drizzle_chose(
        client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _run_with_cards(solved_library, safe, {
        "ADRZAUTO": True, "ADRZWHY": "deep_and_dithered", "ADRZBAR": 200,
        "ADRZSPP": 640, "ADRZDTH": 0.2713, "ADRZPNL": 4, "ADRZSCL": 1.5,
    })
    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    ad = body["auto_drizzle"]
    assert ad == {"drizzled": True, "reason": "deep_and_dithered", "bar": 200,
                  "samples_per_pixel": 640, "dither_px": 0.2713, "panels": 4,
                  "scale": 1.5}


def test_a_run_that_declined_is_reported_too_not_silently_dropped(
        client, solved_library):
    """The half that answers the owner's actual question. A picture that came
    back at the sensor's own resolution has to be able to say why, or the
    feature is invisible on exactly the runs he asked about."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _run_with_cards(solved_library, safe, {
        "ADRZAUTO": False, "ADRZWHY": "too_few_samples", "ADRZBAR": 200,
        "ADRZSPP": 85,
    })
    ad = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/info").json()["auto_drizzle"]
    assert ad["drizzled"] is False
    assert ad["reason"] == "too_few_samples"
    assert ad["samples_per_pixel"] == 85 and ad["bar"] == 200
    # Nothing is invented for the measurement the run never took.
    assert "dither_px" not in ad and "scale" not in ad


def test_a_run_with_no_cards_reports_nothing(client, solved_library):
    """An attended run, and every master written before the feature."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _run_with_cards(solved_library, safe, {})
    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/info").json()
    assert body["auto_drizzle"] is None
