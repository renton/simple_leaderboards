"""AdminAction — audit log of state-changing admin actions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow_column


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = utcnow_column()

    admin_user = relationship("AdminUser")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AdminAction id={self.id} action={self.action!r}>"
