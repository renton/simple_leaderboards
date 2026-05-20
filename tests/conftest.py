"""Shared test fixtures.

Most fixtures spin up a Flask app pointed at a separate `leaderboards_test`
Postgres database on the docker-compose stack, and a `fakeredis` Redis. Tables
are created once per session and truncated between tests for isolation.

Tests that only exercise pure logic (time ranges, sanity checks, name
normalization, session tokens, cache) don't depend on these fixtures and
run with no DB.
"""

from __future__ import annotations

import os

import fakeredis
import pytest

# Test-time env *must* be set before app.create_app is imported because
# create_app reads SECRET_KEY at import. We set safe defaults here.
os.environ.setdefault("SECRET_KEY", "test-secret-do-not-use-in-prod-32bytesxx")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://leaderboards:"
    + os.environ.get("POSTGRES_PASSWORD", "test-postgres-password")
    + "@127.0.0.1:5432/leaderboards_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("REDIS_RATELIMIT_URL", "memory://")
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")
os.environ.setdefault("TRUSTED_PROXY_HOPS", "0")


@pytest.fixture(scope="session")
def app():
    from app import create_app
    from app.config import load_config

    cfg = load_config()
    # Disable CSRF on the WTForms admin so tests can POST forms easily.
    cfg.__dict__["WTF_CSRF_ENABLED"] = False  # type: ignore[attr-defined]
    cfg.__dict__["RATELIMIT_ENABLED"] = False  # type: ignore[attr-defined]
    flask_app = create_app(cfg)

    with flask_app.app_context():
        from app.extensions import db

        db.drop_all()
        db.create_all()

    yield flask_app

    with flask_app.app_context():
        from app.extensions import db

        db.drop_all()


@pytest.fixture(autouse=True)
def _truncate_tables(app):
    """Truncate all tables before each test for hermetic isolation."""
    from sqlalchemy import text

    with app.app_context():
        from app.extensions import db

        # Postgres requires that we identify the tables in dependency order
        # OR use a single TRUNCATE ... CASCADE statement.
        tables = ",".join(
            f'"{t.name}"' for t in reversed(db.metadata.sorted_tables)
        )
        db.session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE;"))
        db.session.commit()
    yield


@pytest.fixture
def db_session(app):
    with app.app_context():
        from app.extensions import db

        yield db.session


@pytest.fixture
def fake_redis(app):
    """Replace the Flask app's redis client with a fakeredis instance for the test."""
    from app.extensions import redis_client

    fake = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set_client(fake)
    yield fake


@pytest.fixture
def client(app, fake_redis):
    return app.test_client()


@pytest.fixture
def make_game(app):
    """Factory for inserting a Game row."""

    def _factory(**overrides):
        from app.extensions import db
        from app.models.game import Game

        defaults = dict(
            slug="tetris-classic",
            name="Tetris Classic",
            timezone="UTC",
            score_direction="desc",
            min_score=0,
            max_score=10**9,
            meta={},
            archived=False,
        )
        defaults.update(overrides)
        with app.app_context():
            game = Game(**defaults)
            db.session.add(game)
            db.session.commit()
            db.session.refresh(game)
            # Detach so the caller can use it without keeping the session alive.
            db.session.expunge(game)
            return game

    return _factory


@pytest.fixture
def make_score(app):
    """Factory for inserting a Score row."""

    def _factory(*, game, player_name, score, **overrides):
        from app.extensions import db
        from app.models.score import Score

        defaults = dict(
            game_id=game.id,
            player_name=player_name,
            score=score,
            seed=None,
            played_at=None,
            device_info={},
            custom_data={},
            deleted_at=None,
        )
        defaults.update(overrides)
        with app.app_context():
            row = Score(**defaults)
            db.session.add(row)
            db.session.commit()
            db.session.refresh(row)
            db.session.expunge(row)
            return row

    return _factory
