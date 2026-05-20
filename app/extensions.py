"""Shared Flask extension singletons.

These are constructed without an app and bound in `create_app()` via `init_app`.
"""

from __future__ import annotations

from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def _rate_limit_key() -> str:
    # ProxyFix has already rewritten remote_addr from the trusted X-Forwarded-For.
    return get_remote_address() or "unknown"


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=[],
    headers_enabled=True,
)


class _RedisClientProxy:
    """Lazy proxy around redis.Redis configured from Flask config.

    Tests can monkeypatch `_client` with a fakeredis instance.
    """

    def __init__(self) -> None:
        self._client = None

    def init_app(self, app: Flask) -> None:
        import redis

        self._client = redis.Redis.from_url(app.config["REDIS_URL"], decode_responses=True)
        app.extensions["redis_client"] = self

    def set_client(self, client) -> None:
        self._client = client

    def __getattr__(self, name):
        if self._client is None:
            raise RuntimeError("redis_client not initialized; call init_app() first")
        return getattr(self._client, name)


redis_client = _RedisClientProxy()


login_manager.login_view = "admin.login"
login_manager.login_message = "Please sign in to access the admin area."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def _load_user(user_id: str):
    from app.models.user import AdminUser

    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    return db.session.get(AdminUser, uid)


def current_remote_ip() -> str:
    """Standard helper for code paths that need the trusted client IP."""
    return request.remote_addr or "unknown"
