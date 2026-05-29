"""Champions query: for each distinct seed, find the winner; tally wins per player.

Computed on read, with the same per-game version-key cache invalidation scheme
as the leaderboards endpoint. No aggregate table — the SQL rides the partial
index `ix_scores_champions` on (game_id, submitted_at, seed) and the existing
`ix_scores_game_seed_score`, so it's bounded even on hot games.

Tie-breaking within a seed: better score wins; ties broken by earlier
submitted_at, then by lower id (deterministic, matches the leaderboard query).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.score import Score

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 50


@dataclass
class ChampionsQuery:
    since: datetime | None = None
    until: datetime | None = None
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    def cache_params(self) -> dict[str, Any]:
        return {
            "_endpoint": "champions",
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
            "page": self.page,
            "page_size": self.page_size,
        }


def _normalize(query: ChampionsQuery) -> ChampionsQuery:
    return ChampionsQuery(
        since=query.since,
        until=query.until,
        page=max(1, int(query.page)),
        page_size=max(1, min(MAX_PAGE_SIZE, int(query.page_size))),
    )


def _base_filter(stmt, game: Game, q: ChampionsQuery):
    stmt = stmt.where(
        Score.game_id == game.id,
        Score.seed.is_not(None),
        Score.deleted_at.is_(None),
    )
    if q.since is not None:
        stmt = stmt.where(Score.submitted_at >= q.since)
    if q.until is not None:
        stmt = stmt.where(Score.submitted_at < q.until)
    return stmt


def run_champions_query(
    *,
    session: Session,
    game: Game,
    query: ChampionsQuery,
) -> dict[str, Any]:
    q = _normalize(query)

    score_order = (
        Score.score.desc() if game.score_direction == "desc" else Score.score.asc()
    )
    rn = (
        func.row_number()
        .over(
            partition_by=Score.seed,
            order_by=[score_order, Score.submitted_at.asc(), Score.id.asc()],
        )
        .label("rn")
    )

    ranked = _base_filter(
        select(Score.seed.label("seed"), Score.player_name.label("player_name"), rn),
        game,
        q,
    ).cte("seed_winners")

    total_seeds = int(
        session.execute(
            _base_filter(select(func.count(distinct(Score.seed))), game, q)
        ).scalar_one()
    )

    winners_grouped = (
        select(ranked.c.player_name, func.count().label("wins"))
        .where(ranked.c.rn == 1)
        .group_by(ranked.c.player_name)
    )

    total_champions = int(
        session.execute(
            select(func.count()).select_from(winners_grouped.subquery())
        ).scalar_one()
    )

    offset = (q.page - 1) * q.page_size
    paged = (
        winners_grouped.order_by(
            func.count().desc(), ranked.c.player_name.asc()
        )
        .limit(q.page_size)
        .offset(offset)
    )
    rows = session.execute(paged).all()

    results = [
        {"rank": offset + i + 1, "player_name": r.player_name, "wins": int(r.wins)}
        for i, r in enumerate(rows)
    ]

    return {
        "since": q.since.isoformat() if q.since else None,
        "until": q.until.isoformat() if q.until else None,
        "total_seeds": total_seeds,
        "page": q.page,
        "page_size": q.page_size,
        "total": total_champions,
        "results": results,
    }
