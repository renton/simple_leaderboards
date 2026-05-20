"""POST /api/v1/scores — submit a score guarded by a session token."""

from __future__ import annotations

import logging

from flask import current_app, jsonify, request
from pydantic import ValidationError

from app.api import api_bp
from app.api.errors import api_error_response
from app.extensions import db, limiter, redis_client
from app.models.game import Game
from app.models.score import Score
from app.schemas.scores import ScoreSubmitIn
from app.services.cache import bump_game_version
from app.services.device_info import build_device_info
from app.services.sanity import SanityError, sanitize_submission
from app.services.session_tokens import (
    InvalidSessionTokenError,
    issued_at_from_token,
    token_fingerprint,
    verify_and_consume,
)

log = logging.getLogger(__name__)


def _rate_limit():
    return current_app.config["RATELIMIT_SCORES"]


def _extract_bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


@api_bp.post("/scores")
@limiter.limit(_rate_limit)
def submit_score():
    token = _extract_bearer_token()
    if token is None:
        return api_error_response("invalid_session", status=401)

    raw = request.get_json(silent=True)
    if not isinstance(raw, dict):
        return api_error_response("invalid_request", status=400)

    try:
        payload = ScoreSubmitIn.model_validate(raw)
    except ValidationError:
        return api_error_response("invalid_request", status=400)

    game = db.session.execute(
        db.select(Game).where(Game.slug == payload.game, Game.archived.is_(False))
    ).scalar_one_or_none()
    if game is None:
        return api_error_response("game_not_found", status=404)

    # Verify+consume the session token. We pull the issuance timestamp first
    # (no consumption) for the sanity check, then call verify_and_consume which
    # atomically consumes the nonce.
    secret = current_app.config["SECRET_KEY"]
    token_iat = issued_at_from_token(secret_key=secret, token=token)

    try:
        verify_and_consume(
            secret_key=secret,
            token=token,
            expected_game_id=game.id,
            redis_client=redis_client,
            max_age_seconds=current_app.config["SESSION_TTL_SECONDS"],
        )
    except InvalidSessionTokenError:
        log.info(
            "score_rejected_invalid_session",
            extra={
                "game": payload.game,
                "fingerprint": token_fingerprint(token),
            },
        )
        return api_error_response("invalid_session", status=401)

    try:
        clean = sanitize_submission(
            game=game,
            player_name=payload.player_name,
            score=payload.score,
            played_at=payload.played_at,
            seed=payload.seed,
            custom_data=payload.custom_data,
            token_issued_at=token_iat,
            skew_seconds=current_app.config["MAX_PLAYED_AT_SKEW_SECONDS"],
        )
    except SanityError as e:
        log.info(
            "score_rejected_sanity",
            extra={
                "game": payload.game,
                "code": e.code,
                "detail": e.detail,
                "fingerprint": token_fingerprint(token),
            },
        )
        return api_error_response(e.code)

    device_info = build_device_info(
        request.headers.get("User-Agent"),
        payload.client_info,
    )

    row = Score(
        game_id=game.id,
        player_name=clean.player_name,
        score=clean.score,
        played_at=clean.played_at,
        seed=clean.seed,
        device_info=device_info,
        custom_data=clean.custom_data,
    )
    db.session.add(row)
    db.session.commit()

    bump_game_version(redis_client, game.id)

    log.info(
        "score_submitted",
        extra={
            "game": payload.game,
            "score_id": row.id,
            "fingerprint": token_fingerprint(token),
        },
    )

    return jsonify({"id": row.id}), 201
