"""Public (no-login) HTML pages — e.g. the per-game privacy policy.

Distinct from `api_bp` (JSON under /api/v1) and `admin_bp` (login-required
under /admin). These pages are world-readable.
"""

from __future__ import annotations

from flask import Blueprint

public_bp = Blueprint(
    "public",
    __name__,
    template_folder="../templates",
)

# Routes are registered via side-effect imports below.
from app.public import privacy  # noqa: E402,F401
