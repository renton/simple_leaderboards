"""Pydantic schemas for /api/v1/scores."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScoreSubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game: str = Field(min_length=1, max_length=64)
    player_name: str = Field(min_length=1, max_length=256)  # final length after norm in sanity
    score: Decimal
    played_at: datetime | None = None
    seed: str | None = Field(default=None, max_length=64)
    custom_data: dict[str, Any] | None = None
    client_info: dict[str, Any] | None = None


class ScoreSubmitResponse(BaseModel):
    id: int
