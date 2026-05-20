"""AdminUser model — accounts allowed to access the admin UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask_login import UserMixin
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow_column

_hasher = PasswordHasher()


class AdminUser(Base, UserMixin):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = utcnow_column()
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def set_password(self, password: str) -> None:
        self.password_hash = _hasher.hash(password)

    def check_password(self, password: str) -> bool:
        try:
            _hasher.verify(self.password_hash, password)
        except VerifyMismatchError:
            return False
        if _hasher.check_needs_rehash(self.password_hash):
            self.password_hash = _hasher.hash(password)
        return True

    def is_locked(self, now: datetime | None = None) -> bool:
        if self.locked_until is None:
            return False
        now = now or datetime.now(timezone.utc)
        return self.locked_until > now

    def register_failed_login(self, max_attempts: int, lockout_minutes: int) -> None:
        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)

    def register_successful_login(self) -> None:
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login_at = datetime.now(timezone.utc)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AdminUser id={self.id} username={self.username!r}>"
