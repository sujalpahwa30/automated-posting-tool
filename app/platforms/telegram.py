"""Telegram Bot API integration."""

from __future__ import annotations

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult


class TelegramPlatform(Platform):
    key = "telegram"
    name = "Telegram"
    docs_url = "https://core.telegram.org/bots/api#sendmessage"
    required_settings = ("telegram_bot_token", "telegram_chat_id")

    def _secrets(self) -> tuple[str, ...]:
        return (self.settings.telegram_bot_token or "",)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        # The bot token is part of the URL, so never log or echo this URL.
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        document, _ = await self.request_json(
            client,
            "POST",
            url,
            json_body={
                "chat_id": self.settings.telegram_chat_id,
                "text": post.message,
            },
            secrets=self._secrets(),
        )

        result = (document or {}).get("result") or {}
        message_id = result.get("message_id")
        username = (result.get("chat") or {}).get("username")
        if message_id is None:
            raise PlatformError("Telegram API did not return a message id")

        # Only channels with a public username have a shareable t.me URL.
        posted_url = f"https://t.me/{username}/{message_id}" if username else None
        return self.success(posted_url, public_access=bool(username))
