"""Unit tests for each platform adapter using a mocked HTTP transport."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.platforms.base import Platform, Post
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.demo import DemoPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.linkedin import LinkedInPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.slack import SlackPlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.tumblr import TumblrPlatform
from app.platforms.x import XPlatform

MESSAGE = "Check out our latest business platform and grow your online visibility. https://example.com"


def _post() -> Post:
    return Post(message=MESSAGE, cta_url="https://example.com")


async def _publish(platform: Platform, handler) -> object:  # type: ignore[no-untyped-def]
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        return await platform.publish(client, _post())


def test_x_success(make_settings) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "1760000000000000000"}})

    platform = XPlatform(make_settings(x_api_bearer_token="x-token"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url == "https://x.com/i/web/status/1760000000000000000"
    assert result.public_access is True
    assert result.error is None
    assert result.date and result.time
    assert captured["url"] == "https://api.x.com/2/tweets"
    assert captured["authorization"] == "Bearer x-token"
    assert captured["body"] == {"text": MESSAGE}


def test_x_api_error_is_reported(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"title": "Unauthorized", "detail": "Unauthorized", "status": 401},
        )

    platform = XPlatform(make_settings(x_api_bearer_token="x-token"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "failed"
    assert result.posted_url is None
    assert result.date is None
    assert "HTTP 401" in result.error
    assert "Unauthorized" in result.error


def test_linkedin_posts_and_reads_urn_header(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.linkedin.com/rest/posts"
        assert request.headers["linkedin-version"] == "202601"
        assert request.headers["x-restli-protocol-version"] == "2.0.0"
        body = json.loads(request.content)
        assert body["author"] == "urn:li:person:abc123"
        assert body["visibility"] == "PUBLIC"
        assert body["commentary"] == MESSAGE
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:99"})

    platform = LinkedInPlatform(
        make_settings(
            linkedin_access_token="li-token",
            linkedin_author_urn="urn:li:person:abc123",
        )
    )
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url == "https://www.linkedin.com/feed/update/urn:li:share:99"
    assert result.public_access is True


def test_linkedin_rejects_malformed_author_urn(make_settings) -> None:
    platform = LinkedInPlatform(
        make_settings(
            linkedin_access_token="li-token",
            linkedin_author_urn="person:abc123",
        )
    )
    result = asyncio.run(_publish(platform, lambda request: pytest.fail("must not call the API")))

    assert result.status == "failed"
    assert "urn:li:" in result.error


def test_telegram_public_channel(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bot123:abc/sendMessage"
        body = json.loads(request.content)
        assert body == {"chat_id": "@demo_channel", "text": MESSAGE}
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 7,
                    "chat": {"id": -100, "username": "demo_channel"},
                },
            },
        )

    platform = TelegramPlatform(make_settings(telegram_bot_token="123:abc", telegram_chat_id="@demo_channel"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url == "https://t.me/demo_channel/7"
    assert result.public_access is True


def test_telegram_private_chat_has_no_public_url(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 7, "chat": {"id": 42}}},
        )

    platform = TelegramPlatform(make_settings(telegram_bot_token="123:abc", telegram_chat_id="42"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url is None
    assert result.public_access is False


def test_telegram_error_redacts_bot_token(make_settings) -> None:
    token = "123456:secret-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "ok": False,
                "error_code": 401,
                "description": f"Unauthorized: {token}",
            },
        )

    platform = TelegramPlatform(make_settings(telegram_bot_token=token, telegram_chat_id="@demo"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "failed"
    assert "***" in result.error
    assert token not in result.error


def test_discord_webhook_returns_message_url(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["wait"] == "true"
        body = json.loads(request.content)
        assert body["content"] == MESSAGE
        assert body["allowed_mentions"] == {"parse": []}
        return httpx.Response(
            200,
            json={"id": "10", "channel_id": "20", "guild_id": "30"},
        )

    platform = DiscordPlatform(make_settings(discord_webhook_url="https://discord.com/api/webhooks/1/webhook-token"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url == "https://discord.com/channels/30/20/10"
    assert result.public_access is True


def test_discord_without_guild_is_not_public(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "10", "channel_id": "20"})

    platform = DiscordPlatform(make_settings(discord_webhook_url="https://discord.com/api/webhooks/1/webhook-token"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url is None
    assert result.public_access is False


def test_discord_falls_back_to_webhook_details_for_guild(make_settings) -> None:
    """Live Discord omits guild_id from the execute-webhook response."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"id": "1", "guild_id": "30", "channel_id": "20"})
        return httpx.Response(200, json={"id": "10", "channel_id": "20"})

    platform = DiscordPlatform(make_settings(discord_webhook_url="https://discord.com/api/webhooks/1/webhook-token"))

    first = asyncio.run(_publish(platform, handler))
    second = asyncio.run(_publish(platform, handler))

    assert first.posted_url == "https://discord.com/channels/30/20/10"
    assert second.posted_url == "https://discord.com/channels/30/20/10"
    assert first.public_access is True
    # The guild id is cached, so only one extra lookup happens.
    assert calls.count("GET") == 1


def test_slack_webhook_delivers_message(make_settings) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="ok")

    platform = SlackPlatform(make_settings(slack_webhook_url="https://hooks.slack.com/services/T0/B0/webhook-token"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.error is None
    assert result.date and result.time
    assert captured["url"] == "https://hooks.slack.com/services/T0/B0/webhook-token"
    assert captured["body"] == {"text": MESSAGE, "unfurl_links": False, "unfurl_media": False}
    # Incoming webhooks expose no permalink for the delivered message.
    assert result.posted_url is None
    assert result.public_access is False


def test_slack_webhook_rejection_is_reported(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="invalid_payload")

    platform = SlackPlatform(make_settings(slack_webhook_url="https://hooks.slack.com/services/T0/B0/webhook-token"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "failed"
    assert "invalid_payload" in result.error
    # The webhook token must never appear in the error message.
    assert "webhook-token" not in result.error


def test_slack_without_webhook_is_not_configured(make_settings) -> None:
    platform = SlackPlatform(make_settings())
    result = asyncio.run(_publish(platform, lambda request: httpx.Response(200, text="ok")))

    assert result.status == "failed"
    assert "SLACK_WEBHOOK_URL" in result.error


def test_tumblr_publishes_text_post(make_settings) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "meta": {"status": 201, "msg": "Created"},
                "response": {"id": 123456789, "id_string": "123456789", "state": "published"},
            },
        )

    platform = TumblrPlatform(
        make_settings(
            tumblr_access_token="tumblr-token",
            tumblr_blog_identifier="demo-blog.tumblr.com",
        )
    )
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url == "https://demo-blog.tumblr.com/post/123456789"
    assert result.public_access is True
    assert captured["url"] == "https://api.tumblr.com/v2/blog/demo-blog.tumblr.com/post"
    assert captured["authorization"] == "Bearer tumblr-token"
    assert captured["body"]["content"] == [{"type": "text", "text": MESSAGE}]
    assert captured["body"]["state"] == "published"


def test_tumblr_retries_after_connection_reset(make_settings, monkeypatch) -> None:
    """A reset before any response is retried over a pinned-TLS client."""

    def reset_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("Server disconnected without sending a response")

    def good_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"response": {"id": "9"}})

    platform = TumblrPlatform(
        make_settings(tumblr_access_token="tumblr-token", tumblr_blog_identifier="demo-blog.tumblr.com")
    )

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(good_handler))

    monkeypatch.setattr(platform, "_fallback_client", factory)
    result = asyncio.run(_publish(platform, reset_handler))

    assert result.status == "success"
    assert result.posted_url == "https://demo-blog.tumblr.com/post/9"


def test_tumblr_api_error_is_not_retried(make_settings, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"meta": {"status": 401, "msg": "Unauthorized"}, "response": []})

    platform = TumblrPlatform(
        make_settings(tumblr_access_token="tumblr-token", tumblr_blog_identifier="demo-blog.tumblr.com")
    )

    def factory() -> httpx.AsyncClient:  # pragma: no cover - must not be used
        raise AssertionError("an HTTP error must not trigger a retry")

    monkeypatch.setattr(platform, "_fallback_client", factory)
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "failed"
    assert "HTTP 401" in result.error


def test_tumblr_blog_name_gets_tumblr_suffix(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/blog/demo-blog.tumblr.com/post"
        return httpx.Response(201, json={"response": {"id": 42}})

    platform = TumblrPlatform(
        make_settings(tumblr_access_token="tumblr-token", tumblr_blog_identifier="https://demo-blog/")
    )
    result = asyncio.run(_publish(platform, handler))

    assert result.posted_url == "https://demo-blog.tumblr.com/post/42"


def test_tumblr_api_error_is_reported(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"meta": {"status": 401, "msg": "Unauthorized"}, "response": []},
        )

    platform = TumblrPlatform(
        make_settings(tumblr_access_token="tumblr-token", tumblr_blog_identifier="demo-blog.tumblr.com")
    )
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "failed"
    assert "HTTP 401" in result.error
    assert "tumblr-token" not in result.error


def test_bluesky_creates_session_then_post(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/com.atproto.server.createSession"):
            body = json.loads(request.content)
            assert body == {"identifier": "demo.bsky.social", "password": "app-password"}
            return httpx.Response(
                200,
                json={
                    "accessJwt": "jwt-value",
                    "did": "did:plc:abc",
                    "handle": "demo.bsky.social",
                },
            )
        if request.url.path.endswith("/com.atproto.repo.createRecord"):
            assert request.headers["authorization"] == "Bearer jwt-value"
            body = json.loads(request.content)
            assert body["collection"] == "app.bsky.feed.post"
            assert body["record"]["text"] == MESSAGE
            assert body["record"]["createdAt"].endswith("Z")
            return httpx.Response(
                200,
                json={
                    "uri": "at://did:plc:abc/app.bsky.feed.post/3kxyz",
                    "cid": "cid",
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    platform = BlueskyPlatform(
        make_settings(
            bluesky_identifier="demo.bsky.social",
            bluesky_app_password="app-password",
        )
    )
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url == "https://bsky.app/profile/demo.bsky.social/post/3kxyz"
    assert result.public_access is True


def test_bluesky_login_failure_is_reported(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": "AuthenticationRequired",
                "message": "Invalid identifier or password",
            },
        )

    platform = BlueskyPlatform(
        make_settings(
            bluesky_identifier="demo.bsky.social",
            bluesky_app_password="wrong-password",
        )
    )
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "failed"
    assert "HTTP 401" in result.error
    assert "wrong-password" not in result.error


def test_mastodon_normalises_instance_url(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://mastodon.social/api/v1/statuses"
        assert request.headers["authorization"] == "Bearer masto-token"
        assert json.loads(request.content) == {
            "status": MESSAGE,
            "visibility": "public",
        }
        return httpx.Response(
            200,
            json={
                "url": "https://mastodon.social/@demo/123",
                "visibility": "public",
            },
        )

    platform = MastodonPlatform(
        make_settings(
            mastodon_instance_url="mastodon.social",
            mastodon_access_token="masto-token",
        )
    )
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url == "https://mastodon.social/@demo/123"
    assert result.public_access is True


def test_devto_creates_published_article(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://dev.to/api/articles"
        assert request.headers["api-key"] == "dev-key"
        article = json.loads(request.content)["article"]
        assert article["published"] is True
        assert article["body_markdown"] == MESSAGE
        assert 0 < len(article["title"]) <= 70
        return httpx.Response(201, json={"url": "https://dev.to/demo/post-1", "id": 1})

    platform = DevToPlatform(make_settings(devto_api_key="dev-key"))
    result = asyncio.run(_publish(platform, handler))

    assert result.status == "success"
    assert result.posted_url == "https://dev.to/demo/post-1"
    assert result.public_access is True


def test_missing_credentials_make_no_http_call(make_settings) -> None:
    platform = XPlatform(make_settings(x_api_bearer_token=None))
    result = asyncio.run(_publish(platform, lambda request: pytest.fail("must not call the API")))

    assert result.status == "failed"
    assert "X_API_BEARER_TOKEN" in result.error


def test_demo_platform_stores_post_locally(make_settings) -> None:
    platform = DemoPlatform(make_settings(public_base_url="http://localhost:4000"))
    result = asyncio.run(_publish(platform, lambda request: pytest.fail("demo must not use the network")))

    assert result.status == "success"
    assert result.public_access is False
    assert result.posted_url is not None
    post_id = result.posted_url.rsplit("/", 1)[-1]
    stored = platform.get(post_id)
    assert stored is not None
    assert stored.message == MESSAGE


def test_demo_platform_public_base_url(make_settings) -> None:
    platform = DemoPlatform(make_settings(public_base_url="https://posts.example.com"))
    result = asyncio.run(_publish(platform, lambda request: httpx.Response(200)))

    assert result.public_access is True
    assert result.posted_url.startswith("https://posts.example.com/demo/posts/")
