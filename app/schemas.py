"""Pydantic request/response models for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.validation import extract_cta_url, validate_message


class PostingRequest(BaseModel):
    """Payload accepted by POST /posting."""

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "examples": [
                {
                    "message": (
                        "Check out our latest business platform and grow your online visibility. https://example.com"
                    )
                }
            ]
        },
    )

    message: str = Field(
        ...,
        description=("Post text of at most 200 characters containing exactly one http(s) call-to-action link."),
    )

    @field_validator("message", mode="before")
    @classmethod
    def _validate_message(cls, value: object) -> str:
        return validate_message(value)

    @property
    def cta_url(self) -> str:
        """The validated CTA link (already guaranteed to exist)."""
        return extract_cta_url(self.message)


class PlatformResult(BaseModel):
    """Outcome of publishing to one platform."""

    platform: str
    status: Literal["success", "failed"]
    posted_url: str | None = None
    public_access: bool = False
    date: str | None = None
    time: str | None = None
    error: str | None = None


class PostingSummary(BaseModel):
    total: int
    successful: int
    failed: int


class PostingResponse(BaseModel):
    """Aggregated result returned by POST /posting."""

    success: bool = Field(description="True when at least one platform published the message.")
    summary: PostingSummary
    results: list[PlatformResult]


class PlatformInfo(BaseModel):
    """Readiness information exposed by GET /platforms."""

    key: str
    name: str
    enabled: bool
    configured: bool
    required_env: list[str]
    docs_url: str | None = None


class PlatformListResponse(BaseModel):
    platforms: list[PlatformInfo]


class DemoPost(BaseModel):
    """A post stored by the local demo platform (for offline review)."""

    id: str
    message: str
    cta_url: str
    created_at: datetime
    url: str
