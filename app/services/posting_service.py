"""Fan-out posting service.

Every platform runs concurrently and independently: a failure (including a
timeout or an unexpected exception) is converted into a failed result and never
stops the remaining platforms.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from time import perf_counter

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult, PostingResponse, PostingSummary

logger = logging.getLogger("automated_posting.service")


class PostingService:
    def __init__(
        self,
        platforms: Sequence[Platform],
        client: httpx.AsyncClient | None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._platforms = list(platforms)
        self._client = client
        self._timeout = timeout_seconds

    @property
    def platforms(self) -> list[Platform]:
        return list(self._platforms)

    async def publish(self, post: Post) -> PostingResponse:
        if not self._platforms:
            logger.warning("No posting platforms are enabled. Configure credentials in .env or set PLATFORMS=demo.")
            return PostingResponse(
                success=False,
                summary=PostingSummary(total=0, successful=0, failed=0),
                results=[],
            )

        started = perf_counter()
        results = await asyncio.gather(*(self._publish_one(platform, post) for platform in self._platforms))
        successful = sum(1 for result in results if result.status == "success")
        logger.info(
            "posting finished platforms=%d successful=%d failed=%d duration_ms=%.0f",
            len(results),
            successful,
            len(results) - successful,
            (perf_counter() - started) * 1000,
        )
        return PostingResponse(
            success=successful > 0,
            summary=PostingSummary(
                total=len(results),
                successful=successful,
                failed=len(results) - successful,
            ),
            results=list(results),
        )

    async def _publish_one(self, platform: Platform, post: Post) -> PlatformResult:
        started = perf_counter()
        try:
            # wait_for is a second safety net in case an integration blocks
            # without honouring the HTTP client timeout.
            result = await asyncio.wait_for(
                platform.publish(self._client, post),  # type: ignore[arg-type]
                timeout=self._timeout,
            )
        except TimeoutError:
            result = platform.failure(f"Timed out after {self._timeout:g}s")
        except PlatformError as exc:
            result = platform.failure(str(exc))
        except Exception:
            # Never leak stack traces or credentials to API clients.
            logger.exception("Unexpected error while publishing platform=%s", platform.key)
            result = platform.failure("Unexpected internal error while publishing (see server logs)")

        logger.info(
            "platform publish key=%s status=%s duration_ms=%.0f url=%s error=%s",
            platform.key,
            result.status,
            (perf_counter() - started) * 1000,
            result.posted_url,
            result.error,
        )
        return result
