"""The shared registry-signature cache behind the per-target roll-ups.

Two endpoints (`/api/library-progress` and `/api/plan/tonight`) answer the same
expensive question — open every target's project and measure what the owner has
collected — so they share one cache. These pin its contract directly, because a
cache that quietly serves a stale answer is a correctness bug wearing a
performance costume.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from webapp.registry_cache import (
    GOAL_DEPENDENT_KEYS,
    cached_for_registry,
    invalidate_registry_cache,
    registry_signature,
)


class _App:
    """The one attribute of a FastAPI app this module touches."""

    def __init__(self) -> None:
        self.state = SimpleNamespace()


def _target(safe: str, activity: str | None, accepted: int,
            preview: str | None = None):
    return SimpleNamespace(
        safe_name=safe, last_activity_utc=activity, n_frames_accepted=accepted,
        last_stack_preview=preview,
    )


def test_signature_is_order_stable_and_moves_with_activity_or_frames():
    a = _target("M_42", "2026-07-01T00:00:00", 10)
    b = _target("NGC_7000", "2026-07-02T00:00:00", 4)
    # Registry order must not matter — a re-listed library isn't a changed one.
    assert registry_signature([a, b]) == registry_signature([b, a])
    # A new stack (activity) or a new/rejected sub (count) both move it.
    assert registry_signature([a]) != registry_signature(
        [_target("M_42", "2026-07-03T00:00:00", 10)])
    assert registry_signature([a]) != registry_signature(
        [_target("M_42", "2026-07-01T00:00:00", 11)])
    # A target with no activity stamp yet is representable, not a crash.
    assert registry_signature([_target("M_1", None, 0)]) == (("M_1", "", 0, ""),)


def test_signature_moves_when_a_new_picture_lands_and_nothing_else_does():
    """A re-stack of frames already in the library adds no accepted frames, and
    ``last_activity_utc`` is written at one-second granularity — so a stack that
    lands inside the same second as the previous registry write moves neither.
    Without the newest-picture column the roll-up would keep answering from the
    *previous* picture for a whole TTL: the Tonight planner would go on telling
    someone to nudge a scope they have already moved."""
    before = _target("M_42", "2026-07-01T00:00:00", 10, "/lib/M_42/old_preview.png")
    after = _target("M_42", "2026-07-01T00:00:00", 10, "/lib/M_42/new_preview.png")
    assert registry_signature([before]) != registry_signature([after])


def test_signature_tolerates_a_target_without_the_picture_column():
    """Every real ``TargetEntry`` carries it; a caller passing a leaner object
    must still get a signature rather than an AttributeError."""
    lean = SimpleNamespace(
        safe_name="M_42", last_activity_utc="t", n_frames_accepted=1)
    assert registry_signature([lean]) == (("M_42", "t", 1, ""),)


def test_a_matching_signature_reuses_the_built_value():
    app, built = _App(), []
    sig = registry_signature([_target("M_42", "t", 1)])

    def build():
        built.append(1)
        return ["rows"]

    assert cached_for_registry(app, "k", sig, build) == ["rows"]
    assert cached_for_registry(app, "k", sig, build) == ["rows"]
    assert len(built) == 1


def test_a_changed_signature_rebuilds():
    app, built = _App(), []
    build = lambda: (built.append(1), len(built))[1]  # noqa: E731
    cached_for_registry(app, "k", registry_signature([_target("M_42", "t", 1)]), build)
    out = cached_for_registry(
        app, "k", registry_signature([_target("M_42", "t", 2)]), build)
    assert out == 2
    assert len(built) == 2


def test_the_ttl_expires_a_stale_entry():
    app, built = _App(), []
    build = lambda: (built.append(1), len(built))[1]  # noqa: E731
    sig = registry_signature([_target("M_42", "t", 1)])
    cached_for_registry(app, "k", sig, build, ttl_s=0.0)
    cached_for_registry(app, "k", sig, build, ttl_s=0.0)
    assert len(built) == 2


def test_keys_do_not_collide():
    app = _App()
    sig = registry_signature([_target("M_42", "t", 1)])
    assert cached_for_registry(app, "one", sig, lambda: "A") == "A"
    assert cached_for_registry(app, "two", sig, lambda: "B") == "B"
    # Each key kept its own answer rather than the other's.
    assert cached_for_registry(app, "one", sig, lambda: "C") == "A"
    assert cached_for_registry(app, "two", sig, lambda: "D") == "B"


def test_a_failed_build_is_not_cached_and_leaves_the_previous_answer():
    app = _App()
    sig = registry_signature([_target("M_42", "t", 1)])
    assert cached_for_registry(app, "k", sig, lambda: "good") == "good"

    def boom():
        raise RuntimeError("project is toast")

    # A transient failure propagates (the caller decides), and must not pin
    # itself as the cached answer.
    with pytest.raises(RuntimeError):
        cached_for_registry(app, "k", registry_signature([_target("M_42", "t", 2)]), boom)
    assert cached_for_registry(app, "k", sig, lambda: "rebuilt") == "good"


def test_invalidate_drops_every_goal_dependent_roll_up():
    app = _App()
    sig = registry_signature([_target("M_42", "t", 1)])
    for key in GOAL_DEPENDENT_KEYS:
        cached_for_registry(app, key, sig, lambda: "old")
    invalidate_registry_cache(app)
    for key in GOAL_DEPENDENT_KEYS:
        assert cached_for_registry(app, key, sig, lambda: "new") == "new"


def test_invalidate_can_target_one_key_and_never_raises_on_a_cold_cache():
    app = _App()
    sig = registry_signature([_target("M_42", "t", 1)])
    cached_for_registry(app, "one", sig, lambda: "A")
    cached_for_registry(app, "two", sig, lambda: "B")
    invalidate_registry_cache(app, "one")
    assert cached_for_registry(app, "one", sig, lambda: "A2") == "A2"
    assert cached_for_registry(app, "two", sig, lambda: "B2") == "B"
    # Dropping something that was never cached is a no-op, not an error — and so
    # is invalidating an app that has never cached anything at all.
    invalidate_registry_cache(app, "never-cached")
    invalidate_registry_cache(_App())


def test_invalidate_is_safe_on_a_real_starlette_state():
    """Regression: Starlette's ``State`` stores attributes in a dict and raises
    ``KeyError`` — not ``AttributeError`` — for a missing one, so catching only
    the latter turned "set a goal before anything was cached" into a 500."""
    from starlette.datastructures import State

    app = SimpleNamespace(state=State())
    invalidate_registry_cache(app)  # cold cache: must be a quiet no-op

    sig = registry_signature([_target("M_42", "t", 1)])
    assert cached_for_registry(app, "library_progress", sig, lambda: "old") == "old"
    invalidate_registry_cache(app)
    assert cached_for_registry(app, "library_progress", sig, lambda: "new") == "new"
