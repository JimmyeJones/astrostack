"""The firmware 7.18+ handshake (⭐ Seestar-page upgrade, slice 2).

A Seestar on firmware 7.18+ answers commands only after the client signs its
challenge: ``get_verify_str`` → RSA PKCS#1 v1.5 / SHA-1 → ``verify_client
{sign, data}`` → ``pi_is_verified``. AstroStack signs with the standard library
(``keyfile.sign_pkcs1v15_sha1``); these tests check that signature against
OpenSSL byte for byte, and drive the client and the manager against a fake
scope shaped like Seestar Studio's ``seestar_sim.py`` — except that this one
actually *checks* the signature with the public half of the key, so a wrong
encoding cannot pass.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import shutil
import socket
import subprocess
import threading
from types import SimpleNamespace

import pytest

from tests.webapp.test_seestar_key import _make_key, _pem
from webapp.seestar import client as client_mod
from webapp.seestar import keyfile
from webapp.seestar.client import (
    AUTH_FAILED,
    AUTH_KEY_NEEDED,
    AUTH_NOT_NEEDED,
    AUTH_REJECTED,
    AUTH_VERIFIED,
    SeestarClient,
)
from webapp.seestar.keyfile import parse_private_key, sign_challenge, sign_pkcs1v15_sha1
from webapp.seestar.manager import SeestarManager

_SHA1_PREFIX = bytes.fromhex("3021300906052b0e03021a05000414")


@pytest.fixture(scope="module")
def key() -> dict:
    return _make_key()


@pytest.fixture(scope="module")
def other_key() -> dict:
    return _make_key(seed=11)


def _rsa(k: dict) -> keyfile.RsaPrivateKey:
    return parse_private_key(_pem("PRIVATE KEY", k["pkcs8"]))[0]


def _signature_ok(n: int, e: int, message: bytes, sig: bytes) -> bool:
    """An independent EMSA-PKCS1-v1_5 / SHA-1 verifier, written out from RFC
    8017 §8.2.2 without touching the module under test."""
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return False
    em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    t = _SHA1_PREFIX + hashlib.sha1(message).digest()
    return em == b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t


# ---------------------------------------------------------------------------
# The signature
# ---------------------------------------------------------------------------


def test_signature_verifies_with_the_public_half(key, other_key):
    rsa = _rsa(key)
    sig = sign_pkcs1v15_sha1(rsa, b"sim-0badc0de")
    assert _signature_ok(key["n"], key["e"], b"sim-0badc0de", sig)
    assert not _signature_ok(key["n"], key["e"], b"sim-0badc0df", sig)
    assert not _signature_ok(other_key["n"], other_key["e"], b"sim-0badc0de", sig)


def test_sign_challenge_is_base64_of_the_utf8_signature(key):
    rsa = _rsa(key)
    out = sign_challenge(rsa, "défi-123")
    assert base64.b64decode(out) == sign_pkcs1v15_sha1(rsa, "défi-123".encode())
    # Deterministic (PKCS#1 v1.5 has no salt), and the size of the modulus.
    assert out == sign_challenge(rsa, "défi-123")
    assert len(base64.b64decode(out)) == 128


def test_a_key_too_short_to_sign_with_is_refused_in_plain_words():
    tiny = keyfile.RsaPrivateKey(n=(1 << 255) + 1, e=3, d=5)  # 32 bytes < 35 + 11
    with pytest.raises(keyfile.KeyFileError, match="too short") as err:
        sign_pkcs1v15_sha1(tiny, b"x")
    assert str(tiny.d) not in str(err.value)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl CLI not installed")
def test_signature_is_byte_identical_to_openssl(tmp_path):
    """The independent check: OpenSSL signs the same challenge with a key it
    generated itself, in the owner's file format (PKCS#8). PKCS#1 v1.5 is
    deterministic, so the two signatures must match byte for byte — and
    OpenSSL must verify ours."""
    pem = tmp_path / "k.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt",
                    "rsa_keygen_bits:2048", "-out", str(pem)],
                   check=True, capture_output=True)
    msg = tmp_path / "challenge.txt"
    msg.write_bytes(b"4f1c9a2e-verify")
    theirs = subprocess.run(["openssl", "dgst", "-sha1", "-sign", str(pem), str(msg)],
                            check=True, capture_output=True).stdout
    rsa, _ = parse_private_key(pem.read_bytes())
    ours = sign_pkcs1v15_sha1(rsa, msg.read_bytes())
    assert ours == theirs
    pub = tmp_path / "pub.pem"
    subprocess.run(["openssl", "pkey", "-in", str(pem), "-pubout", "-out", str(pub)],
                   check=True, capture_output=True)
    sig = tmp_path / "sig.bin"
    sig.write_bytes(ours)
    done = subprocess.run(["openssl", "dgst", "-sha1", "-verify", str(pub), "-signature",
                           str(sig), str(msg)], capture_output=True, text=True)
    assert done.returncode == 0 and "Verified OK" in done.stdout


# ---------------------------------------------------------------------------
# A fake scope, shaped like Studio's seestar_sim.py — but strict
# ---------------------------------------------------------------------------


class _FakeScope:
    """One TCP connection; replies carry ``code`` and ``result``/``error`` as
    the firmware's do. ``mode``: ``gated`` (7.18+: checks the signature against
    ``public``), ``old`` (no gate: 103 on ``get_verify_str``), ``silent``
    (accepts, never answers the challenge)."""

    def __init__(self, mode: str = "gated", public: tuple[int, int] | None = None):
        self.mode = mode
        self.public = public
        self.received: list[dict] = []
        self.verified = False
        self._challenge: str | None = None
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(4)
        self.port = self._srv.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _reply(self, method: str) -> tuple[int, object] | None:
        if self.mode == "silent" and method == "get_verify_str":
            return None
        if method == "get_verify_str":
            if self.mode == "old":
                return 103, "method not found"
            self._challenge = f"sim-{0x5EE57A12:08x}"
            return 0, {"str": self._challenge}
        if self.mode == "old":
            return 0, {}
        if method == "verify_client":
            return None  # handled in _serve (needs params)
        if method == "pi_is_verified":
            return 0, self.verified
        if not self.verified:
            return 207, "fail to operate"
        return 0, {"device": {"name": "S30"}}

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            with conn:
                buf = b""
                while not self._stop:
                    try:
                        data = conn.recv(8192)
                    except OSError:
                        break
                    if not data:
                        break
                    buf += data
                    while b"\r\n" in buf:
                        line, buf = buf.split(b"\r\n", 1)
                        msg = json.loads(line)
                        self.received.append(msg)
                        m = msg["method"]
                        if m == "verify_client":
                            p = msg.get("params") or {}
                            ok = (self.public is not None and p.get("data") == self._challenge
                                  and _signature_ok(*self.public, p["data"].encode(),
                                                    base64.b64decode(p.get("sign", ""))))
                            self.verified = self.verified or ok
                            out = (0, {"key_envelope": "simulated"}) if ok else (109, "verify failed")
                        else:
                            out = self._reply(m)
                        if out is None:
                            continue
                        code, body = out
                        rep = {"jsonrpc": "2.0", "method": m, "code": code, "id": msg["id"]}
                        rep["error" if code else "result"] = body
                        conn.sendall((json.dumps(rep) + "\r\n").encode())

    def methods(self) -> list[str]:
        return [m["method"] for m in self.received]

    def close(self):
        self._stop = True
        with contextlib.suppress(OSError):
            self._srv.close()


@pytest.fixture
def scope_factory(monkeypatch):
    monkeypatch.setattr(client_mod, "_send_udp_intro", lambda host: None)
    made: list[_FakeScope] = []

    def make(*a, **kw):
        s = _FakeScope(*a, **kw)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


def _connected(scope: _FakeScope) -> SeestarClient:
    c = SeestarClient("127.0.0.1", scope.port)
    c.connect()
    return c


# ---------------------------------------------------------------------------
# SeestarClient.handshake
# ---------------------------------------------------------------------------


def test_handshake_with_the_right_key_unlocks_commands(scope_factory, key):
    scope = scope_factory("gated", public=(key["n"], key["e"]))
    c = _connected(scope)
    try:
        # Before: the gated scope refuses commands.
        with pytest.raises(client_mod.SeestarError, match="fail to operate"):
            c.get_device_state(timeout=2)
        assert c.handshake(_rsa(key), timeout=2) == AUTH_VERIFIED
        assert scope.verified
        assert c.get_device_state(timeout=2) == {"device": {"name": "S30"}}
        # Studio's exact sequence and parameter shapes.
        sent = [m for m in scope.received if m["method"] != "get_device_state"]
        assert [m["method"] for m in sent] == ["get_verify_str", "verify_client", "pi_is_verified"]
        assert sent[0]["params"] == "verify" and sent[2]["params"] == "verify"
        assert set(sent[1]["params"]) == {"sign", "data"}
    finally:
        c.disconnect()


def test_handshake_with_the_wrong_key_is_rejected(scope_factory, key, other_key):
    scope = scope_factory("gated", public=(key["n"], key["e"]))
    c = _connected(scope)
    try:
        assert c.handshake(_rsa(other_key), timeout=2) == AUTH_REJECTED
        assert not scope.verified
        assert "pi_is_verified" not in scope.methods()
    finally:
        c.disconnect()


def test_handshake_without_a_key_only_asks_whether_one_is_needed(scope_factory, key):
    scope = scope_factory("gated", public=(key["n"], key["e"]))
    c = _connected(scope)
    try:
        assert c.handshake(None, timeout=2) == AUTH_KEY_NEEDED
        assert scope.methods() == ["get_verify_str"]
    finally:
        c.disconnect()


def test_old_firmware_has_no_gate(scope_factory, key):
    scope = scope_factory("old")
    c = _connected(scope)
    try:
        assert c.handshake(_rsa(key), timeout=2) == AUTH_NOT_NEEDED
        assert scope.methods() == ["get_verify_str"]  # nothing signed, nothing sent
    finally:
        c.disconnect()


def test_no_answer_is_a_failure_not_an_exception(scope_factory, key):
    scope = scope_factory("silent")
    c = _connected(scope)
    try:
        assert c.handshake(_rsa(key), timeout=0.3) == AUTH_FAILED
    finally:
        c.disconnect()
    # And a client that never connected says the same without raising.
    assert SeestarClient("127.0.0.1", scope.port).handshake(_rsa(key), timeout=0.3) == AUTH_FAILED


def test_existing_rpc_still_raises_on_an_error_reply(scope_factory):
    """``_rpc`` was split into ``_call`` + ``_rpc``/``_rpc_reply``; the old
    contract — an error reply raises with its message — must hold."""
    scope = scope_factory("gated", public=None)
    c = _connected(scope)
    try:
        with pytest.raises(client_mod.SeestarError, match="fail to operate"):
            c.get_view_state(timeout=2)
    finally:
        c.disconnect()


# ---------------------------------------------------------------------------
# SeestarManager: handshake on connect, re-run when the key changes
# ---------------------------------------------------------------------------


@pytest.fixture
def manager_on(monkeypatch, tmp_path):
    from webapp.seestar import manager as manager_mod

    def make(scope: _FakeScope) -> SeestarManager:
        monkeypatch.setattr(manager_mod, "SeestarClient",
                            lambda host: SeestarClient(host, scope.port))
        monkeypatch.setattr(manager_mod, "_POLL_TIMEOUT", 2.0)
        return SeestarManager(get_settings=lambda: SimpleNamespace(
            state_dir=tmp_path, seestar_enabled=True))

    return make


def _auth_of(mgr: SeestarManager) -> str | None:
    return mgr.snapshot()[0]["auth"]


def test_manager_connect_runs_the_handshake_with_the_installed_key(
        scope_factory, manager_on, tmp_path, key):
    keyfile.install_key(tmp_path, _pem("PRIVATE KEY", key["pkcs8"]))
    scope = scope_factory("gated", public=(key["n"], key["e"]))
    mgr = manager_on(scope)
    try:
        mgr.connect("127.0.0.1")
        assert _auth_of(mgr) == AUTH_VERIFIED
        assert scope.verified
        # Already verified on this connection: a second connect sends nothing new.
        n = len(scope.received)
        mgr.connect("127.0.0.1")
        assert len(scope.received) == n
    finally:
        mgr.stop()


def test_adding_the_key_later_re_runs_the_handshake(scope_factory, manager_on, tmp_path, key):
    scope = scope_factory("gated", public=(key["n"], key["e"]))
    mgr = manager_on(scope)
    try:
        mgr.connect("127.0.0.1")
        assert _auth_of(mgr) == AUTH_KEY_NEEDED
        keyfile.install_key(tmp_path, _pem("PRIVATE KEY", key["pkcs8"]))
        mgr.connect("127.0.0.1")  # the poll loop does the same via _ensure_auth
        assert _auth_of(mgr) == AUTH_VERIFIED
    finally:
        mgr.stop()


def test_replacing_a_wrong_key_re_runs_the_handshake(
        scope_factory, manager_on, tmp_path, key, other_key):
    keyfile.install_key(tmp_path, _pem("PRIVATE KEY", other_key["pkcs8"]))
    scope = scope_factory("gated", public=(key["n"], key["e"]))
    mgr = manager_on(scope)
    try:
        mgr.connect("127.0.0.1")
        assert _auth_of(mgr) == AUTH_REJECTED
        # A rejected key is not re-sent every poll cycle while it is unchanged.
        n = len(scope.received)
        mgr.connect("127.0.0.1")
        assert len(scope.received) == n
        keyfile.install_key(tmp_path, _pem("PRIVATE KEY", key["pkcs8"]))
        mgr.connect("127.0.0.1")
        assert _auth_of(mgr) == AUTH_VERIFIED
    finally:
        mgr.stop()


def test_a_failed_handshake_is_retried_only_after_a_pause(scope_factory, manager_on, key,
                                                          monkeypatch):
    from webapp.seestar import manager as manager_mod

    scope = scope_factory("silent")
    mgr = manager_on(scope)
    monkeypatch.setattr(manager_mod, "_POLL_TIMEOUT", 0.3)
    clock = {"t": 1000.0}
    mgr._now = lambda: clock["t"]  # noqa: SLF001
    try:
        mgr.connect("127.0.0.1")
        assert _auth_of(mgr) == AUTH_FAILED
        n = scope.methods().count("get_verify_str")
        mgr.connect("127.0.0.1")
        assert scope.methods().count("get_verify_str") == n
        clock["t"] += manager_mod._AUTH_RETRY_S
        mgr.connect("127.0.0.1")
        assert scope.methods().count("get_verify_str") == n + 1
    finally:
        mgr.stop()


def test_disconnect_clears_the_auth_and_a_new_device_starts_without_one(
        scope_factory, manager_on, tmp_path, key):
    keyfile.install_key(tmp_path, _pem("PRIVATE KEY", key["pkcs8"]))
    scope = scope_factory("gated", public=(key["n"], key["e"]))
    mgr = manager_on(scope)
    try:
        mgr.connect("127.0.0.1")
        assert _auth_of(mgr) == AUTH_VERIFIED
        mgr.disconnect("127.0.0.1")
        assert _auth_of(mgr) is None
    finally:
        mgr.stop()


def test_no_telemetry_message_names_the_missing_key(scope_factory, manager_on, monkeypatch):
    """A gated scope with no key refuses every telemetry call; the device's
    error says why in plain words instead of "port 4700 returned no data"."""
    import time

    scope = scope_factory("gated", public=None)
    mgr = manager_on(scope)
    settings = SimpleNamespace(state_dir=None, seestar_enabled=True, seestar_poll_interval_s=2)
    mgr._get_settings = lambda: settings  # noqa: SLF001
    try:
        mgr.connect("127.0.0.1")
        assert _auth_of(mgr) == AUTH_KEY_NEEDED
        mgr._poll_thread = threading.Thread(target=mgr._poll_loop, daemon=True)  # noqa: SLF001
        mgr._poll_thread.start()  # noqa: SLF001
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not (mgr.snapshot()[0]["error"] or ""):
            time.sleep(0.05)
        error = mgr.snapshot()[0]["error"] or ""
        assert "add the key file in Settings" in error
        assert "returned no data" not in error
    finally:
        mgr.stop()


def test_the_key_never_reaches_the_device_snapshot(scope_factory, manager_on, tmp_path, key):
    keyfile.install_key(tmp_path, _pem("PRIVATE KEY", key["pkcs8"]))
    scope = scope_factory("gated", public=(key["n"], key["e"]))
    mgr = manager_on(scope)
    try:
        mgr.connect("127.0.0.1")
        text = json.dumps(mgr.snapshot())
        for secret in (key["d"], key["n"]):
            assert str(secret)[:16] not in text
        assert "PRIVATE KEY" not in text
    finally:
        mgr.stop()
