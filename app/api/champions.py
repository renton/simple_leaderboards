"""GET /api/v1/champions — cached, time-windowed daily-seed win tally per player."""

from __future__ import annotations

import logging

from flask import current_app, jsonify, request
from pydantic import ValidationError

from app.api import api_bp
from app.api.errors import api_error_response
from app.extensions import db, limiter, redis_client
from app.models.game import Game
from app.schemas.champions import ChampionsQueryIn
from app.services.cache import get_or_set
from app.services.champions import ChampionsQuery, run_champions_query

log = logging.getLogger(__name__)


def _rate_limit():
    return current_app.config["RATELIMIT_CHAMPIONS"]


def _parse_params(args):
    raw = {k: args.get(k) for k in args}
    for k in ("page", "page_size"):
        if k in raw and raw[k] is not None:
            try:
                raw[k] = int(raw[k])
            except ValueError:
                raise ValueError(f"{k} must be an integer") from None
    return raw


@api_bp.get("/champions")
@limiter.limit(_rate_limit)
def get_champions():
    try:
        raw = _parse_params(request.args)
    except ValueError:
        return api_error_response("invalid_request", status=400)

    try:
        params = ChampionsQueryIn.model_validate(raw)
    except ValidationError:
        return api_error_response("invalid_request", status=400)

    game = db.session.execute(
        db.select(Game).where(Game.slug == params.game, Game.archived.is_(False))
    ).scalar_one_or_none()
    if game is None:
        return api_error_response("game_not_found", status=404)

    query = ChampionsQuery(
        since=params.since,
        until=params.until,
        page=params.page,
        page_size=params.page_size,
    )

    game_id = game.id

    def _load():
        from app.models.game import Game as G

        g = db.session.execute(db.select(G).where(G.id == game_id)).scalar_one()
        return run_champions_query(session=db.session, game=g, query=query)

    result, hit = get_or_set(
        redis_client=redis_client,
        game_id=game_id,
        params=query.cache_params(),
        loader=_load,
        ttl_seconds=current_app.config["CACHE_TTL_SECONDS"],
    )

    response = jsonify({"game": params.game, **result})
    response.headers["X-Cache"] = "HIT" if hit else "MISS"
    return response
