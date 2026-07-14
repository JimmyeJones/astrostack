"""GET /api/last-night — the Dashboard "Last night" combined recap card."""

from __future__ import annotations

import datetime as dt


def _add_night(lib, safe, start, *, n, exposure=10.0, accept=True, reject_reason=None):
    from seestack.io.project import FrameRow

    proj = lib.open_target(safe)
    try:
        for i in range(n):
            proj.add_frame(FrameRow(
                source_path=f"/x/{safe}-{start:%Y%m%d}-{i}-{accept}.fit",
                timestamp_utc=(start + dt.timedelta(seconds=30 * i)).isoformat(),
                exposure_s=exposure, accept=accept, reject_reason=reject_reason,
            ))
    finally:
        proj.close()


def test_last_night_null_for_an_empty_library(client):
    # No frames carry a capture time yet → nothing datable → null card.
    r = client.get("/api/last-night")
    assert r.status_code == 200
    assert r.json() is None


def test_last_night_combines_targets_shot_the_same_night(client, built_library):
    """Two targets shot back-to-back on one night combine into a single recap; the
    2024 synthetic frames (an earlier 'session') drop out of last night."""
    from seestack.io.library import Library

    safes = {t["safe_name"] for t in client.get("/api/targets").json()}
    m42, ngc = "M_42", "NGC_7000"
    assert {m42, ngc} <= safes

    night = dt.datetime(2026, 7, 8, 21, 0, 0, tzinfo=dt.timezone.utc)
    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, m42, night, n=6)                       # M42 first
        _add_night(lib, m42, night + dt.timedelta(minutes=4),  # one trailed sub
                   n=1, accept=False, reject_reason="auto:streak")
        _add_night(lib, ngc, night + dt.timedelta(hours=2), n=4)  # NGC 2 h later, same night
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert body is not None
    assert body["n_targets"] == 2
    assert body["n_frames"] == 11        # 7 (M42) + 4 (NGC); the 2024 synth night excluded
    assert body["n_kept"] == 10
    assert body["n_set_aside"] == 1
    assert body["reject_buckets"] == {"trailed": 1}
    assert {t["safe"] for t in body["targets"]} == {m42, ngc}
    # Biggest capture leads the card.
    assert body["targets"][0]["safe"] == m42
    assert body["targets"][0]["n_frames"] == 7
    assert body["session_exposure_s"] == 110.0
    assert body["kept_exposure_s"] == 100.0
    assert body["end_utc"] is not None


def test_last_night_excludes_a_target_not_shot_that_night(client, built_library):
    """A target whose last session was a week earlier is not part of last night."""
    from seestack.io.library import Library

    safes = {t["safe_name"] for t in client.get("/api/targets").json()}
    m42, ngc = "M_42", "NGC_7000"
    assert {m42, ngc} <= safes

    lib = Library.open_or_create(built_library / "library")
    try:
        _add_night(lib, ngc, dt.datetime(2026, 7, 1, 22, 0, 0, tzinfo=dt.timezone.utc), n=5)
        _add_night(lib, m42, dt.datetime(2026, 7, 8, 22, 0, 0, tzinfo=dt.timezone.utc), n=6)
    finally:
        lib.close()

    body = client.get("/api/last-night").json()
    assert body is not None
    assert body["n_targets"] == 1        # only M42 was shot last night
    assert body["targets"][0]["safe"] == m42
    assert body["n_frames"] == 6
