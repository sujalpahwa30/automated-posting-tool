"""X (Twitter) API v2 integration."""

from __future__ import annotations

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult


class XPlatform(Platform):
    key = "x"
    name = "X (Twitter)"
    docs_url = "https://docs.x.com/x-api/posts/create-post"
    required_settings = ("x_api_bearer_token",)

    def _secrets(self) -> tuple[str, ...]:
        return (self.settings.x_api_bearer_token or "",)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        document, _ = await self.request_json(
            client,
            "POST",
            "https://api.x.com/2/tweets",
            headers={"Authorization": f"Bearer {self.settings.x_api_bearer_token}"},
            json_body={"text": post.message},
            secrets=self._secrets(),
        )
        post_id = ((document or {}).get("data") or {}).get("id")
        if not post_id:
            raise PlatformError("X API did not return a post id")
        return self.success(f"https://x.com/i/web/status/{post_id}", public_access=True)
