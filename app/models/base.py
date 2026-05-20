"""Shared SQLAlchemy declarative base + common column helpers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


def utcnow_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# Re-export the Flask-SQLAlchemy declarative base for model modules.
Base = db.Model
