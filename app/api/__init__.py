"""Public JSON API blueprint."""

from __future__ import annotations

from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Routes are registered via side-effect imports below.
from app.api import champions, leaderboards, scores, sessions  # noqa: E402,F401
