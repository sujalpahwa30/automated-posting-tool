"""Mastodon REST API integration (works with any Mastodon-compatible server)."""

from __future__ import annotations

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult


class MastodonPlatform(Platform):
    key = "mastodon"
    name = "Mastodon"
    docs_url = "https://docs.joinmastodon.org/methods/statuses/#create"
    required_settings = ("mastodon_instance_url", "mastodon_access_token")

    def _secrets(self) -> tuple[str, ...]:
        return (self.settings.mastodon_access_token or "",)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        instance = (self.settings.mastodon_instance_url or "").strip().rstrip("/")
        if not instance.startswith(("http://", "https://")):
            instance = "https://" + instance
        if "." not in instance:
            raise PlatformError("MASTODON_INSTANCE_URL must be a hostname such as https://mastodon.social")

        document, _ = await self.request_json(
            client,
            "POST",
            f"{instance}/api/v1/statuses",
            headers={"Authorization": f"Bearer {self.settings.mastodon_access_token}"},
            json_body={"status": post.message, "visibility": "public"},
            secrets=self._secrets(),
        )

        document = document or {}
        posted_url = document.get("url") or document.get("uri")
        visibility = document.get("visibility", "public")
        return self.success(posted_url, public_access=visibility in {"public", "unlisted"})
