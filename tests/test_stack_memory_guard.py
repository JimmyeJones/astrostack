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


def test_guard_accounts_for_drizzle_reject(monkeypatch):
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "1.2")
    shape = (4000, 4000)  # 4 arrays ≈ 0.77 GB — fits the 1.2 GB budget…
    stacker._guard_stack_memory(shape, drizzle=True, drizzle_scale=1.0)
    # …but two-pass rejection holds ~7 arrays (~1.3 GB) → refuse, and say why.
    with pytest.raises(MemoryError, match="outlier rejection"):
        stacker._guard_stack_memory(
            shape, drizzle=True, drizzle_scale=1.0, drizzle_reject=True
        )
