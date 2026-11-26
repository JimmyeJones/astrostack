"""Optional HTTP Basic access control.

Auth is **opt-in**: with no password set (the default) the app is wide open,
exactly as before. Once a password is configured every request must carry valid
HTTP Basic credentials — the browser's built-in login dialog handles this, so
there's no separate login page to build, and the same gate covers both the API
and the served SPA.

The password is never stored in the clear: we keep a PBKDF2-HMAC-SHA256 hash and
a per-install random salt in the settings file. Verification is constant-time.

There is a **second, weaker credential**: an optional *read-only token*, for a
locked-down local account that needs to read diagnostics and must not be able to
do anything else. Before it existed there was one shared secret and no roles, so
letting an observer read ``GET /api/logs`` meant handing it the credential that
also posts to ``/api/stack``, rewrites ``/api/settings`` and deletes targets —
and the only alternative was putting that account in the ``docker`` group, which
is root on the host. The token is stored the same way the password is, is
accepted only for ``GET`` and only on the small diagnostics allowlist the gate in
:mod:`webapp.main` owns, and is **off unless minted**. It is deliberately *not*
implemented by opening those paths to everyone: they still need a credential.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import secrets
import threading
from collections import OrderedDict

_PBKDF2_ROUNDS = 200_000

#: How many recently-*accepted* credentials :func:`_verify` remembers. The gate
#: checks the password on **every** request, and 200,000 PBKDF2 rounds is ~190 ms
#: of CPU — so with a password set, 30 parallel GETs took 5.4 s instead of 0.5 s
#: and a gallery of thumbnails queued for tens of seconds (full audit 2026-11-26,
#: backend.md finding 4). A handful of entries covers the owner's browser, the
#: read-only token and a spare; it is a bound, not a tuning knob.
_ACCEPTED_CACHE_SIZE = 16

#: Process-lifetime random key for the cache's fingerprints. The cache never
#: holds a password — only ``HMAC(key, salt ‖ hash ‖ password)`` — and the key
#: never leaves memory, so a fingerprint is useless to anyone who reads it.
_CACHE_KEY = os.urandom(32)
_accepted: OrderedDict[bytes, None] = OrderedDict()
_accepted_lock = threading.Lock()

#: Username the read-only token is presented under, so one
#: ``Authorization: Basic`` header can carry either credential and the gate can
#: tell which it is looking at (``curl -u readonly:<token> …``). Fixed rather
#: than configurable: it is an address, not a secret, and a settings key to get
#: wrong would buy nothing. A ``Bearer`` header carrying the token works too,
#: which is what a script would reach for.
READONLY_USERNAME = "readonly"

#: Bytes of entropy behind a minted token. 32 → a 43-character URL-safe string;
#: nothing types this, it gets pasted into an agent's config.
_READONLY_TOKEN_BYTES = 32


def hash_password(password: str) -> tuple[str, str]:
    """Return ``(hash_hex, salt_hex)`` for a new password."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return digest.hex(), salt.hex()


def _verify(password: str, hash_hex: str, salt_hex: str) -> bool:
    """Constant-time PBKDF2 check, remembering only the answers that were *yes*.

    A credential that already verified against this exact ``(hash, salt)`` is
    accepted from a small in-memory cache instead of paying the KDF again. Only
    successes are cached, so a wrong guess still costs the full KDF every time
    (the brute-force rate is unchanged). The fingerprint includes the stored hash
    and salt, so changing or clearing the password — or rotating the read-only
    token — orphans every old entry: nothing has to be invalidated by hand, and a
    revoked credential can never be let in from the cache.
    """
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    if not expected:
        return False
    fingerprint = hmac.new(
        _CACHE_KEY,
        b"\0".join((salt, expected, password.encode("utf-8"))),
        hashlib.sha256,
    ).digest()
    with _accepted_lock:
        if fingerprint in _accepted:
            _accepted.move_to_end(fingerprint)
            return True
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    ok = hmac.compare_digest(digest, expected)
    if ok:
        with _accepted_lock:
            _accepted[fingerprint] = None
            _accepted.move_to_end(fingerprint)
            while len(_accepted) > _ACCEPTED_CACHE_SIZE:
                _accepted.popitem(last=False)
    return ok


def _forget_accepted() -> None:
    """Empty the accepted-credential cache (tests; nothing in the app needs it,
    because a changed hash or salt already orphans every entry)."""
    with _accepted_lock:
        _accepted.clear()


def is_enabled(settings) -> bool:  # noqa: ANN001 — Settings (avoid import cycle)
    return bool(getattr(settings, "auth_password_hash", ""))


def check_basic_auth(settings, header_value: str | None) -> bool:  # noqa: ANN001
    """Validate an ``Authorization: Basic ...`` header against the settings.

    Returns True when auth is disabled, or when the supplied username+password
    match. Username comparison is constant-time too so a wrong username can't be
    distinguished by timing from a wrong password.
    """
    if not is_enabled(settings):
        return True
    if not header_value or not header_value.lower().startswith("basic "):
        return False
    try:
        raw = base64.b64decode(header_value.split(" ", 1)[1].strip()).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return False
    username, _, password = raw.partition(":")
    user_ok = hmac.compare_digest(
        username.encode("utf-8"),
        str(getattr(settings, "auth_username", "admin")).encode("utf-8"),
    )
    pass_ok = _verify(password, settings.auth_password_hash, settings.auth_salt)
    # Evaluate both regardless (don't short-circuit) to keep timing flat.
    return user_ok and pass_ok


# ---- the read-only token ---------------------------------------------------

def make_readonly_token() -> str:
    """A fresh read-only token. Shown to the owner once and never stored."""
    return secrets.token_urlsafe(_READONLY_TOKEN_BYTES)


def hash_readonly_token(token: str) -> tuple[str, str]:
    """``(hash_hex, salt_hex)`` for a token — the password's own KDF, rounds and
    per-install salt, so the weaker *privilege* is not also a weaker *secret*."""
    return hash_password(token)


def readonly_is_enabled(settings) -> bool:  # noqa: ANN001 — Settings (import cycle)
    return bool(getattr(settings, "readonly_token_hash", ""))


def check_readonly_auth(settings, header_value: str | None) -> bool:  # noqa: ANN001
    """Does this ``Authorization`` header carry the read-only token?

    Unlike :func:`check_basic_auth` this **never** returns True by default: no
    token minted, no header, or a header that isn't the token → False. It answers
    only "is this the read-only credential", never "may this request proceed" —
    the method and path allowlist live in the gate, which is the one place that
    decides access.

    Accepts the token as ``Basic`` under :data:`READONLY_USERNAME` (so the same
    header shape as the password, and the browser dialog works) or as
    ``Bearer <token>`` (what a script reaches for). Comparison is constant-time
    either way, and the username is compared constant-time too, so which half was
    wrong can't be read off the timing.
    """
    if not readonly_is_enabled(settings):
        return False
    if not header_value:
        return False
    scheme, _, rest = header_value.partition(" ")
    rest = rest.strip()
    if scheme.lower() == "bearer":
        return bool(rest) and _verify(
            rest, settings.readonly_token_hash, settings.readonly_token_salt)
    if scheme.lower() != "basic":
        return False
    try:
        raw = base64.b64decode(rest).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return False
    username, _, token = raw.partition(":")
    user_ok = hmac.compare_digest(
        username.encode("utf-8"), READONLY_USERNAME.encode("utf-8"))
    token_ok = _verify(
        token, settings.readonly_token_hash, settings.readonly_token_salt)
    return user_ok and token_ok
