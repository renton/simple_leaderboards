"""Game model — a leaderboard-bearing game registered by an admin."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base, utcnow_column

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")
SCORE_DIRECTIONS = ("desc", "asc")


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("score_direction in ('desc','asc')", name="ck_games_score_direction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    score_direction: Mapped[str] = mapped_column(String(4), nullable=False, default="desc")
    min_score: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    max_score: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    # JSONB column literally named "metadata". The Python attribute uses `meta`
    # because `metadata` is reserved by SQLAlchemy's declarative base.
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = utcnow_column()

    @validates("slug")
    def _validate_slug(self, _key, value: str) -> str:
        if not isinstance(value, str) or not SLUG_RE.match(value):
            raise ValueError(
                "slug must be lowercase alphanumeric with dashes, 2-64 chars"
            )
        return value

    @validates("timezone")
    def _validate_timezone(self, _key, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"invalid IANA timezone: {value!r}") from e
        return value

    @validates("score_direction")
    def _validate_score_direction(self, _key, value: str) -> str:
        if value not in SCORE_DIRECTIONS:
            raise ValueError(f"score_direction must be one of {SCORE_DIRECTIONS}")
        return value

    @validates("min_score", "max_score")
    def _bounds_consistent(self, key, value):
        # No-op individually; cross-field consistency is enforced in service code
        # because the second value might not yet be set during attribute assignment.
        return value

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Game id={self.id} slug={self.slug!r}>"
