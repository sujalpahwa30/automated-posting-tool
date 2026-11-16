"""Discord incoming-webhook integration."""

from __future__ import annotations

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult


class DiscordPlatform(Platform):
    key = "discord"
    name = "Discord"
    docs_url = "https://discord.com/developers/docs/resources/webhook#execute-webhook"
    required_settings = ("discord_webhook_url",)

    def _secrets(self) -> tuple[str, ...]:
        webhook_url = (self.settings.discord_webhook_url or "").rstrip("/")
        token = webhook_url.rsplit("/", 1)[-1] if webhook_url else ""
        return (webhook_url, token)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        # wait=true makes Discord return the created message object.
        document, _ = await self.request_json(
            client,
            "POST",
            self.settings.discord_webhook_url or "",
            params={"wait": "true"},
            json_body={
                "content": post.message,
                # A public post should not ping @everyone or roles.
                "allowed_mentions": {"parse": []},
            },
            secrets=self._secrets(),
        )

        message = document or {}
        message_id = message.get("id")
        channel_id = message.get("channel_id")
        guild_id = message.get("guild_id")
        if not message_id or not channel_id:
            raise PlatformError("Discord did not return the created message id")

        # Without a guild id (e.g. group DM webhook) there is no public URL.
        if guild_id:
            posted_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
            return self.success(posted_url, public_access=True)
        return self.success(None, public_access=False)
