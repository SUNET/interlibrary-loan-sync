from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EnqueueRequest(BaseModel):
    kwargs: dict[str, Any] = Field(default_factory=dict)
    queue: str | None = None


class RetryRequest(BaseModel):
    queue: str | None = None
    priority: int | None = None
    lock: str | None = None


class CancelRequest(BaseModel):
    abort: bool = False
