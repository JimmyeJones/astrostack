"""The Seestar interop key (⭐ Seestar-page upgrade, slice 1): upload, check,
store 0600, remove — and never served back.

Keys are made in the test: a small pure-Python RSA generator for the cases
that must run everywhere, and ``openssl genpkey`` (when present) as the
independent check that a key in the exact format the owner's file uses —
PKCS#8, unencrypted — parses to the same modulus OpenSSL reports.
"""

from __future__ import annotations

import base64
import random
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from webapp.seestar import keyfile
from webapp.seestar.keyfile import KeyFileError, parse_private_key

# ---------------------------------------------------------------------------
# Test keys, made here
# ---------------------------------------------------------------------------


def _is_probable_prime(n: int, rng: random.Random) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(20):
        x = pow(rng.randrange(2, n - 1), d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int, rng: random.Random) -> int:
    while True:
        c = rng.getrandbits(bits) | (3 << (bits - 2)) | 1  # top two bits: p*q has exactly 2*bits
        if _is_probable_prime(c, rng):
            return c


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(body)) + body


def _int(v: int) -> bytes:
    return _tlv(0x02, v.to_bytes(v.bit_length() // 8 + 1, "big", signed=True))


def _make_key(bits: int = 1024, seed: int = 7) -> dict:
    rng = random.Random(seed)
    e = 65537
    while True:
        p, q = _prime(bits // 2, rng), _prime(bits // 2, rng)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            break
    n, d = p * q, pow(e, -1, phi)
    pkcs1 = _tlv(0x30, b"".join(_int(v) for v in (
        0, n, e, d, p, q, d % (p - 1), d % (q - 1), pow(q, -1, p))))
    algo = _tlv(0x30, _tlv(0x06, bytes.fromhex("2a864886f70d010101")) + _tlv(0x05, b""))
    pkcs8 = _tlv(0x30, _int(0) + algo + _tlv(0x04, pkcs1))
    return {"n": n, "e": e, "d": d, "pkcs1": pkcs1, "pkcs8": pkcs8}


def _pem(kind: str, der: bytes) -> str:
    b64 = base64.b64encode(der).decode()
    body = "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
    return f"-----BEGIN {kind}-----\n{body}\n-----END {kind}-----\n"


@pytest.fixture(scope="module")
def key() -> dict:
    return _make_key()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parses_pkcs8_and_pkcs1(key):
    for kind, der in (("PRIVATE KEY", key["pkcs8"]), ("RSA PRIVATE KEY", key["pkcs1"])):
        parsed, pem = parse_private_key(_pem(kind, der))
        assert (parsed.n, parsed.e, parsed.d) == (key["n"], key["e"], key["d"])
        assert pem.startswith(f"-----BEGIN {kind}-----\n")
        # The stored block round-trips to the same key.
        assert parse_private_key(pem)[0] == parsed


def test_text_around_the_block_is_dropped(key):
    noisy = "Seestar key, keep safe\r\n" + _pem("PRIVATE KEY", key["pkcs8"]).replace("\n", "\r\n") + "trailer"
    _, pem = parse_private_key(noisy.encode())
    assert pem == _pem("PRIVATE KEY", key["pkcs8"])


def test_repr_never_carries_the_numbers(key):
    parsed, _ = parse_private_key(_pem("PRIVATE KEY", key["pkcs8"]))
    for text in (repr(parsed), str(parsed)):
        assert str(key["d"])[:12] not in text and str(key["n"])[:12] not in text
        assert "bits=1024" in text


@pytest.mark.parametrize("make,needle", [
    (lambda k: "hello", "doesn't look like a key file"),
    (lambda k: _pem("PUBLIC KEY", b"\x30\x00"), "public half"),
    (lambda k: _pem("CERTIFICATE", b"\x30\x00"), "public half"),
    (lambda k: _pem("ENCRYPTED PRIVATE KEY", b"\x30\x00"), "passphrase"),
    (lambda k: _pem("EC PRIVATE KEY", b"\x30\x00"), "other than a private key"),
    (lambda k: _pem("PRIVATE KEY", k["pkcs8"]) * 2, "more than one key"),
    (lambda k: _pem("PRIVATE KEY", k["pkcs8"][:-20]), "cut short"),
    (lambda k: _pem("PRIVATE KEY", b"\x02\x01\x00"), "not an RSA private key"),
    (lambda k: "-----BEGIN PRIVATE KEY-----\n!!!!\n-----END PRIVATE KEY-----", "damaged"),
    (lambda k: "x" * (keyfile.MAX_KEY_BYTES + 1), "too big"),
])
def test_refusals_are_plain_and_never_quote_the_file(key, make, needle):
    upload = make(key)
    with pytest.raises(KeyFileError) as ei:
        parse_private_key(upload)
    msg = str(ei.value)
    assert needle in msg
    assert "BEGIN" not in msg.replace("“-----BEGIN PRIVATE KEY-----”", "")
    assert base64.b64encode(key["pkcs8"]).decode()[40:60] not in msg


def test_non_rsa_pkcs8_is_named():
    # An EC key's PKCS#8 wrapper: id-ecPublicKey 1.2.840.10045.2.1.
    algo = _tlv(0x30, _tlv(0x06, bytes.fromhex("2a8648ce3d0201")) + _tlv(0x06, bytes.fromhex("2a8648ce3d030107")))
    der = _tlv(0x30, _int(0) + algo + _tlv(0x04, _tlv(0x30, _int(1))))
    with pytest.raises(KeyFileError, match="not an RSA one"):
        parse_private_key(_pem("PRIVATE KEY", der))


def test_numbers_that_do_not_work_together_are_refused(key):
    bad_d = key["d"] + 2
    n, e = key["n"], key["e"]
    pkcs1 = _tlv(0x30, b"".join(_int(v) for v in (0, n, e, bad_d, 0, 0, 0, 0, 0)))
    with pytest.raises(KeyFileError, match="don't make a working key"):
        parse_private_key(_pem("RSA PRIVATE KEY", pkcs1))


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl CLI not installed")
def test_openssl_generated_pkcs8_key_matches_openssl_modulus(tmp_path):
    """Independent check: OpenSSL writes the key (PKCS#8, unencrypted — the
    owner's format) and reports its modulus; ours must agree."""
    pem_path = tmp_path / "k.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                    "-out", str(pem_path)], check=True, capture_output=True)
    text = pem_path.read_text()
    assert text.startswith("-----BEGIN PRIVATE KEY-----")
    out = subprocess.run(["openssl", "rsa", "-in", str(pem_path), "-noout", "-modulus"],
                         check=True, capture_output=True, text=True).stdout
    modulus = int(out.strip().split("=", 1)[1], 16)
    parsed, _ = parse_private_key(text)
    assert parsed.n == modulus and parsed.e == 65537 and parsed.bits == 2048
    # And the traditional (PKCS#1) form of the same key.
    trad = subprocess.run(["openssl", "rsa", "-in", str(pem_path), "-traditional"],
                          check=True, capture_output=True, text=True).stdout
    assert parse_private_key(trad)[0] == parsed


# ---------------------------------------------------------------------------
# Storing
# ---------------------------------------------------------------------------


def test_install_writes_0600_in_a_0700_folder_and_replaces(tmp_path, key):
    keyfile.install_key(tmp_path, _pem("PRIVATE KEY", key["pkcs8"]))
    path = keyfile.key_path(tmp_path)
    assert path == tmp_path / "seestar" / "seestar.pem"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert keyfile.key_status(tmp_path) == {"installed": True, "problem": None}

    other = _make_key(seed=11)
    keyfile.install_key(tmp_path, _pem("RSA PRIVATE KEY", other["pkcs1"]))
    assert keyfile.load_key(tmp_path).n == other["n"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in path.parent.iterdir()] == ["seestar.pem"]  # no temp left behind


def test_a_refused_upload_leaves_the_old_key(tmp_path, key):
    keyfile.install_key(tmp_path, _pem("PRIVATE KEY", key["pkcs8"]))
    with pytest.raises(KeyFileError):
        keyfile.install_key(tmp_path, "not a key")
    assert keyfile.load_key(tmp_path).n == key["n"]


def test_remove_and_unreadable_status(tmp_path, key):
    assert keyfile.key_status(tmp_path) == {"installed": False, "problem": None}
    assert keyfile.remove_key(tmp_path) is False
    keyfile.install_key(tmp_path, _pem("PRIVATE KEY", key["pkcs8"]))
    keyfile.key_path(tmp_path).write_text("scribbled over")
    status = keyfile.key_status(tmp_path)
    assert status["installed"] is False and "Upload it again" in status["problem"]
    assert keyfile.remove_key(tmp_path) is True
    assert not keyfile.key_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# The API: installed / not installed, and never a byte more
# ---------------------------------------------------------------------------


def test_api_upload_status_remove_never_serves_the_key(client, data_root: Path, key, caplog):
    pem = _pem("PRIVATE KEY", key["pkcs8"])
    secret_line = pem.splitlines()[3]

    r = client.get("/api/seestar/key")
    assert r.status_code == 200 and r.json() == {"installed": False, "problem": None}

    caplog.set_level("DEBUG")
    r = client.post("/api/seestar/key", json={"pem": pem})
    assert r.status_code == 200, r.text
    assert r.json() == {"installed": True, "problem": None}
    assert secret_line not in r.text
    stored = data_root / "state" / "seestar" / "seestar.pem"
    assert stored.read_text() == pem
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600

    # Nothing the app answers or logs carries it.
    for path in ("/api/seestar/key", "/api/seestar/devices", "/api/settings",
                 "/api/settings/export", "/api/logs", "/api/diagnostics"):
        resp = client.get(path)
        assert secret_line not in resp.text, path
        assert str(key["d"])[:20] not in resp.text, path
    assert secret_line not in caplog.text

    r = client.post("/api/seestar/key", json={"pem": "-----BEGIN PUBLIC KEY-----\nMAA=\n-----END PUBLIC KEY-----"})
    assert r.status_code == 400 and "public half" in r.json()["detail"]
    assert stored.read_text() == pem  # the refused upload changed nothing

    r = client.delete("/api/seestar/key")
    assert r.status_code == 200 and r.json() == {"installed": False, "problem": None, "removed": True}
    assert not stored.exists()
    assert client.delete("/api/seestar/key").json()["removed"] is False


def test_api_key_is_password_gated_and_refused_to_the_read_only_token(client, key):
    """With a password set, the key endpoints need it; the observer's read-only
    token is refused all three methods (the key path is not on its allowlist)."""
    client.post("/api/auth/password", json={"password": "secret1"})
    ro = client.post("/api/auth/readonly-token", auth=("admin", "secret1")).json()
    ro_auth = (ro["username"], ro["token"])
    pem = _pem("PRIVATE KEY", key["pkcs8"])

    assert client.post("/api/seestar/key", json={"pem": pem}).status_code == 401
    assert client.post("/api/seestar/key", json={"pem": pem}, auth=ro_auth).status_code == 403
    assert client.get("/api/seestar/key", auth=ro_auth).status_code == 403
    assert client.delete("/api/seestar/key", auth=ro_auth).status_code == 403
    r = client.post("/api/seestar/key", json={"pem": pem}, auth=("admin", "secret1"))
    assert r.status_code == 200 and r.json()["installed"] is True


def test_api_rejects_an_oversized_body(client):
    r = client.post("/api/seestar/key", json={"pem": "x" * (keyfile.MAX_KEY_BYTES + 10)})
    assert r.status_code in (400, 422)
