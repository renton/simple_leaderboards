"""Score-submission session tokens.

Bootstrap flow:
1. Client calls `POST /api/v1/sessions` with a game slug.
2. Server resolves slug -> game_id, generates a random `nonce`, stores
   `sess:nonce:<nonce>` in Redis with a TTL, and signs the payload
   `{gid, iat, nonce}` with `itsdangerous.URLSafeTimedSerializer`.
3. Server returns the signed token to the client.

Score submission:
1. Client sends the token in `Authorization: Bearer <token>` along with the
   score payload.
2. Server verifies the signature and max_age via itsdangerous.
3. Server checks that the token's `gid` matches the resolved game_id of the
   score's game slug.
4. Server `DEL`s the nonce in Redis. If DEL returns 0, the nonce was either
   already consumed or expired — reject as `invalid_session`.

Tokens are single-use: each score submission consumes one. Tokens cannot
be revoked individually; rotate `SECRET_KEY` to invalidate all outstanding
tokens.

Tokens are signed, not encrypted — the payload is integrity-protected but
visible. That is intentional: there's nothing secret in `{gid, iat, nonce}`.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SALT = "leaderboards-session-v1"
NONCE_BYTES = 16
NONCE_KEY_PREFIX = "sess:nonce:"


class InvalidSessionTokenError(Exception):
    """Raised when a session token fails verification for any reason."""


@dataclass(frozen=True)
class IssuedToken:
    token: str
    nonce: str
    game_id: int
    issued_at: int  # unix seconds


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=SALT)


def token_fingerprint(token: str) -> str:
    """Stable 12-char prefix of sha256(token) for safe logging."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def issue_token(
    *,
    secret_key: str,
    game_id: int,
    redis_client: Any,
    ttl_seconds: int,
) -> IssuedToken:
    """Issue a new session token for the given game_id."""
    nonce = secrets.token_urlsafe(NONCE_BYTES)
    # NX prevents the astronomically unlikely collision; if it returns None
    # (key already exists), regenerate. In practice this never fires.
    while not redis_client.set(
        NONCE_KEY_PREFIX + nonce, "1", ex=ttl_seconds, nx=True
    ):  # pragma: no cover
        nonce = secrets.token_urlsafe(NONCE_BYTES)

    issued_at_serializer = _serializer(secret_key)
    payload = {"gid": int(game_id), "nonce": nonce}
    token = issued_at_serializer.dumps(payload)

    # The exact `iat` lives in itsdangerous's timestamp portion; we expose it
    # back as a convenience for the caller's API response.
    import time

    return IssuedToken(token=token, nonce=nonce, game_id=int(game_id), issued_at=int(time.time()))


def verify_and_consume(
    *,
    secret_key: str,
    token: str,
    expected_game_id: int,
    redis_client: Any,
    max_age_seconds: int,
) -> dict[str, Any]:
    """Verify the token and atomically consume its single-use nonce.

    Returns the decoded payload on success; raises InvalidSessionTokenError
    on any failure (bad signature, expired, gid mismatch, already consumed).
    """
    serializer = _serializer(secret_key)
    try:
        payload = serializer.loads(token, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise InvalidSessionTokenError("token expired") from e
    except BadSignature as e:
        raise InvalidSessionTokenError("bad signature") from e

    if not isinstance(payload, dict):
        raise InvalidSessionTokenError("malformed payload")

    gid = payload.get("gid")
    nonce = payload.get("nonce")
    if not isinstance(gid, int) or not isinstance(nonce, str) or not nonce:
        raise InvalidSessionTokenError("malformed payload")
    if gid != int(expected_game_id):
        raise InvalidSessionTokenError("token bound to a different game")

    deleted = redis_client.delete(NONCE_KEY_PREFIX + nonce)
    if not deleted:
        raise InvalidSessionTokenError("nonce already consumed or expired")

    return payload


def issued_at_from_token(*, secret_key: str, token: str) -> int | None:
    """Return the signed issuance timestamp (unix seconds) without consuming
    the nonce. Used by sanity checks that compare `played_at` to issuance time.
    Returns None on any signature failure.
    """
    serializer = _serializer(secret_key)
    try:
        ts = serializer.loads(token, return_timestamp=True)
    except (BadSignature, SignatureExpired):
        return None
    # itsdangerous returns (payload, datetime). Coerce to int unix seconds.
    if not isinstance(ts, tuple) or len(ts) != 2:
        return None
    _payload, dt = ts
    return int(dt.timestamp())
