"""Local demo platform.

This is deliberately not a third-party service: it stores posts in memory and
serves them from /demo/posts/{id} so the full request/response flow, validation,
error handling and OpenAPI docs can be exercised without credentials. It is
useful for reviewers and for the screenshots/logs in the README.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.config import Settings
from app.platforms.base import Platform, Post
from app.schemas import DemoPost, PlatformResult

_MAX_POSTS = 200


class DemoPlatform(Platform):
    key = "demo"
    name = "Demo (local sandbox)"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._posts: dict[str, DemoPost] = {}

    @property
    def configured(self) -> bool:
        # The sandbox needs no credentials.
        return True

    def get(self, post_id: str) -> DemoPost | None:
        return self._posts.get(post_id)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        post_id = uuid4().hex[:16]
        base_url = self.settings.public_base_url.rstrip("/")
        url = f"{base_url}/demo/posts/{post_id}"
        self._posts[post_id] = DemoPost(
            id=post_id,
            message=post.message,
            cta_url=post.cta_url,
            created_at=datetime.now(UTC),
            url=url,
        )
        if len(self._posts) > _MAX_POSTS:
            self._posts.pop(next(iter(self._posts)))

        # Localhost URLs are not reachable from the internet, so they are not
        # reported as publicly accessible.
        host = (urlsplit(base_url).hostname or "").lower()
        public = bool(host) and host not in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
        return self.success(url, public_access=public)
