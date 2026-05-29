"""Application factory for the leaderboards service."""

from __future__ import annotations

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config, load_config
from app.extensions import csrf, db, limiter, login_manager, migrate, redis_client


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config or load_config())

    if app.config["TRUSTED_PROXY_HOPS"]:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config["TRUSTED_PROXY_HOPS"],
            x_proto=app.config["TRUSTED_PROXY_HOPS"],
            x_host=app.config["TRUSTED_PROXY_HOPS"],
        )

    db.init_app(app)
    # Register all ORM models with the metadata so migrations can see them.
    from app import models  # noqa: F401

    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    redis_client.init_app(app)

    from app.cli import register_cli

    register_cli(app)

    from app.admin import admin_bp
    from app.api import api_bp

    csrf.exempt(api_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    from app.security_headers import install_security_headers

    install_security_headers(app)

    from app.api.errors import register_api_error_handlers

    register_api_error_handlers(app)

    @app.route("/healthz")
    def healthz() -> tuple[str, int]:
        return "ok", 200

    return app
