"""The stack passes bound their in-flight aligned/prepared frame buffers to the RAM
left after the canvas arrays the OOM guard charged.

``_pass``/``_drizzle_pass`` keep up to ``max_workers·2`` reprojected frame buffers
alive at once, each ~one native reference frame. The OOM guard's peak estimate
(:func:`_estimate_peak_bytes`) charges only the *canvas* arrays and never this
per-worker term, so on a many-core box with a large sensor those buffers could OOM a
run the guard just certified "safe". :func:`_memory_bounded_in_flight` caps the
in-flight count to ``headroom // per_frame_bytes`` — preventing the OOM at the cost of
throughput only, never below 2, and inert for the Seestar target.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow
from seestack.stack import stacker
from seestack.stack.stacker import (
    StackOptions,
    _estimate_peak_bytes,
    _memory_bounded_in_flight,
    _pass,
)

# A typical Seestar OSC frame (H, W). Native ~25 MB as RGB float32.
SEESTAR = (1080, 1920)
# A large-sensor frame (24 MP) — the case the guard hole can actually bite.
BIG = (4000, 6000)


def test_inert_for_the_seestar_target():
    # Small frame + a generous budget → the cap never binds: the caller's
    # requested ceiling (max_workers·2) is returned unchanged.
    got = _memory_bounded_in_flight(SEESTAR, SEESTAR, max_in_flight=64,
                                    memory_budget_gb=8.0)
    assert got == 64


def test_never_returns_more_than_the_requested_ceiling():
    # Even with an enormous budget the function is a *cap*, never an inflator.
    got = _memory_bounded_in_flight(SEESTAR, SEESTAR, max_in_flight=12,
                                    memory_budget_gb=1000.0)
    assert got == 12


def test_caps_below_the_ceiling_when_buffers_would_exceed_headroom():
    # Big sensor: canvas peak ~1.15 GB, per-frame buffer ~288 MB. With a 3 GB
    # budget only a handful of buffers fit in the ~1.85 GB of headroom, so the
    # bare max_workers·2=64 ceiling (which would OOM) is trimmed well below it.
    canvas_peak, _ = _estimate_peak_bytes(BIG, drizzle=False, drizzle_scale=1.0)
    per_frame = BIG[0] * BIG[1] * 3 * 4
    budget = 3.0 * 1e9
    expected = int((budget - canvas_peak) // per_frame)
    got = _memory_bounded_in_flight(BIG, BIG, max_in_flight=64,
                                    memory_budget_gb=3.0)
    assert 2 <= got < 64
    assert got == max(2, expected)


def test_floors_at_two_when_headroom_is_nearly_exhausted():
    # Canvas peak (~1.15 GB) almost fills a 1.3 GB budget — the guard still
    # passes the run, but there is barely room for one buffer. The cap must floor
    # at 2 (never 0/1), so the pass keeps a little pipelining instead of deadlocking.
    got = _memory_bounded_in_flight(BIG, BIG, max_in_flight=64,
                                    memory_budget_gb=1.3)
    assert got == 2


def test_drizzle_per_frame_buffer_is_native_not_scaled():
    # Drizzle enlarges only the canvas, not the per-frame worker buffer (which
    # stays ~the native reference frame). So a larger scale shrinks headroom via a
    # bigger canvas peak and lowers the cap, while per_frame_bytes is unchanged.
    at_1 = _memory_bounded_in_flight(BIG, BIG, max_in_flight=64, drizzle=True,
                                     drizzle_scale=1.0, memory_budget_gb=6.0)
    at_2 = _memory_bounded_in_flight(BIG, BIG, max_in_flight=64, drizzle=True,
                                     drizzle_scale=2.0, memory_budget_gb=6.0)
    assert at_2 <= at_1
    assert at_1 >= 2 and at_2 >= 2


def test_pass_forwards_the_cap_to_imap_bounded(monkeypatch):
    # Wiring: the value the caller computes reaches the bounded work loop. With a
    # tiny explicit cap the pass must submit at most that many buffers at once,
    # regardless of the executor's worker count.
    frame = FrameRow(id=1, source_path="a.fit")
    win = np.ones((2, 2, 3), dtype=np.float32)
    monkeypatch.setattr(stacker, "_align_for_stack",
                        lambda *a, **k: (win.copy(), 0, 0, False))

    captured: dict[str, int] = {}
    real_imap = stacker._imap_bounded

    def spy(ex, fn, items, max_in_flight):
        captured["max_in_flight"] = max_in_flight
        return real_imap(ex, fn, items, max_in_flight)

    monkeypatch.setattr(stacker, "_imap_bounded", spy)

    _pass(
        [frame], frame, "wcs-text", (2, 2), {1: 1.0},
        options=StackOptions(max_workers=8),
        phase_label="Stack",
        consumer=lambda *a, **k: None,
        progress=lambda *a, **k: None,
        cancel=lambda: False,
        errors=[],
        max_in_flight=3,
    )
    assert captured["max_in_flight"] == 3


def test_pass_defaults_to_max_workers_times_two_when_uncapped(monkeypatch):
    # Backward-compatible: a caller (or test) that doesn't pass max_in_flight gets
    # the historical max_workers·2 bound.
    frame = FrameRow(id=1, source_path="a.fit")
    win = np.ones((2, 2, 3), dtype=np.float32)
    monkeypatch.setattr(stacker, "_align_for_stack",
                        lambda *a, **k: (win.copy(), 0, 0, False))

    captured: dict[str, int] = {}
    real_imap = stacker._imap_bounded

    def spy(ex, fn, items, max_in_flight):
        captured["max_in_flight"] = max_in_flight
        return real_imap(ex, fn, items, max_in_flight)

    monkeypatch.setattr(stacker, "_imap_bounded", spy)

    _pass(
        [frame], frame, "wcs-text", (2, 2), {1: 1.0},
        options=StackOptions(max_workers=5),
        phase_label="Stack",
        consumer=lambda *a, **k: None,
        progress=lambda *a, **k: None,
        cancel=lambda: False,
        errors=[],
    )
    assert captured["max_in_flight"] == 10  # 5 * 2
