"""Tumblr (v2 API) text post integration."""

from __future__ import annotations

import html
import ssl
from functools import lru_cache

import httpx

from app.platforms.base import Platform, PlatformError, PlatformNetworkError, Post
from app.schemas import PlatformResult


class TumblrPlatform(Platform):
    key = "tumblr"
    name = "Tumblr"
    docs_url = "https://www.tumblr.com/docs/en/api/v2#posts"
    required_settings = ("tumblr_access_token", "tumblr_blog_identifier")

    def _secrets(self) -> tuple[str, ...]:
        return (self.settings.tumblr_access_token or "",)

    async def _publish(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        try:
            return await self._post_once(client, post)
        except PlatformNetworkError:
            # Some networks (antivirus proxies, ISP middleboxes) reset httpx's
            # default TLS 1.2/1.3 negotiation against Tumblr's edge, even though
            # either version works on its own. A connection-level failure means
            # no request was processed, so one retry over TLS 1.2 is safe.
            async with self._fallback_client() as fallback:
                return await self._post_once(fallback, post)

    def _fallback_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.settings.platform_timeout_seconds,
            verify=build_tls_context(),
        )

    async def _post_once(self, client: httpx.AsyncClient, post: Post) -> PlatformResult:
        blog = normalise_blog(self.settings.tumblr_blog_identifier or "")

        # Legacy text posts: Tumblr rejects a neo-format "content" array with
        # code 8001 ("Post cannot be empty"), but accepts type=text + body.
        document, _ = await self.request_json(
            client,
            "POST",
            f"https://api.tumblr.com/v2/blog/{blog}/post",
            headers={"Authorization": f"Bearer {self.settings.tumblr_access_token or ''}"},
            json_body={"type": "text", "body": render_body(post)},
            secrets=self._secrets(),
        )

        response = (document or {}).get("response") or {}
        post_id = response.get("id_string") or response.get("id")
        if not post_id:
            raise PlatformError("Tumblr did not return the created post id")
        return self.success(f"https://{blog}/post/{post_id}", public_access=True)


@lru_cache(maxsize=1)
def build_tls_context() -> ssl.SSLContext:
    """A TLS 1.2-only context used for Tumblr requests.

    Pinning the version keeps the handshake predictable on networks that reset
    the default 1.2/1.3 negotiation. TLS 1.2 with modern ciphers is still
    required by every current provider, so nothing is weakened in practice.
    """
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    return context


def render_body(post: Post) -> str:
    """Render the message as a legacy text-post body.

    Tumblr treats ``body`` as HTML, so the text is escaped and the single CTA
    URL becomes a real link.
    """
    safe_url = html.escape(post.cta_url, quote=False)
    anchor = f'<a href="{html.escape(post.cta_url, quote=True)}">{safe_url}</a>'
    return html.escape(post.message, quote=False).replace(safe_url, anchor, 1)


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
