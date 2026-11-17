"""Shared pytest fixtures.

The tests never call real platforms. Credential environment variables are
blanked so a developer's local .env cannot accidentally trigger live posting.
"""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings

CREDENTIAL_ENV_VARS = (
    "X_API_BEARER_TOKEN",
    "LINKEDIN_ACCESS_TOKEN",
    "LINKEDIN_AUTHOR_URN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "DISCORD_WEBHOOK_URL",
    "SLACK_WEBHOOK_URL",
    "BLUESKY_IDENTIFIER",
    "BLUESKY_APP_PASSWORD",
    "MASTODON_INSTANCE_URL",
    "MASTODON_ACCESS_TOKEN",
    "TUMBLR_ACCESS_TOKEN",
    "TUMBLR_BLOG_IDENTIFIER",
    "TUMBLR_CLIENT_ID",
    "TUMBLR_CLIENT_SECRET",
    "DEVTO_API_KEY",
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    for name in CREDENTIAL_ENV_VARS:
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("PLATFORMS", "")
    monkeypatch.setenv("DEMO_PLATFORM_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def make_settings():
    def factory(**overrides: object) -> Settings:
        return Settings(_env_file=None, **overrides)

    return factory
