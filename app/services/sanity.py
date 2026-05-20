"""Score-submission sanity checks.

Invoked after schema validation and after the session token has been
verified+consumed. Operates on a `SanitizedSubmission` dataclass that the
route handler builds from the request payload.

Each rejection raises `SanityError` with a stable `code` matching one of
the error codes documented in `app/api/errors.py`. The error code is what
gets returned to the public client; the human-readable `detail` is logged
server-side but is NOT exposed in the API response by default (to avoid
giving cheaters a roadmap to the exact failure).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.models.game import Game
from app.services.name_normalize import (
    InvalidPlayerNameError,
    normalize_player_name,
)

SEED_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
CUSTOM_DATA_MAX_KEYS = 32
CUSTOM_DATA_MAX_VALUE_LEN = 256

CUSTOM_FIELD_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


class SanityError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclass
class SanitizedSubmission:
    player_name: str
    score: Decimal
    played_at: datetime | None
    seed: str | None
    custom_data: dict[str, Any]


def _check_player_name(raw: str) -> str:
    try:
        return normalize_player_name(raw)
    except InvalidPlayerNameError as e:
        raise SanityError("invalid_player_name", str(e)) from e


def _check_score_bounds(score: Decimal, game: Game) -> None:
    if game.min_score is not None and score < game.min_score:
        raise SanityError("score_out_of_bounds", "below min")
    if game.max_score is not None and score > game.max_score:
        raise SanityError("score_out_of_bounds", "above max")


def _check_played_at(
    played_at: datetime | None,
    token_issued_at: int | None,
    *,
    skew_seconds: int,
    now: datetime | None = None,
) -> datetime | None:
    if played_at is None:
        return None
    if played_at.tzinfo is None:
        raise SanityError("invalid_played_at", "played_at must be timezone-aware")
    now = now or datetime.now(timezone.utc)
    if played_at > now + timedelta(seconds=skew_seconds):
        raise SanityError("invalid_played_at", "played_at is in the future")
    if token_issued_at is not None:
        issued_dt = datetime.fromtimestamp(token_issued_at, tz=timezone.utc)
        if played_at < issued_dt - timedelta(seconds=skew_seconds):
            raise SanityError(
                "invalid_played_at",
                "played_at predates the session token",
            )
    return played_at


def _check_seed(seed: str | None) -> str | None:
    if seed is None:
        return None
    if not isinstance(seed, str) or not SEED_RE.match(seed):
        raise SanityError("invalid_seed", "seed must match [A-Za-z0-9_-]{1,64}")
    return seed


def _check_custom_data(payload: dict | None, game: Game) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise SanityError("invalid_custom_data", "custom_data must be an object")
    if len(payload) > CUSTOM_DATA_MAX_KEYS:
        raise SanityError("invalid_custom_data", "too many keys")

    schema = (game.meta or {}).get("custom_fields") or {}
    # If the game declares a schema, validate strictly; if not, accept arbitrary
    # primitives so games can iterate on payload shape without redeploying admin.
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or len(key) > 64:
            raise SanityError("invalid_custom_data", f"bad key {key!r}")
        if isinstance(value, str) and len(value) > CUSTOM_DATA_MAX_VALUE_LEN:
            raise SanityError("invalid_custom_data", f"value too long for {key!r}")
        if schema:
            field = schema.get(key)
            if field is None:
                raise SanityError("invalid_custom_data", f"unknown field {key!r}")
            expected = CUSTOM_FIELD_TYPES.get(field.get("type"))
            if expected is None:
                # Schema declared an unknown type — treat as no constraint.
                pass
            elif not isinstance(value, expected):
                raise SanityError("invalid_custom_data", f"bad type for {key!r}")
        out[key] = value

    if schema:
        for key, field in schema.items():
            if field.get("required") and key not in out:
                raise SanityError("invalid_custom_data", f"missing required {key!r}")
    return out


def sanitize_submission(
    *,
    game: Game,
    player_name: str,
    score: Decimal | int | float,
    played_at: datetime | None,
    seed: str | None,
    custom_data: dict | None,
    token_issued_at: int | None,
    skew_seconds: int,
    now: datetime | None = None,
) -> SanitizedSubmission:
    """Run every score-submission sanity check; return a sanitized result or raise."""
    name = _check_player_name(player_name)
    score_dec = Decimal(str(score))
    _check_score_bounds(score_dec, game)
    played_at_clean = _check_played_at(
        played_at, token_issued_at, skew_seconds=skew_seconds, now=now
    )
    seed_clean = _check_seed(seed)
    custom_clean = _check_custom_data(custom_data, game)
    return SanitizedSubmission(
        player_name=name,
        score=score_dec,
        played_at=played_at_clean,
        seed=seed_clean,
        custom_data=custom_clean,
    )
