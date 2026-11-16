"""Slack incoming-webhook integration."""

from __future__ import annotations

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult


class SlackPlatform(Platform):
    key = "slack"
    name = "Slack"
    docs_url = "https://api.slack.com/messaging/webhooks"
    required_settings = ("slack_webhook_url",)

    def _secrets(self) -> tuple[str, ...]:
        # The webhook URL itself is a credential (it can post to the channel),
        # so neither the full URL nor its token may leak into an error message.
        webhook_url = (self.settings.slack_webhook_url or "").rstrip("/")
        token = webhook_url.rsplit("/", 1)[-1] if webhook_url else ""
        return (webhook_url, token)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        # A webhook answers with the plain-text body "ok" on success.
        _, response = await self.request_json(
            client,
            "POST",
            self.settings.slack_webhook_url or "",
            json_body={
                "text": post.message,
                # Do not turn every link in the CTA into a preview card.
                "unfurl_links": False,
                "unfurl_media": False,
            },
            secrets=self._secrets(),
            expect_json=False,
        )

        body = (response.text or "").strip()
        if body != "ok":
            detail = " ".join(body.split())[:200] or "empty response body"
            raise PlatformError(f"Slack webhook rejected the message: {detail}")

        # Incoming webhooks never expose a permalink for the message, so there
        # is no public URL to report. The message is still delivered.
        return self.success(None, public_access=False)
