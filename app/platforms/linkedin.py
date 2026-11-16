"""LinkedIn Posts API integration."""

from __future__ import annotations

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult


class LinkedInPlatform(Platform):
    key = "linkedin"
    name = "LinkedIn"
    docs_url = "https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api"
    required_settings = ("linkedin_access_token", "linkedin_author_urn")

    def _secrets(self) -> tuple[str, ...]:
        return (self.settings.linkedin_access_token or "",)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        author = (self.settings.linkedin_author_urn or "").strip()
        if not author.startswith("urn:li:"):
            raise PlatformError("LINKEDIN_AUTHOR_URN must look like urn:li:person:<id> or urn:li:organization:<id>")

        payload = {
            "author": author,
            "commentary": post.message,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        _, response = await self.request_json(
            client,
            "POST",
            "https://api.linkedin.com/rest/posts",
            headers={
                "Authorization": f"Bearer {self.settings.linkedin_access_token}",
                "LinkedIn-Version": self.settings.linkedin_api_version,
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json_body=payload,
            secrets=self._secrets(),
        )

        # The Posts API returns the post URN in a header and an empty body.
        post_urn = response.headers.get("x-restli-id")
        posted_url = f"https://www.linkedin.com/feed/update/{post_urn}" if post_urn else None
        return self.success(posted_url, public_access=True)
