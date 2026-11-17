"""Shared platform abstraction and HTTP helpers."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from app.config import Settings
from app.schemas import PlatformResult


@dataclass(frozen=True, slots=True)
class Post:
    """Validated content handed to every platform."""

    message: str
    cta_url: str


class PlatformError(Exception):
    """An expected, user-safe publishing failure."""


class PlatformNetworkError(PlatformError):
    """A connection-level failure: the provider never returned a response."""


class Platform(ABC):
    """Base class for one third-party integration.

    Subclasses implement ``_publish`` and can rely on credential checks and
    conversion of ``PlatformError`` (and HTTP failures) into failed results.
    """

    key: ClassVar[str]
    name: ClassVar[str]
    docs_url: ClassVar[str] = ""
    required_settings: ClassVar[tuple[str, ...]] = ()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------- readiness
    @property
    def configured(self) -> bool:
        return all(bool(getattr(self.settings, field, None)) for field in self.required_settings)

    @property
    def required_env(self) -> list[str]:
        return [field.upper() for field in self.required_settings]

    def credentials_error(self) -> str:
        return "Platform is not configured. Set: " + ", ".join(self.required_env)

    def _secrets(self) -> tuple[str, ...]:
        """Values that must never appear in an error message."""
        return ()

    # -------------------------------------------------------------- results
    def success(self, posted_url: str | None, public_access: bool) -> PlatformResult:
        now = datetime.now(UTC)
        return PlatformResult(
            platform=self.name,
            status="success",
            posted_url=posted_url,
            public_access=public_access,
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S"),
            error=None,
        )

    def failure(self, error: str) -> PlatformResult:
        cleaned = " ".join(str(error).split())[:500]
        return PlatformResult(
            platform=self.name,
            status="failed",
            posted_url=None,
            public_access=False,
            date=None,
            time=None,
            error=cleaned or "Unknown error",
        )

    # ------------------------------------------------------------ execution
    async def publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        if not self.configured:
            return self.failure(self.credentials_error())
        try:
            return await self._publish(client, post)
        except PlatformError as exc:
            return self.failure(str(exc))

    @abstractmethod
    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        """Perform the platform call and return a result."""

    # ------------------------------------------------------------ transport
    async def request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        params: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200, 201),
        secrets: tuple[str, ...] = (),
        expect_json: bool = True,
    ) -> tuple[Any, httpx.Response]:
        """Call an endpoint and return (parsed JSON or None, raw response).

        Set ``expect_json=False`` for endpoints that answer with a plain-text
        body (Slack webhooks reply ``ok``).

        The URL is deliberately never echoed in errors: several providers
        (Telegram, Discord) embed credentials in the request URL.
        """
        try:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise PlatformError(f"Request to {self.name} timed out") from exc
        except httpx.HTTPError as exc:
            # str(exc) may contain the request URL, so only the type is reported.
            raise PlatformNetworkError(f"Network error talking to {self.name} ({type(exc).__name__})") from exc

        if response.status_code not in expected:
            detail = _redact(_describe_error(response), (*self._secrets(), *secrets))
            raise PlatformError(f"{self.name} API returned HTTP {response.status_code}: {detail}")

        if not response.content or not expect_json:
            return None, response
        try:
            return response.json(), response
        except ValueError as exc:
            raise PlatformError(f"{self.name} API returned a non-JSON response (HTTP {response.status_code})") from exc


def _describe_error(response: httpx.Response) -> str:
    """Extract a useful, bounded message from an error response."""
    try:
        payload = response.json()
    except ValueError:
        text = (response.text or "").strip()
    else:
        text = _summarise_payload(payload)
    if not text:
        return f"HTTP {response.status_code} {response.reason_phrase}".strip()
    return text


def _summarise_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("detail", "message", "description", "title", "error", "errors"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list) and value:
                return json.dumps(value, ensure_ascii=False)
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False)


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    """Remove known secrets from text and cap it at 300 characters."""
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    text = " ".join(text.split())
    if len(text) > 300:
        return text[:300] + "..."
    return text
