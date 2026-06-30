"""Admin dashboard: pick a game and view its leaderboard with rich filters."""

from __future__ import annotations

from datetime import date as date_cls, timedelta

from flask import render_template, request
from flask_login import login_required

from app.admin import admin_bp
from app.extensions import db
from app.models.game import Game
from app.models.score import Score
from app.services.daily_seed import date_to_seed, godot_string_hash, looks_like_date
from app.services.leaderboard_query import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    LeaderboardQuery,
    run_leaderboard_query,
)
from app.services.time_ranges import VALID_RANGES


def _safe_int(raw: str | None, default: int, *, lo: int, hi: int) -> int:
    if raw is None:
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


@admin_bp.route("/")
@login_required
def index():
    games = db.session.execute(
        db.select(Game).order_by(Game.archived.asc(), Game.name.asc())
    ).scalars().all()

    selected_game = None
    selected_id = request.args.get("game_id")
    if selected_id and selected_id.isdigit():
        selected_game = db.session.get(Game, int(selected_id))
    if selected_game is None and games:
        for g in games:
            if not g.archived:
                selected_game = g
                break
        if selected_game is None:
            selected_game = games[0]

    range_name = request.args.get("range", "all-time")
    if range_name not in VALID_RANGES:
        range_name = "all-time"

    # seed_date is a YYYY-MM-DD string submitted by the calendar widget.
    # We convert it to the hash for the DB query.
    seed_raw = (request.args.get("seed") or "").strip()
    seed_date = seed_raw if looks_like_date(seed_raw) else ""
    seed = date_to_seed(seed_date) if seed_date else None

    name = (request.args.get("name") or "").strip() or None
    sort = request.args.get("sort", "score")
    if sort not in {"score", "submitted_at", "played_at"}:
        sort = "score"

    page = _safe_int(request.args.get("page"), 1, lo=1, hi=10_000)
    page_size = _safe_int(
        request.args.get("page_size"),
        DEFAULT_PAGE_SIZE,
        lo=1,
        hi=MAX_PAGE_SIZE,
    )

    # Fetch distinct seeds for the selected game, then reverse-map to dates
    # by hashing a 2-year window and checking for matches.
    active_dates: list[str] = []
    if selected_game is not None:
        seed_rows = db.session.execute(
            db.select(Score.seed)
            .where(Score.game_id == selected_game.id, Score.seed.is_not(None), Score.deleted_at.is_(None))
            .distinct()
        ).scalars().all()

        seed_set = {str(s) for s in seed_rows}
        if seed_set:
            today_d = date_cls.today()
            d = today_d - timedelta(days=730)
            while d <= today_d:
                ds = d.strftime("%Y-%m-%d")
                if str(godot_string_hash(ds)) in seed_set:
                    active_dates.append(ds)
                d += timedelta(days=1)

    result = None
    if selected_game is not None:
        query = LeaderboardQuery(
            range=range_name,
            seed=seed,
            name=name,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        result = run_leaderboard_query(
            session=db.session,
            game=selected_game,
            query=query,
        )

    return render_template(
        "admin/dashboard.html",
        games=games,
        selected_game=selected_game,
        result=result,
        active_dates=active_dates,
        filters={
            "range": range_name,
            "seed_date": seed_date,
            "name": name or "",
            "sort": sort,
            "page": page,
            "page_size": page_size,
        },
        range_options=sorted(VALID_RANGES, key=lambda r: ["all-time", "yearly", "monthly", "weekly", "daily", "hourly"].index(r)),
    )
