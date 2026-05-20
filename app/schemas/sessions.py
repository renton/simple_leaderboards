"""Pydantic schemas for /api/v1/sessions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClientInfoIn(BaseModel):
    model_config = ConfigDict(extra="allow")  # filtered by services/device_info


class SessionRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game: str = Field(min_length=1, max_length=64)
    client_info: dict[str, Any] | None = None


class SessionResponse(BaseModel):
    session_token: str
    expires_at: str  # ISO8601 UTC
