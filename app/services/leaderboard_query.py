"""Build and execute a leaderboard SQL query for a given game + filters.

Produces a list of dicts (JSON-serializable) so the result can be cached
verbatim in Redis. Numeric scores are converted to floats for cache
compactness; if you need exact decimals client-side, request raw via the
admin UI (which queries the DB directly).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.score import Score
from app.services.time_ranges import range_to_bounds

MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 25

ALLOWED_SORT_FIELDS = frozenset({"score", "submitted_at", "played_at"})


@dataclass
class LeaderboardQuery:
    range: str = "all-time"
    seed: str | None = None
    name: str | None = None
    sort: str = "score"
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    def cache_params(self) -> dict[str, Any]:
        return {
            "range": self.range,
            "seed": self.seed,
            "name": self.name,
            "sort": self.sort,
            "page": self.page,
            "page_size": self.page_size,
        }


def _normalize(query: LeaderboardQuery) -> LeaderboardQuery:
    page = max(1, int(query.page))
    page_size = max(1, min(MAX_PAGE_SIZE, int(query.page_size)))
    sort = query.sort if query.sort in ALLOWED_SORT_FIELDS else "score"
    return LeaderboardQuery(
        range=query.range,
        seed=query.seed,
        name=query.name,
        sort=sort,
        page=page,
        page_size=page_size,
    )


def _score_serialize(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _row_to_dict(score: Score, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "id": score.id,
        "player_name": score.player_name,
        "score": _score_serialize(score.score),
        "submitted_at": score.submitted_at.isoformat() if score.submitted_at else None,
        "played_at": score.played_at.isoformat() if score.played_at else None,
        "seed": score.seed,
        "device_info": score.device_info or {},
        "custom_data": score.custom_data or {},
    }


def run_leaderboard_query(
    *,
    session: Session,
    game: Game,
    query: LeaderboardQuery,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    q = _normalize(query)

    base = select(Score).where(Score.game_id == game.id, Score.deleted_at.is_(None))

    if q.range != "all-time":
        start, end = range_to_bounds(q.range, game.timezone, now_utc=now_utc)
        if start is not None and end is not None:
            base = base.where(Score.submitted_at >= start, Score.submitted_at < end)

    if q.seed is not None:
        base = base.where(Score.seed == q.seed)
    if q.name:
        base = base.where(Score.player_name.ilike(f"%{q.name}%"))

    # Sort. score uses the game's preferred direction; the other sort keys
    # default to descending (newest/most-recent first).
    if q.sort == "score":
        order_col = Score.score.desc() if game.score_direction == "desc" else Score.score.asc()
    elif q.sort == "submitted_at":
        order_col = Score.submitted_at.desc()
    else:  # played_at
        order_col = Score.played_at.desc()

    # Stable secondary sort: earlier submission wins ties.
    ordered = base.order_by(order_col, Score.submitted_at.asc(), Score.id.asc())

    # Count via subquery (separate query to keep ORM simple).
    from sqlalchemy import func

    count_q = (
        select(func.count())
        .select_from(Score)
        .where(Score.game_id == game.id, Score.deleted_at.is_(None))
    )
    if q.range != "all-time":
        start, end = range_to_bounds(q.range, game.timezone, now_utc=now_utc)
        if start is not None and end is not None:
            count_q = count_q.where(
                Score.submitted_at >= start, Score.submitted_at < end
            )
    if q.seed is not None:
        count_q = count_q.where(Score.seed == q.seed)
    if q.name:
        count_q = count_q.where(Score.player_name.ilike(f"%{q.name}%"))
    total = int(session.execute(count_q).scalar_one())

    offset = (q.page - 1) * q.page_size
    paged = ordered.limit(q.page_size).offset(offset)
    rows = session.execute(paged).scalars().all()

    results = [_row_to_dict(row, rank=offset + i + 1) for i, row in enumerate(rows)]
    return {
        "page": q.page,
        "page_size": q.page_size,
        "total": total,
        "results": results,
    }
