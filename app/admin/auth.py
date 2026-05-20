"""Admin login / logout / lockout."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_required, login_user, logout_user

from app.admin import admin_bp
from app.admin.forms import LoginForm
from app.extensions import db, limiter
from app.models.user import AdminUser

log = logging.getLogger(__name__)


def _admin_login_limit():
    return current_app.config["RATELIMIT_ADMIN_LOGIN"]


def _safe_next(target: str | None) -> str | None:
    """Only honor `next` if it's a same-app, relative path (prevents open redirect)."""
    if not target:
        return None
    if target.startswith("/") and not target.startswith("//"):
        return target
    return None


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit(_admin_login_limit, methods=["POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        user = db.session.execute(
            db.select(AdminUser).where(AdminUser.username == username)
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if user is None:
            # Always run argon2 verify on a sentinel to keep timing roughly equal.
            from argon2 import PasswordHasher

            try:
                PasswordHasher().verify(
                    "$argon2id$v=19$m=65536,t=3,p=4$"
                    "c29tZXNhbHQAAAAAAAAAAA$"
                    "RdescudvJCsgt3ub+b+dWRWJTmaaJObG",
                    form.password.data,
                )
            except Exception:
                pass
            log.info("admin_login_failed_unknown_user", extra={"username": username})
            flash("Invalid credentials.", "danger")
            return render_template("admin/login.html", form=form), 401

        if user.is_locked(now):
            log.info("admin_login_failed_locked", extra={"username": username})
            flash("This account is temporarily locked. Try again later.", "danger")
            return render_template("admin/login.html", form=form), 423

        if not user.check_password(form.password.data):
            user.register_failed_login(
                max_attempts=current_app.config["ADMIN_MAX_FAILED_LOGINS"],
                lockout_minutes=current_app.config["ADMIN_LOCKOUT_MINUTES"],
            )
            db.session.commit()
            log.info(
                "admin_login_failed_bad_password",
                extra={"username": username, "attempts": user.failed_login_attempts},
            )
            flash("Invalid credentials.", "danger")
            return render_template("admin/login.html", form=form), 401

        # Successful login. Rotate session ID to mitigate session fixation.
        session.clear()
        login_user(user, remember=False)
        user.register_successful_login()
        db.session.commit()

        next_target = _safe_next(request.args.get("next")) or url_for("admin.index")
        log.info("admin_login_succeeded", extra={"username": username})
        return redirect(next_target)

    return render_template("admin/login.html", form=form)


@admin_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Signed out.", "info")
    return redirect(url_for("admin.login"))
