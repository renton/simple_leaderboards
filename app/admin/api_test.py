"""Admin API test page — build and fire leaderboard requests interactively."""

from __future__ import annotations

from flask import render_template
from flask_login import login_required

from app.admin import admin_bp
from app.extensions import db
from app.models.game import Game
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
