"""The live preview stops re-fitting the sky model it fitted a moment ago.

``webapp.edit_fit_cache`` carries a *number* an op measured. The three
``background.*`` ops fit a **spatial model** instead — a mesh over the whole
canvas, a per-coverage-level offset — so nothing was carried for them and every
debounced frame re-fitted the sky from the top, twice over (the preview PNG and
the histogram are two requests over the same recipe and the same proxy).

``webapp.edit_resume_cache`` stores the *picture* at the last additive
``background.*`` op and resumes there when the next recipe agrees op for op up to
that boundary. The pure half below pins the boundary arithmetic and the budget;
the endpoint half pins that a repeat render really skips the fit *and* returns
byte-identical bytes, that an edit below the boundary reuses while still
rendering what a cold render renders, and that an edit at or above it does not.
"""

from __future__ import annotations

import base64
import json

import numpy as np
import pytest

from seestack.edit.recipe import recipe_from_dict
from webapp import edit_fit_cache, edit_resume_cache

from .test_editor import _make_run

_GRADIENT = {"id": "background.final_gradient", "params": {"mode": "luminance"}}
_STRETCH = {"id": "tone.stretch", "params": {"mode": "stf", "target_bg": 0.2}}
_CURVES = {"id": "tone.curves", "params": {"points": [[0, 0], [0.5, 0.6], [1, 1]]}}


def _enc(recipe: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(recipe).encode()).decode()


def _rec(*ops):
    return recipe_from_dict({"ops": list(ops)})


def _ops(*ops):
    return edit_resume_cache.enabled_ops(_rec(*ops))


@pytest.fixture(autouse=True)
def _clean_caches():
    edit_fit_cache.clear()
    edit_resume_cache.clear()
    yield
    edit_fit_cache.clear()
    edit_resume_cache.clear()


# --- where the boundary goes ------------------------------------------------

def test_the_boundary_sits_after_the_last_additive_op():
    assert edit_resume_cache.boundary(_ops(
        {"id": "background.level_coverage", "params": {}},
        _GRADIENT, _STRETCH, _CURVES)) == 2


def test_a_recipe_with_no_additive_op_has_no_boundary():
    """Nothing above a tone op is a whole-canvas fit, so there is nothing to
    cache and the render stays exactly what it is today."""
    assert edit_resume_cache.boundary(_ops(_STRETCH, _CURVES)) == 0


def test_a_disabled_additive_op_does_not_move_the_boundary():
    """``apply_recipe`` filters disabled ops out before it runs anything, so a
    switched-off op is not a step — counting it would put the boundary one op
    further down than the array actually reaches."""
    assert edit_resume_cache.boundary(_ops(
        _GRADIENT, dict(_GRADIENT, enabled=False), _STRETCH)) == 1


def test_a_stretch_above_the_boundary_declines_the_whole_idea():
    """The pipeline's linear→nonlinear contract is per-call state, so splitting
    after a stretch would let the tail's own fallback stretch fire on an
    already-stretched picture. The frontend cannot build this; a posted recipe
    can."""
    assert edit_resume_cache.boundary(_ops(_STRETCH, _GRADIENT, _CURVES)) == 0


# --- the prefix match and the budget ----------------------------------------

def _key(run_id=1, scale=2.0, shape=(10, 20), display=False, path=None):
    return edit_resume_cache.render_key(
        "/p", run_id, path, proxy_scale=scale, proxy_shape=shape,
        already_display=display)


def _arr(h=4, w=4):
    return np.zeros((h, w, 3), dtype=np.float32)


def test_only_a_recipe_that_agrees_up_to_the_boundary_resumes():
    key = _key()
    stored = (("u1", "background.final_gradient", "{}"),
              ("u2", "tone.stretch", "{}"))
    edit_resume_cache.remember(key, stored, array=_arr(), n_ops=1)
    # A fresh uid is not a change — a recipe posted without one gets a new uid
    # per request, so matching on it would be a permanent miss.
    assert edit_resume_cache.resume_for(
        key, (("new", "background.final_gradient", "{}"),
              ("new2", "tone.curves", "{}"))) is not None
    # …but the op above the boundary itself has to still match.
    assert edit_resume_cache.resume_for(
        key, (("new", "background.final_gradient", '{"mode": "per_channel"}'),)) is None
    assert edit_resume_cache.resume_for(
        key, (("new", "background.subtract", "{}"),)) is None
    # And a recipe shorter than the boundary cannot resume past it.
    assert edit_resume_cache.resume_for(key, ()) is None


def test_a_different_picture_or_geometry_never_shares_a_key(tmp_path):
    fps = (("u1", "background.final_gradient", "{}"),)
    src = tmp_path / "master.fits"
    src.write_bytes(b"x" * 16)
    key = _key(path=src)
    edit_resume_cache.remember(key, fps, array=_arr(), n_ops=1)
    assert edit_resume_cache.resume_for(key, fps) is not None
    for other in (_key(scale=4.0, path=src), _key(shape=(5, 20), path=src),
                  _key(display=True, path=src), _key(run_id=2, path=src),
                  _key(path=None)):
        assert edit_resume_cache.resume_for(other, fps) is None
    # A rewritten master invalidates it even at the same shape and scale — an
    # array is a picture, not a measurement, so a stale one would be wrong
    # rather than slightly off.
    src.write_bytes(b"y" * 32)
    assert edit_resume_cache.resume_for(_key(path=src), fps) is None


def test_the_store_is_bounded_by_bytes_not_only_by_entries():
    """The budget this has to respect is the owner's RAM, so it is counted in
    bytes: one slot of the largest proxy the editor can build must not be able
    to push the store past its ceiling."""
    fps = (("u1", "background.final_gradient", "{}"),)
    side = int((edit_resume_cache.MAX_BYTES / 3 / 4 / 2) ** 0.5) + 1
    keys = [_key(run_id=i) for i in range(4)]
    for k in keys:
        edit_resume_cache.remember(k, fps, array=_arr(side, side), n_ops=1)
    live = [k for k in keys if edit_resume_cache.resume_for(k, fps) is not None]
    assert 0 < len(live) <= edit_resume_cache.MAX_ENTRIES
    assert keys[0] not in live  # oldest evicted first
    assert edit_resume_cache._total_bytes() <= edit_resume_cache.MAX_BYTES


def test_an_array_bigger_than_the_whole_budget_is_simply_not_cached():
    fps = (("u1", "background.final_gradient", "{}"),)
    side = int((edit_resume_cache.MAX_BYTES / 3 / 4) ** 0.5) + 64
    edit_resume_cache.remember(_key(), fps, array=_arr(side, side), n_ops=1)
    assert edit_resume_cache.resume_for(_key(), fps) is None


def test_carried_notes_are_re_keyed_onto_this_renders_uids():
    """``record_note`` keys a note by op uid, and a resumed render's uids are its
    own — so the carry travels by *position* and is re-keyed on arrival."""
    ops = _ops(_GRADIENT, _STRETCH)
    point = edit_resume_cache.ResumePoint(
        array=_arr(), n_ops=1,
        notes=((0, "background.final_gradient", {"mode_used": "luminance"}),
               (7, "nope", "out of range")))
    assert edit_resume_cache.notes_onto(point, ops) == {
        f"{ops[0].uid}:background.final_gradient": {"mode_used": "luminance"}}


# --- what it buys the editor, end to end ------------------------------------

def _count_gradient_fits(monkeypatch) -> list[int]:
    """How often the gradient op really fits a mesh.

    ``background._final_gradient`` imports ``remove_final_gradient`` from the
    engine module inside the call, so patching the module attribute is what the
    op will see."""
    from seestack.bg import final_gradient

    calls = [0]
    real = final_gradient.remove_final_gradient

    def counted(*a, **kw):
        calls[0] += 1
        return real(*a, **kw)

    monkeypatch.setattr(final_gradient, "remove_final_gradient", counted)
    return calls


def test_a_repeat_render_skips_the_sky_fit_and_returns_the_same_bytes(
        client, solved_library, monkeypatch):
    """Fail-before: the second identical preview re-fitted the whole canvas."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    q = _enc({"ops": [_GRADIENT, _STRETCH, _CURVES]})
    url = f"/api/targets/{safe}/stack-runs/{rid}/editor/preview?recipe={q}"

    calls = _count_gradient_fits(monkeypatch)
    first = client.get(url)
    assert first.status_code == 200
    assert calls[0] == 1
    second = client.get(url)
    assert second.status_code == 200
    # The fit was not redone…
    assert calls[0] == 1
    # …and the picture is the same picture, byte for byte.
    assert second.content == first.content


def test_the_histogram_beside_it_resumes_from_the_same_array(
        client, solved_library, monkeypatch):
    """The two requests the editor fires together stop fitting the sky twice."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    q = _enc({"ops": [_GRADIENT, _STRETCH]})
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor"

    calls = _count_gradient_fits(monkeypatch)
    assert client.get(f"{base}/preview?recipe={q}").status_code == 200
    hist = client.get(f"{base}/histogram?recipe={q}").json()
    assert calls[0] == 1
    assert sum(hist["r"]) > 0  # and a real histogram, not a blank one


def test_an_edit_below_the_boundary_reuses_and_still_renders_the_real_picture(
        client, solved_library, monkeypatch):
    """The claim that matters: resuming is a shortcut, not an approximation. The
    reused render has to equal what the same recipe renders from cold."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor/preview"
    warm_q = _enc({"ops": [_GRADIENT, _STRETCH,
                           {"id": "tone.saturation", "params": {"amount": 1.4}}]})

    calls = _count_gradient_fits(monkeypatch)
    assert client.get(f"{base}?recipe={_enc({'ops': [_GRADIENT, _STRETCH]})}"
                      ).status_code == 200
    assert calls[0] == 1
    warm = client.get(f"{base}?recipe={warm_q}")
    assert warm.status_code == 200
    assert calls[0] == 1                      # the sky fit was skipped…

    edit_resume_cache.clear()
    edit_fit_cache.clear()
    cold = client.get(f"{base}?recipe={warm_q}")
    assert cold.status_code == 200
    assert calls[0] == 2                      # …and this one really did re-fit
    assert warm.content == cold.content       # same picture either way


def test_an_edit_to_the_additive_op_itself_re_fits_and_changes_the_picture(
        client, solved_library, monkeypatch):
    """The other direction, and the one a stale array would get wrong: the op
    above the boundary is part of the key, so changing it cannot reuse."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor/preview"

    calls = _count_gradient_fits(monkeypatch)
    first = client.get(f"{base}?recipe={_enc({'ops': [_GRADIENT, _STRETCH]})}")
    assert first.status_code == 200
    assert calls[0] == 1
    changed = client.get(f"{base}?recipe=" + _enc({"ops": [
        {"id": "background.final_gradient", "params": {"mode": "per_channel"}},
        _STRETCH]}))
    assert changed.status_code == 200
    assert calls[0] == 2
    assert changed.content != first.content


def test_a_recipe_whose_op_failed_is_not_cached(client, solved_library,
                                                monkeypatch):
    """A failed op is *skipped*, so the array is not the picture the recipe
    makes — and the next render has to run it again so the editor can say so."""
    from seestack.bg import final_gradient

    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor"
    q = _enc({"ops": [_GRADIENT, _STRETCH]})

    def boom(*a, **kw):
        raise RuntimeError("no sky here")

    monkeypatch.setattr(final_gradient, "remove_final_gradient", boom)
    hist = client.get(f"{base}/histogram?recipe={q}").json()
    assert any("no sky here" in e for e in hist["errors"])
    monkeypatch.undo()

    calls = _count_gradient_fits(monkeypatch)
    again = client.get(f"{base}/histogram?recipe={q}").json()
    assert not again["errors"]
    assert calls[0] == 1   # it ran, rather than resuming the half-applied array
