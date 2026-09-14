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


# --------------------------------------------------------------------------- #
# the read-only token — read diagnostics, and nothing else
# --------------------------------------------------------------------------- #

def _readonly_settings(token: str) -> Settings:
    h, salt = auth.hash_readonly_token(token)
    pw_h, pw_salt = auth.hash_password("hunter2")
    return Settings(auth_password_hash=pw_h, auth_salt=pw_salt,
                    readonly_token_hash=h, readonly_token_salt=salt)


def test_a_minted_token_verifies_as_basic_and_as_bearer():
    token = auth.make_readonly_token()
    s = _readonly_settings(token)
    assert auth.readonly_is_enabled(s)
    assert auth.check_readonly_auth(s, _basic(auth.READONLY_USERNAME, token))
    assert auth.check_readonly_auth(s, f"Bearer {token}")
    # …and nothing else does.
    assert not auth.check_readonly_auth(s, _basic(auth.READONLY_USERNAME, "wrong"))
    assert not auth.check_readonly_auth(s, _basic("admin", token))
    assert not auth.check_readonly_auth(s, "Bearer")
    assert not auth.check_readonly_auth(s, "Bearer ")
    assert not auth.check_readonly_auth(s, None)
    # The full password is *not* a read-only token — the two credentials are
    # separate, which is the whole point of having a second one.
    assert not auth.check_readonly_auth(s, _basic("admin", "hunter2"))


def test_no_token_minted_means_no_token_accepted():
    # The inverse of `check_basic_auth`'s "disabled allows everything": this
    # function answers "is this the read-only credential", so with none minted the
    # answer is always no. A True here would be an open door on every listed path.
    s = Settings()
    assert not auth.readonly_is_enabled(s)
    assert not auth.check_readonly_auth(s, None)
    assert not auth.check_readonly_auth(s, _basic(auth.READONLY_USERNAME, "anything"))
    assert not auth.check_readonly_auth(s, "Bearer anything")


def test_a_fresh_token_is_unguessable_and_never_repeats():
    a, b = auth.make_readonly_token(), auth.make_readonly_token()
    assert a != b
    assert len(a) >= 40                      # 32 bytes, URL-safe base64
    assert a.strip() == a and ":" not in a   # survives a Basic header intact


def test_the_token_reads_diagnostics_and_is_refused_everything_else(client):
    client.post("/api/auth/password", json={"password": "secret1"})
    minted = client.post("/api/auth/readonly-token", auth=("admin", "secret1"))
    assert minted.status_code == 200
    token = minted.json()["token"]
    assert minted.json()["username"] == "readonly"
    ro = (minted.json()["username"], token)

    # The reproduced failure: the observer can read the log ring at last.
    assert client.get("/api/logs", auth=ro).status_code == 200
    for path in ("/api/stats", "/api/jobs", "/api/targets", "/api/health"):
        assert client.get(path, auth=ro).status_code == 200, path

    # Everything else is 403 — a credential we know, on a request it may not
    # make — never 401, which would invite a retry with the same token.
    denied_get = client.get("/api/settings", auth=ro)
    assert denied_get.status_code == 403
    assert "read-only" in denied_get.json()["detail"]
    # Not even a GET-allowlisted path by another method.
    assert client.put("/api/settings", json={"auto_stack": True}, auth=ro).status_code == 403
    assert client.post("/api/targets", json={"name": "X"}, auth=ro).status_code == 403
    assert client.delete("/api/targets/whatever", auth=ro).status_code == 403

    # A Bearer header is the same privilege by the same rules.
    hdr = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/logs", headers=hdr).status_code == 200
    assert client.get("/api/settings", headers=hdr).status_code == 403

    # The real password is unaffected on both kinds of path.
    assert client.get("/api/logs", auth=("admin", "secret1")).status_code == 200
    assert client.get("/api/settings", auth=("admin", "secret1")).status_code == 200
    # And a wrong token is still an anonymous caller: 401 with the challenge.
    bad = client.get("/api/logs", auth=("readonly", "not-the-token"))
    assert bad.status_code == 401 and "Basic" in bad.headers.get("WWW-Authenticate", "")

    client.post("/api/auth/password", json={"password": ""}, auth=("admin", "secret1"))


def test_the_token_cannot_mint_or_revoke_a_token(client):
    """The privilege must not be able to widen itself."""
    client.post("/api/auth/password", json={"password": "secret1"})
    token = client.post("/api/auth/readonly-token", auth=("admin", "secret1")).json()["token"]
    ro = ("readonly", token)

    assert client.post("/api/auth/readonly-token", auth=ro).status_code == 403
    assert client.delete("/api/auth/readonly-token", auth=ro).status_code == 403
    assert client.post("/api/auth/password", json={"password": "mine"}, auth=ro).status_code == 403
    # It still works, i.e. nothing above rotated it out from under itself.
    assert client.get("/api/logs", auth=ro).status_code == 200

    client.post("/api/auth/password", json={"password": ""}, auth=("admin", "secret1"))


def test_rotating_and_revoking_the_token(client):
    client.post("/api/auth/password", json={"password": "secret1"})
    first = client.post("/api/auth/readonly-token", auth=("admin", "secret1")).json()["token"]
    second = client.post("/api/auth/readonly-token", auth=("admin", "secret1")).json()["token"]
    assert first != second
    # Minting again revokes the old one — how a leaked token is dealt with
    # without turning the feature off.
    assert client.get("/api/logs", auth=("readonly", first)).status_code == 401
    assert client.get("/api/logs", auth=("readonly", second)).status_code == 200

    assert client.get("/api/auth/status", auth=("admin", "secret1")).json()["readonly_enabled"] is True
    cleared = client.delete("/api/auth/readonly-token", auth=("admin", "secret1"))
    assert cleared.status_code == 200 and cleared.json()["readonly_enabled"] is False
    assert client.get("/api/logs", auth=("readonly", second)).status_code == 401
    # Revoking twice is not an error — no token is the goal, not a state change.
    assert client.delete("/api/auth/readonly-token", auth=("admin", "secret1")).status_code == 200

    client.post("/api/auth/password", json={"password": ""}, auth=("admin", "secret1"))


def test_no_token_is_offered_while_the_app_is_open(client):
    # With no password set every path is already reachable by anyone on the LAN,
    # so a token would guard nothing — refuse rather than hand out a secret that
    # reads as protection.
    r = client.post("/api/auth/readonly-token")
    assert r.status_code == 400
    assert "password" in r.json()["detail"].lower()
    assert client.get("/api/auth/status").json()["readonly_enabled"] is False


def test_an_install_with_no_token_behaves_exactly_as_before(client):
    """The default is off, and off means the gate is what it always was."""
    client.post("/api/auth/password", json={"password": "secret1"})
    assert client.get("/api/auth/status", auth=("admin", "secret1")).json()["readonly_enabled"] is False
    # No token minted → the reserved username is just a wrong password: 401 with
    # the challenge, exactly like any other anonymous caller.
    for creds in (("readonly", "anything"), ("admin", "nope")):
        r = client.get("/api/logs", auth=creds)
        assert r.status_code == 401 and "Basic" in r.headers.get("WWW-Authenticate", "")
    assert client.get("/api/logs", headers={"Authorization": "Bearer anything"}).status_code == 401
    assert client.get("/api/health").status_code == 200

    client.post("/api/auth/password", json={"password": ""}, auth=("admin", "secret1"))


def test_settings_never_expose_or_accept_the_readonly_token(client):
    client.post("/api/auth/password", json={"password": "secret1"})
    token = client.post("/api/auth/readonly-token", auth=("admin", "secret1")).json()["token"]
    body = client.get("/api/settings", auth=("admin", "secret1")).json()
    assert "readonly_token_hash" not in body
    assert "readonly_token_salt" not in body

    # Injecting a hash through the settings PUT is ignored — otherwise anyone who
    # could write settings could mint themselves a token they already know.
    forged, forged_salt = auth.hash_readonly_token("forged")
    client.put("/api/settings", json={"readonly_token_hash": forged,
                                     "readonly_token_salt": forged_salt},
               auth=("admin", "secret1"))
    assert client.get("/api/logs", auth=("readonly", "forged")).status_code == 401
    assert client.get("/api/logs", auth=("readonly", token)).status_code == 200

    client.post("/api/auth/password", json={"password": ""}, auth=("admin", "secret1"))


def test_every_readonly_path_is_a_real_get_route_and_reads_nothing_else(client):
    """The allowlist is the whole privilege, so it must not carry a typo — a path
    that 404s would be a silent hole in the *other* direction (the observer's
    call fails and nothing says why), and a path that isn't a GET route at all
    cannot be granted by a GET allowlist."""
    from webapp.main import _AUTH_OPEN_PATHS, _READONLY_GET_PATHS

    def walk(routes):
        # FastAPI wraps each `include_router` in an `_IncludedRouter` that holds
        # the real routes, so a flat scan of `app.routes` sees none of them and
        # would make this test pass on an empty set.
        for r in routes:
            inner = getattr(r, "original_router", None)
            if inner is not None:
                yield from walk(inner.routes)
            elif getattr(r, "path", None):
                yield r.path, set(getattr(r, "methods", None) or ())

    get_routes = {p for p, methods in walk(client.app.routes) if "GET" in methods}
    assert get_routes, "route walk found nothing — this test would pass vacuously"
    assert _READONLY_GET_PATHS <= get_routes, _READONLY_GET_PATHS - get_routes
    # Health is on both lists on purpose: open to everyone for the Docker
    # healthcheck, and named here so the token's own list reads completely.
    assert _AUTH_OPEN_PATHS <= _READONLY_GET_PATHS
    # Nothing that writes crept onto it.
    assert not any("settings" in p or "stack" in p for p in _READONLY_GET_PATHS)
