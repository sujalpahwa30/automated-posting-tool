"""Bluesky (AT Protocol) integration.

Posting is a two-step flow: create a session (access JWT) and then create the
post record through the PDS.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult


class BlueskyPlatform(Platform):
    key = "bluesky"
    name = "Bluesky"
    docs_url = "https://docs.bsky.app/docs/tutorials/creating-a-post"
    required_settings = ("bluesky_identifier", "bluesky_app_password")

    def _secrets(self) -> tuple[str, ...]:
        return (
            self.settings.bluesky_app_password or "",
            self.settings.bluesky_identifier or "",
        )

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        base_url = self.settings.bluesky_service_url.rstrip("/") + "/xrpc"

        session, _ = await self.request_json(
            client,
            "POST",
            f"{base_url}/com.atproto.server.createSession",
            json_body={
                "identifier": self.settings.bluesky_identifier,
                "password": self.settings.bluesky_app_password,
            },
            secrets=self._secrets(),
        )
        access_jwt = (session or {}).get("accessJwt")
        did = (session or {}).get("did")
        if not access_jwt or not did:
            raise PlatformError("Bluesky login did not return an access token")
        handle = (session or {}).get("handle") or did

        created_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        document, _ = await self.request_json(
            client,
            "POST",
            f"{base_url}/com.atproto.repo.createPost",
            headers={"Authorization": f"Bearer {access_jwt}"},
            json_body={
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": {
                    "$type": "app.bsky.feed.post",
                    "text": post.message,
                    "createdAt": created_at,
                },
            },
            secrets=(*self._secrets(), access_jwt),
        )

        uri = (document or {}).get("uri")
        if not uri:
            raise PlatformError("Bluesky API did not return a post URI")
        rkey = uri.rsplit("/", 1)[-1]
        return self.success(
            f"https://bsky.app/profile/{handle}/post/{rkey}",
            public_access=True,
        )
