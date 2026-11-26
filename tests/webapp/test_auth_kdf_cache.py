"""The password check must not cost a full PBKDF2 per request, nor stall the loop.

Full audit 2026-11-26 (backend.md finding 4): with a password set, every request
paid ~190 ms of PBKDF2 *on the event loop* — 30 parallel GETs took 5.4 s instead
of 0.5 s, and the Docker health probe queued behind them. Now an accepted
credential is remembered (successes only, keyed on the stored hash and salt) and
the check that does need the KDF runs in a threadpool.
"""

from __future__ import annotations

import base64
import threading
import time

import pytest

from webapp import auth
from webapp.config import Settings


def _basic(user: str, pw: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


@pytest.fixture
def kdf_calls(monkeypatch):
    """Count the real PBKDF2 calls :mod:`webapp.auth` makes."""
    auth._forget_accepted()
    real = auth.hashlib.pbkdf2_hmac
    calls = {"n": 0}

    def counting(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", counting)
    yield calls
    auth._forget_accepted()


def _settings(pw: str = "hunter22") -> Settings:
    h, salt = auth.hash_password(pw)
    return Settings(auth_username="admin", auth_password_hash=h, auth_salt=salt)


def test_an_accepted_password_is_not_rehashed_on_every_request(kdf_calls):
    s = _settings()
    kdf_calls["n"] = 0
    for _ in range(20):
        assert auth.check_basic_auth(s, _basic("admin", "hunter22"))
    assert kdf_calls["n"] == 1


def test_a_wrong_password_pays_the_full_kdf_every_time(kdf_calls):
    s = _settings()
    kdf_calls["n"] = 0
    for _ in range(3):
        assert not auth.check_basic_auth(s, _basic("admin", "nope"))
    assert kdf_calls["n"] == 3


def test_a_cached_password_is_refused_once_the_password_changes(kdf_calls):
    old = _settings("first-pass")
    assert auth.check_basic_auth(old, _basic("admin", "first-pass"))
    new = _settings("second-pass")
    assert not auth.check_basic_auth(new, _basic("admin", "first-pass"))
    assert auth.check_basic_auth(new, _basic("admin", "second-pass"))
    # A wrong username is still refused even though the password is cached.
    assert not auth.check_basic_auth(new, _basic("root", "second-pass"))


def test_a_rotated_readonly_token_is_refused_from_the_cache(kdf_calls):
    s = _settings()
    tok = auth.make_readonly_token()
    s.readonly_token_hash, s.readonly_token_salt = auth.hash_readonly_token(tok)
    assert auth.check_readonly_auth(s, f"Bearer {tok}")
    tok2 = auth.make_readonly_token()
    s.readonly_token_hash, s.readonly_token_salt = auth.hash_readonly_token(tok2)
    assert not auth.check_readonly_auth(s, f"Bearer {tok}")
    assert auth.check_readonly_auth(s, f"Bearer {tok2}")


def test_the_cache_is_bounded(kdf_calls):
    s = _settings()
    # Many distinct accepted credentials (one per minted hash) never grow it past its cap.
    for i in range(auth._ACCEPTED_CACHE_SIZE * 3):
        t = _settings(f"pass-{i:04d}")
        assert auth.check_basic_auth(t, _basic("admin", f"pass-{i:04d}"))
    assert len(auth._accepted) <= auth._ACCEPTED_CACHE_SIZE
    assert auth.check_basic_auth(s, _basic("admin", "hunter22"))


def test_a_slow_password_check_does_not_stall_other_requests(client, monkeypatch):
    """A KDF that the cache cannot answer must not block the event loop: the
    health probe (an open path) answers while a wrong-password request hashes."""
    assert client.post("/api/auth/password", json={"password": "secret1"}).status_code == 200
    real = auth._verify
    started = threading.Event()

    def slow_verify(*a, **kw):
        started.set()
        time.sleep(1.5)  # a blocking KDF, as PBKDF2 is
        return real(*a, **kw)

    monkeypatch.setattr(auth, "_verify", slow_verify)
    result = {}

    def wrong():
        result["status"] = client.get("/api/system", auth=("admin", "nope")).status_code

    t = threading.Thread(target=wrong)
    t.start()
    assert started.wait(5)
    t0 = time.monotonic()
    assert client.get("/api/health").status_code == 200
    health_s = time.monotonic() - t0
    t.join(10)
    assert result.get("status") == 401
    assert health_s < 0.75, f"health waited {health_s:.2f}s behind a password check"
    monkeypatch.setattr(auth, "_verify", real)
    client.post("/api/auth/password", json={"password": ""}, auth=("admin", "secret1"))
