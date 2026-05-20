"""POST /api/v1/sessions — issue a session token for a game."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from flask import current_app, jsonify, request
from pydantic import ValidationError

from app.api import api_bp
from app.api.errors import api_error_response
from app.extensions import db, limiter, redis_client
from app.models.game import Game
from app.schemas.sessions import SessionRequestIn
from app.services.session_tokens import issue_token, token_fingerprint

log = logging.getLogger(__name__)


def _rate_limit():
    return current_app.config["RATELIMIT_SESSIONS"]


@api_bp.post("/sessions")
@limiter.limit(_rate_limit)
def create_session():
    raw = request.get_json(silent=True)
    if not isinstance(raw, dict):
        return api_error_response("invalid_request", status=400)

    try:
        payload = SessionRequestIn.model_validate(raw)
    except ValidationError:
        return api_error_response("invalid_request", status=400)

    game = db.session.execute(
        db.select(Game).where(Game.slug == payload.game, Game.archived.is_(False))
    ).scalar_one_or_none()
    if game is None:
        return api_error_response("game_not_found", status=404)

    ttl = current_app.config["SESSION_TTL_SECONDS"]
    issued = issue_token(
        secret_key=current_app.config["SECRET_KEY"],
        game_id=game.id,
        redis_client=redis_client,
        ttl_seconds=ttl,
    )

    log.info(
        "session_issued",
        extra={
            "game": payload.game,
            "fingerprint": token_fingerprint(issued.token),
        },
    )

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    return jsonify(
        {
            "session_token": issued.token,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }
    ), 201
