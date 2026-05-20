"""Admin CRUD for AdminUser rows."""

from __future__ import annotations

import logging

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.admin import admin_bp
from app.admin.forms import NewAdminForm
from app.extensions import db
from app.models.admin_action import AdminAction
from app.models.user import AdminUser

log = logging.getLogger(__name__)


@admin_bp.route("/users")
@login_required
def users_list():
    users = db.session.execute(
        db.select(AdminUser).order_by(AdminUser.created_at.desc())
    ).scalars().all()
    return render_template("admin/users_list.html", users=users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@login_required
def users_new():
    form = NewAdminForm()
    if form.validate_on_submit():
        try:
            user = AdminUser(username=form.username.data.strip())
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            db.session.add(
                AdminAction(
                    admin_user_id=current_user.id,
                    action="admin.create",
                    target_type="admin_user",
                    target_id=user.id,
                    details={"username": user.username},
                )
            )
            db.session.commit()
            flash(f"Admin '{user.username}' created.", "success")
            return redirect(url_for("admin.users_list"))
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("Username already in use.")
            return render_template("admin/user_form.html", form=form), 400
        except Exception:
            db.session.rollback()
            log.exception("admin_user_create_failed")
            flash("Could not create admin user.", "danger")
            return render_template("admin/user_form.html", form=form), 400
    from flask import request

    status = 400 if request.method == "POST" else 200
    return render_template("admin/user_form.html", form=form), status
