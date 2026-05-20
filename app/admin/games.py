"""Admin CRUD for Game rows."""

from __future__ import annotations

import json
import logging
from zoneinfo import available_timezones

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.admin import admin_bp
from app.admin.forms import GameForm
from app.extensions import db, redis_client
from app.models.admin_action import AdminAction
from app.models.game import Game
from app.services.cache import bump_game_version

log = logging.getLogger(__name__)


def _timezone_choices():
    return sorted([(tz, tz) for tz in available_timezones()])


def _populate_form(form: GameForm) -> None:
    form.timezone.choices = _timezone_choices()


def _audit(action: str, target: Game, details: dict | None = None) -> None:
    db.session.add(
        AdminAction(
            admin_user_id=current_user.id,
            action=action,
            target_type="game",
            target_id=target.id,
            details=details or {},
        )
    )


@admin_bp.route("/games")
@login_required
def games_list():
    games = db.session.execute(
        db.select(Game).order_by(Game.archived.asc(), Game.name.asc())
    ).scalars().all()
    return render_template("admin/games_list.html", games=games)


@admin_bp.route("/games/new", methods=["GET", "POST"])
@login_required
def games_new():
    form = GameForm()
    _populate_form(form)
    if form.validate_on_submit():
        if not _bounds_ok(form):
            return render_template("admin/game_form.html", form=form, mode="new"), 400
        try:
            game = Game(
                slug=form.slug.data,
                name=form.name.data,
                timezone=form.timezone.data,
                score_direction=form.score_direction.data,
                min_score=form.min_score.data,
                max_score=form.max_score.data,
                meta=json.loads(form.metadata_json.data or "{}"),
                archived=form.archived.data,
            )
            db.session.add(game)
            db.session.flush()
            _audit("game.create", game, {"slug": game.slug})
            db.session.commit()
            flash(f"Game '{game.slug}' created.", "success")
            return redirect(url_for("admin.games_list"))
        except ValueError as e:
            db.session.rollback()
            form.slug.errors.append(str(e))
            return render_template("admin/game_form.html", form=form, mode="new"), 400
        except Exception:
            db.session.rollback()
            log.exception("game_create_failed")
            flash("Could not create game (slug already in use?).", "danger")
            return render_template("admin/game_form.html", form=form, mode="new"), 400
    status = 400 if request.method == "POST" else 200
    return render_template("admin/game_form.html", form=form, mode="new"), status


@admin_bp.route("/games/<int:game_id>/edit", methods=["GET", "POST"])
@login_required
def games_edit(game_id: int):
    game = db.session.get(Game, game_id)
    if game is None:
        abort(404)
    form = GameForm(obj=None)
    _populate_form(form)

    if request.method == "GET":
        form.name.data = game.name
        form.slug.data = game.slug
        form.timezone.data = game.timezone
        form.score_direction.data = game.score_direction
        form.min_score.data = game.min_score
        form.max_score.data = game.max_score
        form.metadata_json.data = json.dumps(game.meta or {}, indent=2)
        form.archived.data = game.archived
        return render_template("admin/game_form.html", form=form, mode="edit", game=game)

    if form.validate_on_submit():
        if not _bounds_ok(form):
            return render_template(
                "admin/game_form.html", form=form, mode="edit", game=game
            ), 400
        try:
            game.name = form.name.data
            game.slug = form.slug.data
            game.timezone = form.timezone.data
            game.score_direction = form.score_direction.data
            game.min_score = form.min_score.data
            game.max_score = form.max_score.data
            game.meta = json.loads(form.metadata_json.data or "{}")
            game.archived = form.archived.data
            _audit("game.update", game, {"slug": game.slug})
            db.session.commit()
            # Bump cache version so consumers see new bounds / archived state.
            bump_game_version(redis_client, game.id)
            flash(f"Game '{game.slug}' updated.", "success")
            return redirect(url_for("admin.games_list"))
        except ValueError as e:
            db.session.rollback()
            form.slug.errors.append(str(e))
            return render_template(
                "admin/game_form.html", form=form, mode="edit", game=game
            ), 400
        except Exception:
            db.session.rollback()
            log.exception("game_update_failed")
            flash("Could not update game.", "danger")
            return render_template(
                "admin/game_form.html", form=form, mode="edit", game=game
            ), 400

    status = 400 if request.method == "POST" else 200
    return render_template("admin/game_form.html", form=form, mode="edit", game=game), status


def _bounds_ok(form: GameForm) -> bool:
    lo = form.min_score.data
    hi = form.max_score.data
    if lo is not None and hi is not None and lo > hi:
        form.min_score.errors.append("min_score must be <= max_score")
        return False
    return True
