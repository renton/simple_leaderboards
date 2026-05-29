"""Pydantic schema for /api/v1/champions query params."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChampionsQueryIn(BaseModel):
    """Query parameters for GET /api/v1/champions.

    Unknown query parameters are rejected to keep the cache keyspace bounded.
    """

    model_config = ConfigDict(extra="forbid")

    game: str = Field(min_length=1, max_length=64)
    since: datetime | None = None
    until: datetime | None = None
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=25, ge=1, le=50)

    @field_validator("since", "until")
    @classmethod
    def _assume_utc_if_naive(cls, value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value

        return value.replace(tzinfo=UTC)

    @model_validator(mode="after")
    def _check_window_order(self) -> ChampionsQueryIn:
        if self.since is not None and self.until is not None and self.since >= self.until:
            raise ValueError("since must be earlier than until")
        return self
