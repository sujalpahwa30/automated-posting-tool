"""API and orchestration tests."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_service
from app.platforms.base import Platform, PlatformError, Post
from app.platforms.x import XPlatform
from app.services.posting_service import PostingService

MESSAGE = "Check out our latest business platform and grow your online visibility. https://example.com"
RESULT_FIELDS = {
    "platform",
    "status",
    "posted_url",
    "public_access",
    "date",
    "time",
    "error",
}


class OkPlatform(Platform):
    key = "ok"
    name = "Ok"

    async def _publish(self, client, post):  # type: ignore[no-untyped-def]
        return self.success("https://example.com/ok", public_access=True)


class FailPlatform(Platform):
    key = "fail"
    name = "Fail"

    async def _publish(self, client, post):  # type: ignore[no-untyped-def]
        raise PlatformError("platform exploded")


class CrashPlatform(Platform):
    key = "crash"
    name = "Crash"

    async def _publish(self, client, post):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


class SlowPlatform(Platform):
    key = "slow"
    name = "Slow"

    async def _publish(self, client, post):  # type: ignore[no-untyped-def]
        await asyncio.sleep(1)
        return self.success(None, public_access=False)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _override_service(service: PostingService) -> None:
    app.dependency_overrides[get_service] = lambda: service


def _post() -> Post:
    return Post(message=MESSAGE, cta_url="https://example.com")


def test_posting_returns_a_result_for_every_platform(client, make_settings) -> None:
    service = PostingService(
        [OkPlatform(make_settings()), FailPlatform(make_settings())],
        client=None,
        timeout_seconds=5,
    )
    _override_service(service)

    response = client.post("/posting", json={"message": MESSAGE})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["summary"] == {"total": 2, "successful": 1, "failed": 1}
    assert [result["platform"] for result in body["results"]] == ["Ok", "Fail"]
    assert set(body["results"][0]) == RESULT_FIELDS
    assert body["results"][0]["error"] is None
    assert body["results"][1]["status"] == "failed"
    assert body["results"][1]["posted_url"] is None
    assert body["results"][1]["date"] is None
    assert body["results"][1]["error"] == "platform exploded"


def test_unexpected_errors_and_timeouts_are_isolated(make_settings) -> None:
    service = PostingService(
        [
            OkPlatform(make_settings()),
            CrashPlatform(make_settings()),
            SlowPlatform(make_settings()),
        ],
        client=None,
        timeout_seconds=0.05,
    )
    response = asyncio.run(service.publish(_post()))

    assert response.success is True
    assert response.summary.successful == 1
    assert response.summary.failed == 2
    crash = next(result for result in response.results if result.platform == "Crash")
    slow = next(result for result in response.results if result.platform == "Slow")
    assert "Unexpected internal error" in crash.error
    assert "Timed out after 0.05s" in slow.error


def test_service_reports_missing_credentials(make_settings) -> None:
    service = PostingService(
        [XPlatform(make_settings(x_api_bearer_token=None))],
        client=None,
        timeout_seconds=1,
    )
    response = asyncio.run(service.publish(_post()))

    assert response.success is False
    assert response.results[0].status == "failed"
    assert "X_API_BEARER_TOKEN" in response.results[0].error


@pytest.mark.parametrize(
    ("message", "expected_error"),
    [
        ("too short", "exactly one CTA link (found 0)"),
        ("a" * 181 + " https://example.com", "at most 200 characters"),
        ("Two https://a.example.com https://b.example.com", "found 2"),
        ("Bare www.example.com", "must start with http"),
        ("Bad host https://example", "public domain name"),
        ("", "must not be empty"),
    ],
)
def test_posting_validation_errors(client, message: str, expected_error: str) -> None:
    response = client.post("/posting", json={"message": message})

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Request validation failed"
    assert body["errors"][0]["field"] == "message"
    assert expected_error in body["errors"][0]["message"]


def test_non_string_message_is_rejected(client) -> None:
    response = client.post("/posting", json={"message": 42})

    assert response.status_code == 422
    assert response.json()["errors"][0]["message"] == "message must be a string"


def test_missing_message_is_rejected(client) -> None:
    response = client.post("/posting", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["errors"][0]["field"] == "message"
    assert body["errors"][0]["message"] == "Field required"


def test_malformed_json_returns_422(client) -> None:
    response = client.post(
        "/posting",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Request validation failed"
    assert response.json()["errors"][0]["field"] == "body"


def test_unknown_fields_are_ignored_and_platform_selection_is_internal(client) -> None:
    response = client.post(
        "/posting",
        json={"message": MESSAGE, "platforms": ["x"]},
    )

    assert response.status_code == 200
    # Only the demo platform is enabled in the test environment.
    assert [result["platform"] for result in response.json()["results"]] == ["Demo (local sandbox)"]


def test_demo_platform_end_to_end(client) -> None:
    response = client.post("/posting", json={"message": MESSAGE})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {"total": 1, "successful": 1, "failed": 0}
    result = body["results"][0]
    assert result["status"] == "success"
    assert result["public_access"] is False
    assert result["error"] is None
    assert result["posted_url"]

    detail = client.get(urlsplit(result["posted_url"]).path)
    assert detail.status_code == 200
    assert detail.json()["message"] == MESSAGE


def test_unknown_demo_post_returns_404(client) -> None:
    assert client.get("/demo/posts/does-not-exist").status_code == 404


def test_health_and_platform_listing(client) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["platforms_enabled"] == 1

    platforms = client.get("/platforms").json()["platforms"]
    assert [item["key"] for item in platforms] == [
        "x",
        "linkedin",
        "telegram",
        "discord",
        "slack",
        "bluesky",
        "mastodon",
        "devto",
        "demo",
    ]
    x_platform = platforms[0]
    assert x_platform["required_env"] == ["X_API_BEARER_TOKEN"]
    assert x_platform["configured"] is False
    assert x_platform["enabled"] is False
    assert platforms[-1]["key"] == "demo"
    assert platforms[-1]["enabled"] is True


def test_no_enabled_platforms_returns_503(client) -> None:
    _override_service(PostingService([], client=None, timeout_seconds=1))

    response = client.post("/posting", json={"message": MESSAGE})

    assert response.status_code == 503
    assert "No posting platforms are enabled" in response.json()["detail"]
