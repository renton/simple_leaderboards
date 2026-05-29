"""Admin UI blueprint."""

from __future__ import annotations

from flask import Blueprint, redirect, request, url_for
from flask_login import current_user

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="../templates",
)


@admin_bp.before_request
def _require_login_for_admin():
    # Allow the login and static paths anonymously.
    if request.endpoint in {"admin.login", "admin.static", "static"}:
        return None
    if not current_user.is_authenticated:
        return redirect(url_for("admin.login", next=request.path))
    return None


# Routes are registered via side-effect imports below.
from app.admin import api_test, auth, dashboard, games, scores, users  # noqa: E402,F401
