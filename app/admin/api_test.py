"""Admin API test page — build and fire leaderboard requests interactively."""

from __future__ import annotations

from flask import jsonify, render_template, request
from flask_login import login_required

from app.admin import admin_bp
from app.extensions import db
from app.models.game import Game
from app.models.score import Score
from app.services.leaderboard_query import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


@admin_bp.route("/api-test")
@login_required
def api_test():
    games = db.session.execute(
        db.select(Game).where(Game.archived.is_(False)).order_by(Game.name.asc())
    ).scalars().all()

    range_options = ["all-time", "yearly", "monthly", "weekly", "daily", "hourly"]
    sort_options = ["score", "submitted_at", "played_at"]

    return render_template(
        "admin/api_test.html",
        games=games,
        range_options=range_options,
        sort_options=sort_options,
        default_page_size=DEFAULT_PAGE_SIZE,
        max_page_size=MAX_PAGE_SIZE,
    )


@admin_bp.route("/api/seeds")
@login_required
def api_seeds():
    slug = request.args.get("game", "")
    game = db.session.execute(
        db.select(Game).where(Game.slug == slug)
    ).scalar_one_or_none()
    if game is None:
        return jsonify(seeds=[])
    seeds = db.session.execute(
        db.select(Score.seed)
        .where(Score.game_id == game.id, Score.seed.is_not(None), Score.deleted_at.is_(None))
        .distinct()
        .order_by(Score.seed.desc())
    ).scalars().all()
    return jsonify(seeds=list(seeds))
