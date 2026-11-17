"""Tumblr (v2 API) text post integration."""

from __future__ import annotations

import httpx

from app.platforms.base import Platform, PlatformError, Post
from app.schemas import PlatformResult


class TumblrPlatform(Platform):
    key = "tumblr"
    name = "Tumblr"
    docs_url = "https://www.tumblr.com/docs/en/api/v2#posts"
    required_settings = ("tumblr_access_token", "tumblr_blog_identifier")

    def _secrets(self) -> tuple[str, ...]:
        return (self.settings.tumblr_access_token or "",)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        blog = normalise_blog(self.settings.tumblr_blog_identifier or "")

        # Neo-format posts: a single text block, published immediately.
        document, _ = await self.request_json(
            client,
            "POST",
            f"https://api.tumblr.com/v2/blog/{blog}/post",
            headers={"Authorization": f"Bearer {self.settings.tumblr_access_token or ''}"},
            json_body={
                "content": [{"type": "text", "text": post.message}],
                "state": "published",
            },
            secrets=self._secrets(),
        )

        response = (document or {}).get("response") or {}
        post_id = response.get("id_string") or response.get("id")
        if not post_id:
            raise PlatformError("Tumblr did not return the created post id")
        return self.success(f"https://{blog}/post/{post_id}", public_access=True)


def normalise_blog(value: str) -> str:
    """Turn a blog identifier into the host used by the public post URL."""
    blog = value.strip()
    for prefix in ("https://", "http://"):
        if blog.startswith(prefix):
            blog = blog[len(prefix) :]
    blog = blog.rstrip("/")
    if not blog:
        raise PlatformError("TUMBLR_BLOG_IDENTIFIER must be a blog such as myblog.tumblr.com")
    if "." not in blog:
        return f"{blog}.tumblr.com"
    return blog
