"""Admin moderation actions on scores (soft-delete + restore)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app.admin import admin_bp
from app.extensions import db, redis_client
from app.models.admin_action import AdminAction
from app.models.game import Game
from app.models.score import Score
from app.services.cache import bump_game_version

log = logging.getLogger(__name__)


def _safe_next() -> str:
    target = request.form.get("next") or request.args.get("next")
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("admin.index")


def _audit(action: str, score: Score, details: dict | None = None) -> None:
    db.session.add(
        AdminAction(
            admin_user_id=current_user.id,
            action=action,
            target_type="score",
            target_id=score.id,
            details=details or {},
        )
    )


@admin_bp.route("/games/<int:game_id>/scores/clear", methods=["POST"])
@login_required
def scores_clear(game_id: int):
    game = db.session.get(Game, game_id)
    if game is None:
        abort(404)

    now = datetime.now(UTC)
    updated = (
        db.session.execute(
            db.update(Score)
            .where(Score.game_id == game_id, Score.deleted_at.is_(None))
            .values(deleted_at=now)
            .returning(Score.id)
        )
        .scalars()
        .all()
    )
    count = len(updated)

    if count:
        db.session.add(
            AdminAction(
                admin_user_id=current_user.id,
                action="scores.clear_all",
                target_type="game",
                target_id=game_id,
                details={"count": count, "slug": game.slug},
            )
        )
        db.session.commit()
        bump_game_version(redis_client, game_id)
        log.info("scores_cleared", extra={"game_id": game_id, "count": count, "admin": current_user.username})
        flash(f"Cleared {count} score(s) from '{game.slug}'.", "success")
    else:
        db.session.rollback()
        flash(f"No active scores to clear for '{game.slug}'.", "warning")

    return redirect(url_for("admin.games_list"))


@admin_bp.route("/scores/<int:score_id>/delete", methods=["POST"])
@login_required
def scores_delete(score_id: int):
    score = db.session.get(Score, score_id)
    if score is None:
        abort(404)
    if score.deleted_at is not None:
        flash("Score is already deleted.", "warning")
        return redirect(_safe_next())

    score.deleted_at = datetime.now(UTC)
    _audit(
        "score.soft_delete",
        score,
        {"game_id": score.game_id, "player_name": score.player_name, "score": str(score.score)},
    )
    db.session.commit()
    bump_game_version(redis_client, score.game_id)

    log.info(
        "score_soft_deleted",
        extra={"score_id": score.id, "admin": current_user.username},
    )
    flash(f"Score #{score.id} hidden from leaderboards.", "success")
    return redirect(_safe_next())


@admin_bp.route("/scores/<int:score_id>/restore", methods=["POST"])
@login_required
def scores_restore(score_id: int):
    score = db.session.get(Score, score_id)
    if score is None:
        abort(404)
    if score.deleted_at is None:
        flash("Score is not deleted.", "warning")
        return redirect(_safe_next())

    score.deleted_at = None
    _audit(
        "score.restore",
        score,
        {"game_id": score.game_id, "player_name": score.player_name, "score": str(score.score)},
    )
    db.session.commit()
    bump_game_version(redis_client, score.game_id)

    log.info(
        "score_restored",
        extra={"score_id": score.id, "admin": current_user.username},
    )
    flash(f"Score #{score.id} restored.", "success")
    return redirect(_safe_next())
