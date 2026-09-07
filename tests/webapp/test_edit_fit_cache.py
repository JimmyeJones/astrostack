"""The live preview stops re-measuring what it measured a moment ago.

Several editor ops measure the whole image before they touch a pixel — the
stretch's robust per-channel stats, the tone curve's derived points, colour
calibration's star solve. Every render used to redo all of that from the top,
so dragging one slider re-solved a star field that could not have changed, on
every debounced frame, and twice over (the preview PNG and the histogram are
two requests running the same recipe on the same proxy).

``webapp.edit_fit_cache`` carries those measurements from one render to the
next, but only for the **longest common prefix** of enabled ops — the safety
rule these tests exist to pin. The pure half checks the prefix arithmetic; the
endpoint half checks that a repeat render really skips the measurement *and*
returns byte-identical bytes, and that a change to the first op re-measures.
"""

from __future__ import annotations

import base64
import json

import pytest

from seestack.edit.recipe import recipe_from_dict
from webapp import edit_fit_cache

from .test_editor import _make_run


def _enc(recipe: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(recipe).encode()).decode()


def _rec(*ops):
    return recipe_from_dict({"ops": list(ops)})


@pytest.fixture(autouse=True)
def _clean_cache():
    edit_fit_cache.clear()
    yield
    edit_fit_cache.clear()


# --- the prefix arithmetic -------------------------------------------------

def test_disabled_ops_are_not_part_of_the_fingerprint():
    """A switched-off op changes no pixel, so editing it must not break reuse."""
    a = _rec({"id": "tone.stretch", "params": {"target_bg": 0.2}},
             {"id": "tone.curves", "params": {"points": [[0, 0], [1, 1]]},
              "enabled": False})
    b = _rec({"id": "tone.stretch", "params": {"target_bg": 0.2}})
    fa, fb = edit_fit_cache.op_fingerprints(a), edit_fit_cache.op_fingerprints(b)
    assert len(fa) == 1
    # Only the uid differs (recipe_from_dict mints one per op), so the ids and
    # params — the parts that decide what an op measures — agree.
    assert [(o[1], o[2]) for o in fa] == [(o[1], o[2]) for o in fb]


def test_param_order_is_not_a_change():
    a = _rec({"id": "tone.stretch", "params": {"target_bg": 0.2, "mode": "stf"}})
    b = _rec({"id": "tone.stretch", "params": {"mode": "stf", "target_bg": 0.2}})
    assert (edit_fit_cache.op_fingerprints(a)[0][2]
            == edit_fit_cache.op_fingerprints(b)[0][2])


def test_only_the_unchanged_leading_ops_are_offered_back():
    """The rule: a fit is reusable only when the op's params *and its input* are
    unchanged, so the first difference ends the prefix."""
    key = edit_fit_cache.render_key("/p", 1, proxy_scale=2.0,
                                    proxy_shape=(10, 20), already_display=False)
    stored = (("u1", "tone.stretch", "{}"), ("u2", "tone.curves", "{}"),
              ("u3", "detail.sharpen", "{}"))
    edit_fit_cache.remember(key, stored, {
        "u1:stretch_stats": "S", "u2:points": "P", "u3:whatever": "W"})

    # Second op's params changed: the first op's fit survives, the rest don't.
    changed = (("u1", "tone.stretch", "{}"), ("u2", "tone.curves", '{"x":1}'),
               ("u3", "detail.sharpen", "{}"))
    assert edit_fit_cache.frozen_fits_for(key, changed) == {"u1:stretch_stats": "S"}

    # Identical recipe: everything is reusable.
    assert edit_fit_cache.frozen_fits_for(key, stored) == {
        "u1:stretch_stats": "S", "u2:points": "P", "u3:whatever": "W"}

    # First op changed: nothing is, and the answer is None (what EditContext
    # reads as "the caller supplied no fits"), never an empty dict.
    first = (("u1", "tone.stretch", '{"x":1}'),) + stored[1:]
    assert edit_fit_cache.frozen_fits_for(key, first) is None


def test_a_freshly_minted_uid_still_reuses_the_measurement():
    """A recipe posted without uids gets new ones every request, so matching on
    the uid would make the carry a permanent miss. The values come back re-keyed
    onto *this* render's uids, which is what ``EditContext`` looks them up by."""
    key = edit_fit_cache.render_key("/p", 1, proxy_scale=2.0,
                                    proxy_shape=(10, 20), already_display=False)
    edit_fit_cache.remember(key, (("old1", "tone.stretch", "{}"),),
                            {"old1:stretch_stats": "S"})
    assert edit_fit_cache.frozen_fits_for(
        key, (("new1", "tone.stretch", "{}"),)) == {"new1:stretch_stats": "S"}
    # …but only when the op itself still matches.
    assert edit_fit_cache.frozen_fits_for(
        key, (("new1", "tone.curves", "{}"),)) is None


def test_a_different_proxy_geometry_never_shares_a_key():
    """A windowed or rescaled render measures different pixels, so it must miss."""
    fps = (("u1", "tone.stretch", "{}"),)
    k1 = edit_fit_cache.render_key("/p", 1, proxy_scale=2.0,
                                   proxy_shape=(10, 20), already_display=False)
    edit_fit_cache.remember(k1, fps, {"u1:stretch_stats": "S"})
    for other in (
        edit_fit_cache.render_key("/p", 1, proxy_scale=4.0,
                                  proxy_shape=(10, 20), already_display=False),
        edit_fit_cache.render_key("/p", 1, proxy_scale=2.0,
                                  proxy_shape=(5, 20), already_display=False),
        edit_fit_cache.render_key("/p", 1, proxy_scale=2.0,
                                  proxy_shape=(10, 20), already_display=True),
        edit_fit_cache.render_key("/p", 2, proxy_scale=2.0,
                                  proxy_shape=(10, 20), already_display=False),
        edit_fit_cache.render_key("/q", 1, proxy_scale=2.0,
                                  proxy_shape=(10, 20), already_display=False),
    ):
        assert edit_fit_cache.frozen_fits_for(other, fps) is None


def test_the_store_stays_bounded():
    fps = (("u1", "tone.stretch", "{}"),)
    keys = [edit_fit_cache.render_key("/p", i, proxy_scale=1.0,
                                      proxy_shape=(4, 4), already_display=False)
            for i in range(edit_fit_cache.MAX_ENTRIES + 3)]
    for k in keys:
        edit_fit_cache.remember(k, fps, {"u1:stretch_stats": "S"})
    live = [k for k in keys if edit_fit_cache.frozen_fits_for(k, fps) is not None]
    assert len(live) == edit_fit_cache.MAX_ENTRIES
    assert keys[0] not in live  # oldest evicted first


# --- what it buys the editor, end to end -----------------------------------

def _count_stretch_measurements(monkeypatch) -> list[int]:
    """Count how often the stretch actually measures the image.

    ``tone._stretch`` imports it from ``render.thumbnail`` inside the call, so
    patching the module attribute is what the op will see."""
    from seestack.render import thumbnail

    calls = [0]
    real = thumbnail.measure_stretch_stats

    def counted(src, *a, **kw):
        calls[0] += 1
        return real(src, *a, **kw)

    monkeypatch.setattr(thumbnail, "measure_stretch_stats", counted)
    return calls


def test_a_repeat_render_reuses_the_measurement_and_returns_the_same_bytes(
        client, solved_library, monkeypatch):
    """Fail-before: the second identical preview re-measured the whole image."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    q = _enc({"ops": [
        {"id": "tone.stretch", "params": {"mode": "stf", "target_bg": 0.2}},
        {"id": "tone.curves", "params": {"points": [[0, 0], [0.5, 0.6], [1, 1]]}},
    ]})
    url = f"/api/targets/{safe}/stack-runs/{rid}/editor/preview?recipe={q}"

    calls = _count_stretch_measurements(monkeypatch)
    first = client.get(url)
    assert first.status_code == 200
    assert calls[0] == 1
    second = client.get(url)
    assert second.status_code == 200
    # The measurement was carried, not redone…
    assert calls[0] == 1
    # …and the picture is the same picture, byte for byte.
    assert second.content == first.content


def test_the_histogram_beside_it_shares_the_same_measurement(
        client, solved_library, monkeypatch):
    """The two requests the editor always fires together stop doing it twice."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    q = _enc({"ops": [
        {"id": "tone.stretch", "params": {"mode": "stf", "target_bg": 0.2}}]})
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor"

    calls = _count_stretch_measurements(monkeypatch)
    assert client.get(f"{base}/preview?recipe={q}").status_code == 200
    hist = client.get(f"{base}/histogram?recipe={q}").json()
    assert calls[0] == 1
    assert sum(hist["r"]) > 0  # and it is a real histogram, not a blank one


def test_changing_the_first_op_re_measures_rather_than_reusing_a_stale_fit(
        client, solved_library, monkeypatch):
    """The correctness half: a changed op invalidates its own fit."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor"

    def preview(target_bg: float):
        q = _enc({"ops": [{"id": "tone.stretch",
                           "params": {"mode": "stf", "target_bg": target_bg}}]})
        r = client.get(f"{base}/preview?recipe={q}")
        assert r.status_code == 200
        return r.content

    calls = _count_stretch_measurements(monkeypatch)
    dim = preview(0.12)
    bright = preview(0.40)
    assert calls[0] == 2          # the changed op measured again
    assert dim != bright          # and the change reached the picture


def test_a_change_below_an_op_still_reuses_the_op_above_it(
        client, solved_library, monkeypatch):
    """The win: dragging the last slider stops re-measuring everything above it,
    and still renders exactly what a cold render would."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid = _make_run(solved_library, safe)
    base = f"/api/targets/{safe}/stack-runs/{rid}/editor"
    stretch = {"id": "tone.stretch", "params": {"mode": "stf", "target_bg": 0.2},
               "uid": "aaaa"}

    def preview(sat: float):
        q = _enc({"ops": [stretch,
                          {"id": "tone.saturation", "params": {"amount": sat},
                           "uid": "bbbb"}]})
        r = client.get(f"{base}/preview?recipe={q}")
        assert r.status_code == 200
        return r.content

    calls = _count_stretch_measurements(monkeypatch)
    preview(1.0)
    warm = preview(1.6)
    assert calls[0] == 1  # the stretch above the changed op measured once

    # Cold: the same recipe with nothing carried forward must render the same.
    edit_fit_cache.clear()
    cold = preview(1.6)
    assert warm == cold
