"""The Seestar interop key: upload, check, store, remove — never serve back.

A Seestar on firmware 7.18+ answers a client's commands only after the client
signs a challenge with an RSA key (``get_verify_str`` → sign → ``verify_client``;
``docs/reference/seestar-studio/AGENTS_GUIDE.md``). Without the key AstroStack
sees only the scope's broadcast events. The owner uploads the key file through
Settings (his answer, 2026-11-18) and this module is everything that touches it.

The rules, in one place, because they are the point of the module:

* The key is stored as ``state/seestar/seestar.pem``, the folder mode 0700 and
  the file mode 0600, written atomically (a crash leaves the old key or the new
  one, never half of one).
* It is **never served back, logged, or included** in an API response, a
  settings export, an update backup or a diagnostic. The API says only whether
  one is installed. Nothing here puts a byte of the key into an exception
  message or a ``repr``, so a traceback in the log cannot carry it either.
* An upload is refused unless it parses as an unencrypted RSA private key —
  PKCS#8 (``BEGIN PRIVATE KEY``, what the owner's file is) or PKCS#1
  (``BEGIN RSA PRIVATE KEY``, which the ``cryptography`` loader Seestar Studio
  uses also accepts) — and the numbers in it actually work together.

**Standard library only.** Seestar Studio loads the key with ``cryptography``,
which AstroStack does not ship; adding it needs the owner's sign-off (AGENTS.md
§10). A private key is a short DER structure of integers, so a minimal reader
of the handful of DER shapes involved is enough — and the parsed numbers are
what the handshake (slice 2) signs with, via ``pow``.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

KEY_DIRNAME = "seestar"
KEY_FILENAME = "seestar.pem"

#: A 4096-bit PKCS#8 key is ~3.3 KB of PEM; anything far past that is not a key.
MAX_KEY_BYTES = 16 * 1024

# rsaEncryption, 1.2.840.113549.1.1.1, DER-encoded OID contents.
_RSA_OID = bytes.fromhex("2a864886f70d010101")

_PEM_RE = re.compile(
    rb"-----BEGIN ([A-Z0-9 ]+)-----(.*?)-----END \1-----", re.DOTALL)


class KeyFileError(ValueError):
    """An upload that is not a usable key. The message is plain words for the
    owner and never quotes the file."""


@dataclass(frozen=True)
class RsaPrivateKey:
    """The numbers a PKCS#1 v1.5 signature needs. ``repr`` shows the size only,
    so a key that reaches a log line by accident leaks nothing."""

    n: int
    e: int
    d: int

    @property
    def bits(self) -> int:
        return self.n.bit_length()

    def __repr__(self) -> str:  # defined here, so @dataclass keeps it
        return f"RsaPrivateKey(bits={self.bits})"


# ---------------------------------------------------------------------------
# A minimal DER reader — just the shapes a private key is made of.
# ---------------------------------------------------------------------------

_SEQUENCE, _INTEGER, _OCTET_STRING, _NULL, _OID = 0x30, 0x02, 0x04, 0x05, 0x06


def _read_tlv(buf: bytes, pos: int) -> tuple[int, bytes, int]:
    """``(tag, contents, next_pos)`` of the DER element at ``pos``."""
    if pos + 2 > len(buf):
        raise KeyFileError("The key file is cut short.")
    tag = buf[pos]
    length = buf[pos + 1]
    pos += 2
    if length & 0x80:
        n_bytes = length & 0x7F
        if n_bytes == 0 or n_bytes > 4 or pos + n_bytes > len(buf):
            raise KeyFileError("The key file is damaged.")
        length = int.from_bytes(buf[pos:pos + n_bytes], "big")
        pos += n_bytes
    end = pos + length
    if end > len(buf):
        raise KeyFileError("The key file is cut short.")
    return tag, buf[pos:end], end


def _expect(buf: bytes, pos: int, tag: int) -> tuple[bytes, int]:
    got, contents, nxt = _read_tlv(buf, pos)
    if got != tag:
        raise KeyFileError("This file is not an RSA private key.")
    return contents, nxt


def _sequence_items(contents: bytes) -> list[tuple[int, bytes]]:
    out, pos = [], 0
    while pos < len(contents):
        tag, body, pos = _read_tlv(contents, pos)
        out.append((tag, body))
    return out


def _integer(tag: int, body: bytes) -> int:
    if tag != _INTEGER or not body:
        raise KeyFileError("This file is not an RSA private key.")
    return int.from_bytes(body, "big", signed=True)


def _parse_pkcs1(der: bytes) -> RsaPrivateKey:
    """``RSAPrivateKey ::= SEQUENCE { version, n, e, d, p, q, dp, dq, qinv, … }``."""
    contents, end = _expect(der, 0, _SEQUENCE)
    if end != len(der):
        raise KeyFileError("The key file is damaged.")
    items = _sequence_items(contents)
    if len(items) < 9:
        raise KeyFileError("This file is not an RSA private key.")
    version, n, e, d, p, q = (_integer(t, b) for t, b in items[:6])
    if version not in (0, 1):
        raise KeyFileError("This key uses a format AstroStack doesn't know.")
    if n <= 0 or e <= 1 or d <= 0 or e % 2 == 0:
        raise KeyFileError("The numbers in this key don't make a working key.")
    if not 512 <= n.bit_length() <= 8192:
        raise KeyFileError("This key is an unusual size for a Seestar key.")
    if p > 1 and q > 1 and p * q != n:
        raise KeyFileError("The numbers in this key don't make a working key.")
    # The decisive check: what the key signs, its public half must undo.
    probe = 0x5EE57A12 % n
    if pow(pow(probe, d, n), e, n) != probe:
        raise KeyFileError("The numbers in this key don't make a working key.")
    return RsaPrivateKey(n=n, e=e, d=d)


def _parse_pkcs8(der: bytes) -> RsaPrivateKey:
    """``PrivateKeyInfo ::= SEQUENCE { version, AlgorithmIdentifier, OCTET STRING }``."""
    contents, end = _expect(der, 0, _SEQUENCE)
    if end != len(der):
        raise KeyFileError("The key file is damaged.")
    items = _sequence_items(contents)
    if len(items) < 3 or items[0][0] != _INTEGER or items[1][0] != _SEQUENCE:
        raise KeyFileError("This file is not an RSA private key.")
    algo = _sequence_items(items[1][1])
    if not algo or algo[0][0] != _OID:
        raise KeyFileError("This file is not an RSA private key.")
    if algo[0][1] != _RSA_OID:
        raise KeyFileError(
            "This is a private key, but not an RSA one — the Seestar's key is RSA.")
    if items[2][0] != _OCTET_STRING:
        raise KeyFileError("This file is not an RSA private key.")
    return _parse_pkcs1(items[2][1])


def parse_private_key(data: bytes | str) -> tuple[RsaPrivateKey, str]:
    """Parse an uploaded key file. Returns the key and the one PEM block it came
    from, re-wrapped canonically (what gets stored — any text around the block
    is dropped). Raises :class:`KeyFileError` with a plain-words reason."""
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    if len(data) > MAX_KEY_BYTES:
        raise KeyFileError("That file is far too big to be a Seestar key.")
    blocks = _PEM_RE.findall(data)
    if not blocks:
        raise KeyFileError(
            "That doesn't look like a key file. The Seestar key is a text file "
            "that starts with “-----BEGIN PRIVATE KEY-----”.")
    kinds = [kind.decode("ascii") for kind, _ in blocks]
    usable = [(k, body) for k, (_, body) in zip(kinds, blocks, strict=True)
              if k in ("PRIVATE KEY", "RSA PRIVATE KEY")]
    if not usable:
        if "ENCRYPTED PRIVATE KEY" in kinds:
            raise KeyFileError(
                "This key is protected by a passphrase. AstroStack needs the "
                "unprotected key file.")
        if any("PUBLIC KEY" in k or k == "CERTIFICATE" for k in kinds):
            raise KeyFileError(
                "This is the public half of a key. AstroStack needs the private key file.")
        raise KeyFileError("That file holds something other than a private key.")
    if len(usable) > 1:
        raise KeyFileError("That file holds more than one key. Upload just the Seestar key.")
    kind, body = usable[0]
    try:
        der = base64.b64decode(b"".join(body.split()), validate=True)
    except (binascii.Error, ValueError):
        raise KeyFileError("The key file is damaged.") from None
    key = _parse_pkcs8(der) if kind == "PRIVATE KEY" else _parse_pkcs1(der)
    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    pem = f"-----BEGIN {kind}-----\n" + "\n".join(lines) + f"\n-----END {kind}-----\n"
    return key, pem


# ---------------------------------------------------------------------------
# Where it lives
# ---------------------------------------------------------------------------

def key_path(state_dir: Path) -> Path:
    return Path(state_dir) / KEY_DIRNAME / KEY_FILENAME


def install_key(state_dir: Path, data: bytes | str) -> RsaPrivateKey:
    """Check and store an uploaded key, replacing any earlier one. Nothing is
    written unless the upload parses."""
    key, pem = parse_private_key(data)
    folder = key_path(state_dir).parent
    folder.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):  # a filesystem that ignores modes (some SMB mounts)
        os.chmod(folder, 0o700)
    fd, tmp = tempfile.mkstemp(prefix=".seestar-", suffix=".tmp", dir=folder)
    try:
        # mkstemp already creates 0600; say so explicitly so a changed umask or
        # library default can never widen it.
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(pem)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, key_path(state_dir))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    log.info("Seestar key installed (%d-bit RSA).", key.bits)
    return key


def remove_key(state_dir: Path) -> bool:
    """Delete the stored key. True if there was one."""
    path = key_path(state_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    log.info("Seestar key removed.")
    return True


def load_key(state_dir: Path) -> RsaPrivateKey | None:
    """The stored key, or None when there is none or it no longer parses."""
    try:
        data = key_path(state_dir).read_bytes()
    except OSError:
        return None
    try:
        return parse_private_key(data)[0]
    except KeyFileError:
        return None


def key_status(state_dir: Path) -> dict:
    """What the API may say about the key — and nothing more."""
    path = key_path(state_dir)
    if not path.exists():
        return {"installed": False, "problem": None}
    if load_key(state_dir) is None:
        return {"installed": False,
                "problem": "A key file is stored but can't be read. Upload it again."}
    return {"installed": True, "problem": None}


# ---------------------------------------------------------------------------
# Signing the scope's challenge (⭐ Seestar-page upgrade, slice 2)
# ---------------------------------------------------------------------------

# DigestInfo prefix for SHA-1 (RFC 8017 §9.2, note 1): the DER of
# ``SEQUENCE { SEQUENCE { OID sha1, NULL }, OCTET STRING (20 bytes) }`` up to
# the hash itself.
_SHA1_DIGEST_INFO = bytes.fromhex("3021300906052b0e03021a05000414")


def sign_pkcs1v15_sha1(key: RsaPrivateKey, message: bytes) -> bytes:
    """RSASSA-PKCS1-v1_5 with SHA-1 (RFC 8017 §8.2.1) — what the Seestar's
    ``verify_client`` checks, and what Seestar Studio makes with
    ``cryptography``'s ``PKCS1v15()`` + ``SHA1()``. Standard library only:
    EMSA-PKCS1-v1_5 encode, then ``pow``. The signature is ``k`` bytes long,
    ``k`` being the modulus length in bytes."""
    k = (key.n.bit_length() + 7) // 8
    t = _SHA1_DIGEST_INFO + hashlib.sha1(message).digest()
    if k < len(t) + 11:
        raise KeyFileError("This key is too short to sign with.")
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    s = pow(int.from_bytes(em, "big"), key.d, key.n)
    return s.to_bytes(k, "big")


def sign_challenge(key: RsaPrivateKey, challenge: str) -> str:
    """The ``sign`` field of ``verify_client``: the challenge string's UTF-8
    bytes, signed, base64-encoded — exactly as Seestar Studio sends it."""
    return base64.b64encode(
        sign_pkcs1v15_sha1(key, challenge.encode("utf-8"))).decode("ascii")
