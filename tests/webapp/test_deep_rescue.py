"""The on-demand deep-image rescue — "Try harder to locate these subs".

On a faint / star-poor target a single 10 s sub has too few stars for ASTAP, so
most subs stay accepted-but-un-located and the stack silently leaves them out.
The cure already existed (``seestack.solve.bootstrap``) but could only be reached
by finding a switch in Settings. These cover the two halves that make it a
button: the endpoint that runs it, and the server-side answer to "would it
actually do anything here?" that decides whether the button is offered at all.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest

from seestack.io.library import Library
from seestack.io.project import FrameRow
from seestack.solve.bootstrap import DEFAULT_MIN_FRAMES

from .conftest import FRAME_H, FRAME_W

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ for synth
from synth import write_seestar_fits  # noqa: E402, I001


_shape_calls = itertools.count()


def _shape_target(data_root, safe: str, *, n_unsolved: int, n_tried: int,
                  n_solved: int = 0) -> None:
    """Give ``safe`` a faint-field shape: ``n_unsolved`` accepted subs with no
    position, ``n_tried`` of which the solver has already been beaten on, and
    ``n_solved`` that did locate.

    The subs are written as real (tiny, synthetic) FITS rather than bare rows,
    because the rescue's own gate filters on whether a sub can be *read* right
    now — a target of unreadable rows would stand down for a reason that has
    nothing to do with the counts under test."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            # Start from a clean slate: the fixture's own three subs are solved
            # or not depending on which library fixture is in play.
            for f in proj.iter_frames():
                proj.update_frame(f.id, accept=False, reject_reason="user")
            gen = next(_shape_calls)  # source paths are unique, so re-shaping works
            faint = data_root / "faint" / str(gen)
            faint.mkdir(parents=True, exist_ok=True)
            for i in range(n_unsolved):
                path = faint / f"u{i:03d}.fit"
                write_seestar_fits(path, width=FRAME_W, height=FRAME_H,
                                   n_stars=30, seed=100 + i)
                fid = proj.add_frame(FrameRow(source_path=str(path)))
                if i < n_tried:
                    proj.update_frame(fid, reject_reason="solve_failed:no solution")
            for i in range(n_solved):
                path = faint / f"s{i:03d}.fit"
                write_seestar_fits(path, width=FRAME_W, height=FRAME_H,
                                   n_stars=30, seed=200 + i)
                fid = proj.add_frame(FrameRow(source_path=str(path)))
                proj.update_frame(fid, wcs_json="{}")
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def _offered(client, safe: str = "M_42") -> bool:
    body = client.get(f"/api/targets/{safe}/frames/reject-summary").json()
    return body["deep_rescue_offered"]


def test_the_rescue_is_offered_when_the_plate_solve_has_been_beaten(
    client, built_library, data_root,
):
    """The case the button exists for: plenty of subs, the solver ran on them and
    placed almost none."""
    _shape_target(data_root, "M_42", n_unsolved=DEFAULT_MIN_FRAMES,
                  n_tried=DEFAULT_MIN_FRAMES)
    assert _offered(client) is True


def test_the_rescue_is_not_offered_before_the_plate_solve_has_even_run(
    client, built_library, data_root,
):
    """A freshly-scanned target with automatic solving off has every sub
    un-located and none attempted. The rescue *would* engage there and would
    probably work — but it would hand each sub a position propagated from a
    neighbour where the ordinary solver would have given it its own verified one.
    The first move is the plate solve, so the button stays out of the way."""
    _shape_target(data_root, "M_42", n_unsolved=DEFAULT_MIN_FRAMES, n_tried=0)
    assert _offered(client) is False


def test_the_rescue_is_not_offered_once_enough_subs_are_located(
    client, built_library, data_root,
):
    """With a real stack's worth already located the rescue stands down, so
    offering it would start a job with nothing to do."""
    _shape_target(data_root, "M_42", n_unsolved=DEFAULT_MIN_FRAMES,
                  n_tried=DEFAULT_MIN_FRAMES, n_solved=DEFAULT_MIN_FRAMES)
    assert _offered(client) is False


def test_the_rescue_is_not_offered_with_too_few_subs_to_build_a_deep_image(
    client, built_library, data_root,
):
    """Below the floor the deep image wouldn't clear ASTAP's detection floor
    either — the honest answer is "shoot more", not a button."""
    n = DEFAULT_MIN_FRAMES - 1
    _shape_target(data_root, "M_42", n_unsolved=n, n_tried=n)
    assert _offered(client) is False


def test_an_ordinary_healthy_target_is_never_offered_the_rescue(
    client, solved_library,
):
    """The everyday case: every sub located. Nothing about the page changes."""
    assert _offered(client) is False


def test_the_offer_is_the_engines_own_gate_not_a_second_opinion(
    client, built_library, data_root,
):
    """Whatever the endpoint says, the rescue must agree — the whole reason the
    rule is one pure function rather than a copy beside the button.

    Walks the boundary: one sub short of the floor the endpoint declines and the
    rescue declines; at the floor both accept.
    """
    from seestack.solve.bootstrap import bootstrap_solve

    def _engine_verdict() -> bool:
        lib = Library.open_or_create(data_root / "library")
        try:
            proj = lib.open_target("M_42")
            try:
                # The injected solver never solves, so the rescue cannot get
                # past the deep image — but it does get past the *gate*, which
                # is the decision under test. Any reason other than the two gate
                # reasons means it engaged with these counts.
                res = bootstrap_solve(proj, deep_solver=lambda *a, **k: None)
                return res.reason not in (
                    "enough subs already solved",
                    "too few unsolved subs to bootstrap",
                )
            finally:
                proj.close()
        finally:
            lib.close()

    n = DEFAULT_MIN_FRAMES - 1
    _shape_target(data_root, "M_42", n_unsolved=n, n_tried=n)
    assert _offered(client) is False
    assert _engine_verdict() is False

    _shape_target(data_root, "M_42", n_unsolved=DEFAULT_MIN_FRAMES,
                  n_tried=DEFAULT_MIN_FRAMES)
    assert _offered(client) is True
    assert _engine_verdict() is True


def test_pressing_the_button_runs_the_rescue_and_not_a_second_solve_pass(
    client, built_library, data_root, monkeypatch,
):
    """The endpoint submits a job that runs *only* the rescue. Re-running the
    per-sub ladder that already failed on all of these subs would cost minutes
    and locate nothing new, so it must not happen."""
    import seestack.solve.bootstrap as bootstrap_mod
    from seestack.solve.bootstrap import BootstrapResult

    calls = {"bootstrap": 0}

    def _fake_bootstrap(project, **kwargs):
        calls["bootstrap"] += 1
        return BootstrapResult(engaged=True, deep_solved=True, n_propagated=6,
                               reason="rescued 6 sub(s) from a deep image")

    def _no_solving(*args, **kwargs):
        raise AssertionError("the per-sub solve ladder must not run")

    monkeypatch.setattr(bootstrap_mod, "bootstrap_solve", _fake_bootstrap)
    monkeypatch.setattr("seestack.solve.runner.solve_one", _no_solving)

    _shape_target(data_root, "M_42", n_unsolved=DEFAULT_MIN_FRAMES,
                  n_tried=DEFAULT_MIN_FRAMES)
    r = client.post("/api/targets/M_42/rescue-unsolved")
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    result = _await_job(client, job_id)
    assert calls["bootstrap"] == 1
    assert result["bootstrap_propagated"] == 6
    # Priced no solve pass at all: the progress counters are seeded by the engine
    # and stayed at zero, and the solve phase's own report never appeared.
    assert result["solve_total"] == 0
    assert result["qc_total"] == 0
    assert "solve_ok" not in result


def test_the_endpoint_refuses_an_unknown_target(client, built_library):
    assert client.post("/api/targets/not_a_target/rescue-unsolved").status_code == 404


def _await_job(client, job_id: str, timeout_s: float = 60.0) -> dict:
    """Block until the single-worker JobManager finishes ``job_id``."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "error", "cancelled", "interrupted"):
            assert job["state"] == "done", job
            return job.get("result") or {}
        time.sleep(0.05)
    pytest.fail(f"job {job_id} did not finish within {timeout_s}s")
