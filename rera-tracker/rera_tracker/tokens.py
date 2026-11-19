"""Signed, tamper-proof tokens for links in emails and for web forms.

A token carries a *purpose* (so a confirmation link cannot be used as an
unsubscribe link), a *value* (an id or a timestamp) and an optional expiry.
Nothing is stored: the server recomputes the signature with its secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional

_TAG_BYTES = 16


class TokenError(Exception):
    """The token is malformed, forged, for another purpose, or expired."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _tag(secret: str, payload: bytes) -> bytes:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()[:_TAG_BYTES]


def sign(secret: str, purpose: str, value: str, expires_at: Optional[int] = None) -> str:
    if not secret:
        raise ValueError("a secret is required to sign tokens")
    if "|" in purpose or "|" in value:
        raise ValueError("purpose and value must not contain '|'")
    payload = ("%s|%s|%s" % (purpose, value, "" if expires_at is None else int(expires_at))).encode("utf-8")
    return _b64(payload) + "." + _b64(_tag(secret, payload))


def verify(secret: str, purpose: str, token: str, now: Optional[float] = None) -> str:
    """Return the value if the token is genuine, for this purpose and not expired."""
    try:
        body, tag = token.split(".")
        payload = _unb64(body)
        given = _unb64(tag)
    except (ValueError, TypeError, AttributeError):
        raise TokenError("malformed token") from None
    if not secret or not hmac.compare_digest(_tag(secret, payload), given):
        raise TokenError("bad signature")
    try:
        found_purpose, value, expires = payload.decode("utf-8").split("|", 2)
    except (UnicodeDecodeError, ValueError):
        raise TokenError("malformed token") from None
    if found_purpose != purpose:
        raise TokenError("token is for another purpose")
    if expires:
        try:
            expiry = int(expires)
        except ValueError:
            raise TokenError("malformed token") from None
        if (time.time() if now is None else now) > expiry:
            raise TokenError("token expired")
    return value
