"""``GET /api/library/missing-files`` — the library-wide storage preflight.

The per-target version of this question has been answered since v0.232.0, but an
unmounted drive or an offline share takes out *every* target at once, and the
owner would have to open each target in turn to discover the scale of it. These
tests pin the whole-library answer: the totals, the worst-first (capped) list the
Dashboard note names a single-target outage from, the silence on a healthy
install, and the cache that keeps a per-render read off the disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seestack.io.library import Library


def _unlink_accepted(data_root: Path, safe: str, n: int) -> list[int]:
    """Take ``n`` of ``safe``'s accepted subs off disk, exactly as an unmounted
    drive would: the rows stay, the bytes don't. Returns the frame ids."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            gone = list(proj.iter_frames(accepted_only=True))[:n]
            for frame in gone:
                for path in (frame.aligned_cache_path, frame.cached_path,
                             frame.source_path):
                    if path:
                        Path(path).unlink(missing_ok=True)
            return [f.id for f in gone]
        finally:
            proj.close()
    finally:
        lib.close()


def test_healthy_library_reports_nothing_missing(client, built_library):
    """The overwhelmingly common case: every listed sub is where it should be, so
    the note this feeds has nothing to say and self-hides."""
    body = client.get("/api/library/missing-files").json()
    assert body["n_missing"] == 0
    assert body["n_targets_missing"] == 0
    assert body["targets"] == []
    # The denominator is real, so the caller can tell "nothing missing" apart
    # from "nothing to check".
    assert body["n_accepted"] >= 2


def test_counts_vanished_subs_across_every_target(client, built_library, data_root):
    """The whole point of the endpoint: one answer covering the library, not one
    per target. Both fixture targets lose subs; the totals add up and both are
    named."""
    _unlink_accepted(data_root, "M_42", 2)
    _unlink_accepted(data_root, "NGC_7000", 1)

    body = client.get("/api/library/missing-files").json()
    assert body["n_missing"] == 3
    assert body["n_targets_missing"] == 2
    named = {t["safe"]: t["n_missing"] for t in body["targets"]}
    assert named == {"M_42": 2, "NGC_7000": 1}
    # Worst first, so a capped list still names the worst offender.
    assert [t["safe"] for t in body["targets"]] == ["M_42", "NGC_7000"]


def test_only_the_affected_targets_are_listed(client, built_library, data_root):
    """A target whose files are all present isn't an outage and must not appear —
    otherwise the Dashboard note would say "across 2 targets" for a fault in one."""
    _unlink_accepted(data_root, "NGC_7000", 1)

    body = client.get("/api/library/missing-files").json()
    assert body["n_targets_missing"] == 1
    assert [t["safe"] for t in body["targets"]] == ["NGC_7000"]
    assert body["n_missing"] == 1


def test_rejected_subs_dont_count(client, built_library, data_root):
    """A rejected sub was never going to be stacked, so its file going missing is
    not a fault to warn about — the count is over *accepted* subs only."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            frame = next(iter(proj.iter_frames(accepted_only=True)))
            proj.update_frame(frame.id, accept=False, reject_reason="user")
            for path in (frame.aligned_cache_path, frame.cached_path,
                         frame.source_path):
                if path:
                    Path(path).unlink(missing_ok=True)
        finally:
            proj.close()
        lib.refresh_target_stats("M_42")
    finally:
        lib.close()

    body = client.get("/api/library/missing-files").json()
    assert body["n_missing"] == 0
    assert body["targets"] == []


def test_answer_is_cached_between_calls(client, built_library, data_root):
    """Answering means opening every project and one ``stat()`` per accepted
    frame, so the Dashboard must not pay for it on every render. Taking files
    away changes nothing the registry signature can see, so a second call inside
    the TTL returns the cached answer — which is exactly the property that keeps
    this off the render path (the TTL is what lets a reconnected drive clear it).
    """
    first = client.get("/api/library/missing-files").json()
    assert first["n_missing"] == 0

    _unlink_accepted(data_root, "M_42", 2)

    cached = client.get("/api/library/missing-files").json()
    assert cached["n_missing"] == 0, "a second call inside the TTL should be cached"

    # And the cache really is a cache, not a wrong answer: drop it and the same
    # request now reports the outage.
    from webapp.registry_cache import invalidate_registry_cache

    invalidate_registry_cache(client.app, "library_missing_files")
    fresh = client.get("/api/library/missing-files").json()
    assert fresh["n_missing"] == 2
    assert [t["safe"] for t in fresh["targets"]] == ["M_42"]


def test_a_broken_project_doesnt_500_the_dashboard(client, built_library, data_root,
                                                   monkeypatch):
    """One unreadable project must cost its own row, not the whole answer — the
    remaining targets are still counted and the dashboard still gets a 200."""
    # Both targets lose a sub, so the assertion below doesn't depend on which
    # one the registry happens to list first.
    _unlink_accepted(data_root, "M_42", 1)
    _unlink_accepted(data_root, "NGC_7000", 1)

    from seestack.io import project as project_mod

    real_open = project_mod.Project.open
    calls: list[Path] = []

    def flaky_open(path):  # noqa: ANN001 — mirrors the classmethod's signature
        calls.append(Path(path))
        if len(calls) == 1:
            raise OSError("database is locked")
        return real_open(path)

    monkeypatch.setattr(project_mod.Project, "open", staticmethod(flaky_open))
    resp = client.get("/api/library/missing-files")
    assert resp.status_code == 200
    # The first target opened raised and is simply absent; the second is still
    # read, and its outage still reported.
    assert len(calls) >= 2
    body = resp.json()
    assert body["n_missing"] == 1
    assert body["n_targets_missing"] == 1
    assert len(body["targets"]) == 1


@pytest.mark.parametrize("field", ["n_missing", "n_accepted", "n_targets_missing"])
def test_response_shape(client, built_library, field):
    """The three numbers the Dashboard note reads are always present, so the
    frontend never has to guess at a partial payload."""
    body = client.get("/api/library/missing-files").json()
    assert isinstance(body[field], int)
