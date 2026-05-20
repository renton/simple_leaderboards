"""Pydantic schemas for /api/v1/leaderboards (query params)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.leaderboard_query import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.services.time_ranges import VALID_RANGES


class LeaderboardQueryIn(BaseModel):
    """Query parameters for GET /api/v1/leaderboards.

    Querystring fields are coerced to these types in the route handler;
    `extra="forbid"` rejects unknown parameters to keep the cache keyspace
    bounded.
    """

    model_config = ConfigDict(extra="forbid")

    game: str = Field(min_length=1, max_length=64)
    range: Literal["all-time", "yearly", "monthly", "weekly", "daily", "hourly"] = "all-time"
    seed: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=32)
    sort: Literal["score", "submitted_at", "played_at"] = "score"
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


# Re-export for callers that introspect the set.
__all__ = ["LeaderboardQueryIn", "VALID_RANGES"]
