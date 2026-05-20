"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. Refusing to start."
        )
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass
class Config:
    SECRET_KEY: str
    SQLALCHEMY_DATABASE_URI: str
    SQLALCHEMY_ENGINE_OPTIONS: dict = field(default_factory=lambda: {"pool_pre_ping": True})
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_RATELIMIT_URL: str = "redis://redis:6379/1"
    RATELIMIT_STORAGE_URI: str = "redis://redis:6379/1"
    RATELIMIT_HEADERS_ENABLED: bool = True

    SESSION_TTL_SECONDS: int = 3600
    CACHE_TTL_SECONDS: int = 300
    MAX_PLAYED_AT_SKEW_SECONDS: int = 60

    MAX_CONTENT_LENGTH: int = 4096

    TRUSTED_PROXY_HOPS: int = 1

    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Strict"
    SESSION_COOKIE_SECURE: bool = True
    PERMANENT_SESSION_LIFETIME: int = 60 * 30  # 30 min idle

    WTF_CSRF_TIME_LIMIT: int | None = None  # rely on session lifetime

    # Public-API rate limits
    RATELIMIT_SESSIONS: str = "10/minute;100/hour"
    RATELIMIT_SCORES: str = "30/minute;300/hour"
    RATELIMIT_LEADERBOARDS: str = "60/minute"
    RATELIMIT_ADMIN_LOGIN: str = "5/minute;20/hour"

    # Admin lockout
    ADMIN_MAX_FAILED_LOGINS: int = 10
    ADMIN_LOCKOUT_MINUTES: int = 15


def load_config() -> Config:
    db_uri = os.environ.get("DATABASE_URL") or _build_db_uri()
    ratelimit_uri = os.environ.get(
        "RATELIMIT_STORAGE_URI",
        os.environ.get("REDIS_RATELIMIT_URL", "redis://redis:6379/1"),
    )
    return Config(
        SECRET_KEY=_required("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=db_uri,
        REDIS_URL=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        REDIS_RATELIMIT_URL=os.environ.get("REDIS_RATELIMIT_URL", "redis://redis:6379/1"),
        RATELIMIT_STORAGE_URI=ratelimit_uri,
        SESSION_TTL_SECONDS=_int("SESSION_TTL_SECONDS", 3600),
        CACHE_TTL_SECONDS=_int("CACHE_TTL_SECONDS", 300),
        MAX_PLAYED_AT_SKEW_SECONDS=_int("MAX_PLAYED_AT_SKEW_SECONDS", 60),
        TRUSTED_PROXY_HOPS=_int("TRUSTED_PROXY_HOPS", 1),
        SESSION_COOKIE_SECURE=_bool("SESSION_COOKIE_SECURE", True),
    )


def _build_db_uri() -> str:
    user = os.environ.get("POSTGRES_USER", "leaderboards")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "db")
    port = os.environ.get("POSTGRES_PORT", "5432")
    name = os.environ.get("POSTGRES_DB", "leaderboards")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


class TestConfig(Config):
    """Convenience subclass tests can construct with overrides."""

    def __init__(self, **overrides) -> None:
        defaults = dict(
            SECRET_KEY="test-secret-do-not-use",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            REDIS_URL="redis://localhost:6379/15",
            REDIS_RATELIMIT_URL="memory://",
            RATELIMIT_STORAGE_URI="memory://",
            SESSION_COOKIE_SECURE=False,
            TRUSTED_PROXY_HOPS=0,
            WTF_CSRF_ENABLED=False,
        )
        defaults.update(overrides)
        super().__init__(**defaults)
