"""Optional HTTP Basic access control.

Auth is **opt-in**: with no password set (the default) the app is wide open,
exactly as before. Once a password is configured every request must carry valid
HTTP Basic credentials — the browser's built-in login dialog handles this, so
there's no separate login page to build, and the same gate covers both the API
and the served SPA.

The password is never stored in the clear: we keep a PBKDF2-HMAC-SHA256 hash and
a per-install random salt in the settings file. Verification is constant-time.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os

_PBKDF2_ROUNDS = 200_000


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
