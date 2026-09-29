"""``/api/health`` says which build answered it.

`/api/health` is the one path `webapp.main._AUTH_OPEN_PATHS` leaves open, so on
an install with a password set it is the only thing an unattended reader can ask
without a credential — a deploy script confirming the upgrade took, a health
dashboard, or the owner's own on-NAS observer. Until v0.488.2 it answered exactly
`{"ok": true}`, and the running version could only be *inferred* from the newest
`stack_runs.engine_version`, i.e. from whenever the owner last stacked anything.

That is not hypothetical: the observer reported (issue #1015) that it had spent
its entire life reading a checked-out tree the deployed app had never run —
first 36 versions ahead, later 18 behind — and that nothing it was permitted to
read could have told it. A reading taken against the wrong code is silently
wrong rather than absent, which is the worst shape a confound can have.

So the tests here are about the property that makes the field worth having: it
is on the **open** path, it is the **same** number `/api/system` reports, and
asking for it stays as cheap as a liveness probe must be.
"""

from __future__ import annotations

import webapp


def test_health_reports_the_running_version(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["version"] == webapp.__version__


def test_it_is_the_same_number_system_reports(client):
    """One value, one name. Two endpoints disagreeing about "which version is
    this?" would be worse than neither answering."""
    health = client.get("/api/health").json()
    system = client.get("/api/system").json()
    assert health["version"] == system["version"]


def test_a_password_protected_install_still_answers_it_unauthenticated(client):
    """The whole reason the field is on *this* endpoint: `/api/system` carries
    the same number and is behind the gate, which is exactly the position the
    observer was in when it could not tell what was running."""
    r = client.post("/api/auth/password", json={"password": "secret1", "username": "pilot"})
    assert r.status_code == 200 and r.json()["enabled"] is True
    try:
        assert client.get("/api/system").status_code == 401
        body = client.get("/api/health").json()
        assert body["ok"] is True
        assert body["version"] == webapp.__version__
    finally:
        client.post("/api/auth/password", json={"password": ""}, auth=("pilot", "secret1"))


def test_the_probe_still_touches_nothing(client, monkeypatch):
    """Docker's HEALTHCHECK hits this while the job worker may be pinning every
    core, so it must stay a dict literal: no library open, no settings read, no
    disk. Opening the library here is made fatal, and the probe still answers."""
    from seestack.io.library import Library

    def _boom(*_a, **_kw):
        raise AssertionError("/api/health opened the library")

    monkeypatch.setattr(Library, "open_or_create", staticmethod(_boom))
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("/api/health read the disk")),
    )
    body = client.get("/api/health").json()
    assert body["version"] == webapp.__version__
