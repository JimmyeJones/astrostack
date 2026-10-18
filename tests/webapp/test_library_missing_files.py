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
        # Break one *named* project rather than "whichever open happens to be
        # first". `Project.open` is patched process-wide and the app under test
        # runs a job worker and a watcher thread, so a call-ordinal rule let a
        # background open consume the failure — both targets were then readable,
        # both outages were reported, and the test failed with `2 == 1`. Seen
        # once on CI (2026-09-12) and never locally, which is what a timing race
        # looks like. Matching the path removes it instead of hoping the
        # ordering holds, and says more than the ordinal did: *this* project is
        # the broken one.
        calls.append(Path(path))
        if Path(path).name == "M_42":
            raise OSError("database is locked")
        return real_open(path)

    monkeypatch.setattr(project_mod.Project, "open", staticmethod(flaky_open))
    resp = client.get("/api/library/missing-files")
    assert resp.status_code == 200
    # The broken target raised and is simply absent; the other is still read,
    # and its outage still reported.
    assert any(p.name == "M_42" for p in calls), "the broken project was never opened"
    assert any(p.name == "NGC_7000" for p in calls), "the healthy project was skipped"
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


def test_the_roll_up_never_builds_a_frame_row_per_sub(client, built_library,
                                                      data_root, monkeypatch):
    """The whole library's worth of this question must not cost a row per sub.

    The roll-up opens *every* target with accepted frames and stats each one's
    subs, so it is the one caller that pays the row building more than once per
    page. It asks ``Project.count_unreadable_frames`` — two path columns, no
    plate-solve header — and this pins that by making the whole-row read fail:
    the answer is unchanged, where the ``count_unreadable_frames(iter_frames(…))``
    idiom it replaced could not have produced one at all.
    """
    from seestack.io.project import Project

    _unlink_accepted(data_root, "M_42", 2)

    def _boom(*_a, **_k):
        raise AssertionError("the missing-files roll-up must not read whole rows")

    monkeypatch.setattr(Project, "iter_frames", _boom)
    body = client.get("/api/library/missing-files").json()
    assert body["n_missing"] == 2
    assert [t["safe"] for t in body["targets"]] == ["M_42"]


# --- issue #878: a sub two targets registered is one sub -------------------
#
# The mosaic double-registration lists the same subs under two targets. Each
# target really can't stack a missing one, so each keeps its own row — but the
# library totals added those rows together and said an outage had taken out
# up to twice the subs it had.


def _twin(data_root: Path, safe: str, name: str = "twin") -> None:
    """Register a second target over every one of ``safe``'s accepted subs —
    #878's shape. Nothing on disk moves."""
    from seestack.io.project import FrameRow

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            frames = list(proj.iter_frames(accepted_only=True))
        finally:
            proj.close()
        entry, twin = lib.create_target(name)
        try:
            twin.add_frames([FrameRow(source_path=f.source_path, accept=True)
                             for f in frames])
        finally:
            twin.close()
        lib.refresh_target_stats(entry.safe_name)
    finally:
        lib.close()


def test_a_sub_two_targets_registered_counts_once(client, built_library, data_root):
    """Healthy library, one target twinned: the denominator is the real number
    of subs, not the sum of both targets' rows."""
    before = client.get("/api/library/missing-files").json()["n_accepted"]
    _twin(data_root, "M_42")
    body = client.get("/api/library/missing-files").json()
    assert body["n_accepted"] == before
    assert body["n_missing"] == 0


def test_a_missing_twinned_sub_counts_once_but_both_targets_are_named(
        client, built_library, data_root):
    """Two of M 42's subs go missing and a twin lists them too: the note says
    two subs across two targets — each target can't stack them — not four."""
    _twin(data_root, "M_42")
    _unlink_accepted(data_root, "M_42", 2)

    body = client.get("/api/library/missing-files").json()
    assert body["n_missing"] == 2
    assert body["n_targets_missing"] == 2
    named = {t["safe"]: t["n_missing"] for t in body["targets"]}
    assert named["M_42"] == 2
    assert sorted(named.values()) == [2, 2]
    # Never below a row the same answer names.
    assert body["n_missing"] >= max(named.values())


def test_distinct_subs_in_different_targets_still_add_up(client, built_library,
                                                         data_root):
    """The de-duplication is by file, not by count: a twin alongside an
    unrelated outage in another target still adds that target's subs."""
    _twin(data_root, "M_42")
    _unlink_accepted(data_root, "M_42", 1)
    _unlink_accepted(data_root, "NGC_7000", 1)

    body = client.get("/api/library/missing-files").json()
    assert body["n_missing"] == 2
    assert body["n_targets_missing"] == 3
