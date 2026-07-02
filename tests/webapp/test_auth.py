"""Optional HTTP Basic access control."""

from __future__ import annotations

from webapp import auth
from webapp.config import Settings


def test_hash_and_verify():
    h, salt = auth.hash_password("hunter2")
    s = Settings(auth_username="admin", auth_password_hash=h, auth_salt=salt)
    assert auth.is_enabled(s)
    assert auth.check_basic_auth(s, _basic("admin", "hunter2"))
    assert not auth.check_basic_auth(s, _basic("admin", "wrong"))
    assert not auth.check_basic_auth(s, _basic("root", "hunter2"))
    assert not auth.check_basic_auth(s, None)


def test_disabled_allows_everything():
    s = Settings()  # no password
    assert not auth.is_enabled(s)
    assert auth.check_basic_auth(s, None)
    assert auth.check_basic_auth(s, _basic("x", "y"))


def _basic(user: str, pw: str) -> str:
    import base64
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return f"Basic {token}"


def test_auth_gate_end_to_end(client):
    # Initially open.
    assert client.get("/api/auth/status").json()["enabled"] is False
    assert client.get("/api/system").status_code == 200

    # Enable.
    r = client.post("/api/auth/password", json={"password": "secret1", "username": "pilot"})
    assert r.status_code == 200 and r.json()["enabled"] is True

    # No creds → 401 (with challenge), wrong creds → 401, right creds → 200.
    unauth = client.get("/api/system")
    assert unauth.status_code == 401
    assert "Basic" in unauth.headers.get("WWW-Authenticate", "")
    assert client.get("/api/system", auth=("pilot", "nope")).status_code == 401
    assert client.get("/api/system", auth=("pilot", "secret1")).status_code == 200

    # Health stays open for the Docker healthcheck.
    assert client.get("/api/health").status_code == 200

    # Disable (must be authenticated to do so).
    d = client.post("/api/auth/password", json={"password": ""}, auth=("pilot", "secret1"))
    assert d.status_code == 200 and d.json()["enabled"] is False
    assert client.get("/api/system").status_code == 200


def test_settings_never_expose_or_accept_auth(client):
    client.post("/api/auth/password", json={"password": "secret1"})
    body = client.get("/api/settings", auth=("admin", "secret1")).json()
    assert "auth_password_hash" not in body
    assert "auth_salt" not in body

    # Trying to set the hash via the settings PUT is ignored (auth still works
    # with the real password, not the injected one).
    client.put("/api/settings", json={"auth_password_hash": "deadbeef"},
               auth=("admin", "secret1"))
    assert client.get("/api/system", auth=("admin", "secret1")).status_code == 200

    client.post("/api/auth/password", json={"password": ""}, auth=("admin", "secret1"))


def test_short_password_rejected(client):
    r = client.post("/api/auth/password", json={"password": "ab"})
    assert r.status_code == 400
