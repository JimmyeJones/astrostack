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

_PBKDF2_ROUNDS = 200_000

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
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return hmac.compare_digest(digest, expected)


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
