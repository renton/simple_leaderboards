"""GET /api/v1/leaderboards — cached, filtered, paginated read endpoint."""

from __future__ import annotations

import logging

from flask import current_app, jsonify, request
from pydantic import ValidationError

from app.api import api_bp
from app.api.errors import api_error_response
from app.extensions import db, limiter, redis_client
from app.models.game import Game
from app.schemas.leaderboards import LeaderboardQueryIn
from app.services.cache import get_or_set
from app.services.leaderboard_query import LeaderboardQuery, run_leaderboard_query

log = logging.getLogger(__name__)


def _rate_limit():
    return current_app.config["RATELIMIT_LEADERBOARDS"]


def _parse_params(args):
    # Flask's request.args is a MultiDict; pydantic wants plain dict.
    raw = {k: args.get(k) for k in args.keys()}
    # Coerce numeric params; Pydantic accepts string ints but explicit is safer
    # for stable cache keys (params_hash sees these as plain ints).
    for k in ("page", "page_size"):
        if k in raw and raw[k] is not None:
            try:
                raw[k] = int(raw[k])
            except ValueError:
                raise ValueError(f"{k} must be an integer")
    return raw


@api_bp.get("/leaderboards")
@limiter.limit(_rate_limit)
def get_leaderboards():
    try:
        raw = _parse_params(request.args)
    except ValueError:
        return api_error_response("invalid_request", status=400)

    try:
        params = LeaderboardQueryIn.model_validate(raw)
    except ValidationError:
        return api_error_response("invalid_request", status=400)

    game = db.session.execute(
        db.select(Game).where(Game.slug == params.game, Game.archived.is_(False))
    ).scalar_one_or_none()
    if game is None:
        return api_error_response("game_not_found", status=404)

    query = LeaderboardQuery(
        range=params.range,
        seed=params.seed,
        name=params.name,
        sort=params.sort,
        page=params.page,
        page_size=params.page_size,
    )

    # Snapshot the game's pure scalar attributes the query needs, so the cached
    # closure doesn't capture a session-bound ORM object.
    game_id = game.id
    game_tz = game.timezone
    game_dir = game.score_direction

    def _load():
        from app.models.game import Game as G

        # Re-fetch a session-attached game inside the loader (the outer one
        # may be detached by the time this runs).
        g = db.session.execute(db.select(G).where(G.id == game_id)).scalar_one()
        return run_leaderboard_query(session=db.session, game=g, query=query)

    result, hit = get_or_set(
        redis_client=redis_client,
        game_id=game_id,
        params=query.cache_params(),
        loader=_load,
        ttl_seconds=current_app.config["CACHE_TTL_SECONDS"],
    )

    response = jsonify(result)
    response.headers["X-Cache"] = "HIT" if hit else "MISS"
    # Touch unused vars so ruff doesn't complain.
    _ = (game_tz, game_dir)
    return response
