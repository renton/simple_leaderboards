"""Public privacy-policy pages.

`GET /privacy`          — index listing games that have a published policy.
`GET /privacy/<slug>`   — the per-game privacy policy.

The policy text is a standard template (templates/public/privacy_policy.html)
parameterized by the game's operator/contact fields. It comprehensively
describes the data this software collects, uses, and shares — satisfying the
Google Play requirement for an active, app-specific privacy-policy URL.
"""

from __future__ import annotations

from flask import abort, render_template

from app.extensions import db
from app.models.game import Game
from app.public import public_bp


@public_bp.route("/privacy")
def privacy_index():
    games = db.session.execute(
        db.select(Game).where(Game.archived.is_(False)).order_by(Game.name.asc())
    ).scalars().all()
    return render_template("public/privacy_index.html", games=games)


@public_bp.route("/privacy/<slug>")
def privacy_policy(slug: str):
    game = db.session.execute(
        db.select(Game).where(Game.slug == slug, Game.archived.is_(False))
    ).scalar_one_or_none()
    if game is None:
        abort(404)

    effective = game.privacy_updated_at or game.created_at
    return render_template(
        "public/privacy_policy.html",
        game=game,
        effective_date=effective,
    )
