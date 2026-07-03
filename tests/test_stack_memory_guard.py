"""Pre-allocation memory guard: refuse oversized stacks instead of OOM-killing."""

from __future__ import annotations

import pytest

from seestack.stack import stacker


def test_guard_refuses_huge_canvas(monkeypatch):
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "1")
    # 10000×10000×3×4 bytes × 4 arrays ≈ 4.8 GB, well over the 1 GB budget.
    with pytest.raises(MemoryError, match="working memory"):
        stacker._guard_stack_memory((10000, 10000), drizzle=False, drizzle_scale=1.0)


def test_guard_allows_small_canvas(monkeypatch):
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "1")
    # 1000×1000 needs ~48 MB — fine.
    stacker._guard_stack_memory((1000, 1000), drizzle=False, drizzle_scale=1.0)


def test_guard_accounts_for_drizzle_scale(monkeypatch):
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "5")
    shape = (4000, 4000)  # ~0.77 GB undrizzled — allowed
    stacker._guard_stack_memory(shape, drizzle=False, drizzle_scale=1.0)
    # drizzle ×3 multiplies area ~9× → ~6.9 GB > 5 GB budget → refuse.
    with pytest.raises(MemoryError):
        stacker._guard_stack_memory(shape, drizzle=True, drizzle_scale=3.0)


def test_budget_honors_env_override(monkeypatch):
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "42")
    assert stacker._stack_memory_budget_bytes() == pytest.approx(42e9)


def test_budget_uses_setting_when_no_env(monkeypatch):
    """The user-facing Settings value applies when the env override is absent."""
    monkeypatch.delenv("ASTROSTACK_MAX_STACK_GB", raising=False)
    assert stacker._stack_memory_budget_bytes(8.0) == pytest.approx(8e9)


def test_budget_env_wins_over_setting(monkeypatch):
    """A deployment env override must beat the in-app Settings value."""
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "3")
    assert stacker._stack_memory_budget_bytes(64.0) == pytest.approx(3e9)


def test_budget_setting_none_falls_back_to_auto(monkeypatch):
    """None (auto) leaves the RAM-based default in place, not a zero budget."""
    monkeypatch.delenv("ASTROSTACK_MAX_STACK_GB", raising=False)
    assert stacker._stack_memory_budget_bytes(None) > 0


def test_guard_honors_setting_budget(monkeypatch):
    monkeypatch.delenv("ASTROSTACK_MAX_STACK_GB", raising=False)
    # A 4000×4000 canvas needs ~0.77 GB; a 0.5 GB setting must refuse it.
    with pytest.raises(MemoryError, match="working memory"):
        stacker._guard_stack_memory((4000, 4000), drizzle=False, drizzle_scale=1.0,
                                    memory_budget_gb=0.5)
    # …and a generous setting must allow it.
    stacker._guard_stack_memory((4000, 4000), drizzle=False, drizzle_scale=1.0,
                                memory_budget_gb=8.0)


def test_guard_accounts_for_drizzle_reject(monkeypatch):
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "1.2")
    shape = (4000, 4000)  # 4 arrays ≈ 0.77 GB — fits the 1.2 GB budget…
    stacker._guard_stack_memory(shape, drizzle=True, drizzle_scale=1.0)
    # …but two-pass rejection holds ~7 arrays (~1.3 GB) → refuse, and say why.
    with pytest.raises(MemoryError, match="outlier rejection"):
        stacker._guard_stack_memory(
            shape, drizzle=True, drizzle_scale=1.0, drizzle_reject=True
        )


def test_guard_accounts_for_k_reject_planes(monkeypatch):
    monkeypatch.delenv("ASTROSTACK_MAX_STACK_GB", raising=False)
    shape = (4000, 4000)  # baseline 4 planes ≈ 0.77 GB
    # k=1 charges the baseline (2 + 2·1 = 4 planes) — same as no reject.
    base = stacker._min_max_reject_arrays(1)
    assert base == 4
    stacker._guard_stack_memory(shape, drizzle=False, drizzle_scale=1.0,
                                reject_arrays=base, memory_budget_gb=0.9)
    # k=3 needs 2 + 2·3 = 8 planes ≈ 1.5 GB — the 0.9 GB budget that fit k=1
    # must now refuse it, so a big k can't sneak past the OOM guard.
    assert stacker._min_max_reject_arrays(3) == 8
    with pytest.raises(MemoryError, match="working memory"):
        stacker._guard_stack_memory(shape, drizzle=False, drizzle_scale=1.0,
                                    reject_arrays=stacker._min_max_reject_arrays(3),
                                    memory_budget_gb=0.9)


def _peak(shape, scale, reject=False):
    peak, _ = stacker._estimate_peak_bytes(
        shape, drizzle=True, drizzle_scale=scale, drizzle_reject=reject)
    return peak


def test_largest_drizzle_scale_suggests_a_fitting_smaller_scale():
    shape = (320, 480)
    # A budget between the ×1.0 and ×2.0 peaks: a smaller scale should fit.
    budget = int((_peak(shape, 1.0) + _peak(shape, 2.0)) / 2)
    s = stacker._largest_drizzle_scale_within_budget(
        shape, drizzle_reject=False, budget=budget, max_scale=2.0)
    assert s is not None
    assert 1.0 <= s < 2.0
    # The suggestion genuinely fits and is on the 0.1 grid.
    assert _peak(shape, s) <= budget
    assert round(s * 10) == s * 10


def test_largest_drizzle_scale_none_when_request_already_fits():
    shape = (320, 480)
    # Generous budget: ×2.0 already fits, so there is nothing to suggest.
    s = stacker._largest_drizzle_scale_within_budget(
        shape, drizzle_reject=False, budget=_peak(shape, 2.0) * 2, max_scale=2.0)
    assert s is None


def test_largest_drizzle_scale_none_when_even_unity_exceeds():
    shape = (320, 480)
    # Budget below the ×1.0 peak: drizzle can't rescue it (must drop the canvas).
    s = stacker._largest_drizzle_scale_within_budget(
        shape, drizzle_reject=False, budget=_peak(shape, 1.0) - 1, max_scale=2.0)
    assert s is None
