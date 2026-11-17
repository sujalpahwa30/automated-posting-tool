"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view of the environment.

    Every credential is optional so the service still starts without a fully
    configured .env. Platforms that are missing credentials are simply not
    auto-enabled (and report a clear error if forced via PLATFORMS).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ server
    app_name: str = "Automated Multi-Platform Posting API"
    environment: str = "development"
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:4000"
    platform_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    # Comma-separated allowlist; empty means "auto-detect from credentials".
    platforms: str = ""
    demo_platform_enabled: bool = True

    # --------------------------------------------------------------- platforms
    # X (Twitter) - OAuth 2.0 user-context bearer token with tweet.write scope.
    x_api_bearer_token: str | None = None

    # LinkedIn - 3-legged member token with w_member_social scope.
    linkedin_access_token: str | None = None
    linkedin_author_urn: str | None = None
    linkedin_api_version: str = "202601"

    # Telegram - bot token from @BotFather and a channel/chat id.
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # Discord - channel webhook URL.
    discord_webhook_url: str | None = None

    # Slack - incoming webhook URL.
    slack_webhook_url: str | None = None

    # Bluesky / AT Protocol - app password (never the main account password).
    bluesky_identifier: str | None = None
    bluesky_app_password: str | None = None
    bluesky_service_url: str = "https://bsky.social"

    # Mastodon - instance base URL and a token with write:statuses.
    mastodon_instance_url: str | None = None
    mastodon_access_token: str | None = None

    # Dev.to (Forem) - API key from the account settings.
    devto_api_key: str | None = None

    # Tumblr - OAuth2 app credentials are only needed to obtain a token; the
    # adapter itself uses the access token and the target blog.
    tumblr_client_id: str | None = None
    tumblr_client_secret: str | None = None
    tumblr_access_token: str | None = None
    tumblr_blog_identifier: str | None = None
    tumblr_redirect_uri: str = "http://localhost:8765/callback"

    @field_validator("public_base_url")
    @classmethod
    def _clean_base_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("linkedin_api_version")
    @classmethod
    def _validate_linkedin_version(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"\d{6}", value):
            raise ValueError("LINKEDIN_API_VERSION must use the YYYYMM format, e.g. 202601")
        return value

    @property
    def platform_allowlist(self) -> list[str] | None:
        keys = [part.strip().lower() for part in self.platforms.split(",") if part.strip()]
        return keys or None


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide settings instance (re-read with cache_clear())."""
    return Settings()
