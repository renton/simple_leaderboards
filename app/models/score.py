"""Score model — a single player-submitted leaderboard entry."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow_column
from app.models.game import Game


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        Index("ix_scores_game_submitted", "game_id", "submitted_at"),
        Index("ix_scores_game_score", "game_id", "score"),
        Index("ix_scores_game_seed_score", "game_id", "seed", "score"),
        Index("ix_scores_game_deleted", "game_id", "deleted_at"),
        Index("ix_scores_player_name", "player_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_name: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    submitted_at: Mapped[datetime] = utcnow_column()
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_info: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    custom_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    game: Mapped[Game] = relationship("Game", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Score id={self.id} game_id={self.game_id} score={self.score}>"
