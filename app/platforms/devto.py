"""Dev.to (Forem) articles API integration."""

from __future__ import annotations

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult

_MAX_TITLE_LENGTH = 70


class DevToPlatform(Platform):
    key = "devto"
    name = "Dev.to"
    docs_url = "https://developers.forem.com/api/v1#tag/articles/operation/createArticle"
    required_settings = ("devto_api_key",)

    def _secrets(self) -> tuple[str, ...]:
        return (self.settings.devto_api_key or "",)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        document, _ = await self.request_json(
            client,
            "POST",
            "https://dev.to/api/articles",
            headers={
                "api-key": self.settings.devto_api_key or "",
                "accept": "application/vnd.forem.api-v1+json",
            },
            json_body={
                "article": {
                    "title": _build_title(post),
                    "published": True,
                    "body_markdown": post.message,
                }
            },
            secrets=self._secrets(),
        )

        posted_url = (document or {}).get("url")
        if not posted_url:
            raise PlatformError("Dev.to API did not return an article URL")
        return self.success(posted_url, public_access=True)


def _build_title(post: Post) -> str:
    """Derive a short article title from the message (URL removed)."""
    text = post.message.replace(post.cta_url, " ")
    text = " ".join(text.split()).strip(" -:;,.|")
    if not text:
        return "New update"
    if len(text) <= _MAX_TITLE_LENGTH:
        return text
    shortened = text[:_MAX_TITLE_LENGTH].rsplit(" ", 1)[0].rstrip(" -:;,.|")
    return shortened or text[:_MAX_TITLE_LENGTH]
