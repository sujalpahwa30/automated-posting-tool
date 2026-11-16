"""Platform registry and internal platform selection."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.platforms.base import Platform, PlatformError, Post
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.demo import DemoPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.linkedin import LinkedInPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.slack import SlackPlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.x import XPlatform

PLATFORM_CLASSES: tuple[type[Platform], ...] = (
    XPlatform,
    LinkedInPlatform,
    TelegramPlatform,
    DiscordPlatform,
    SlackPlatform,
    BlueskyPlatform,
    MastodonPlatform,
    DevToPlatform,
)

__all__ = [
    "PLATFORM_CLASSES",
    "Platform",
    "PlatformError",
    "PlatformRegistry",
    "Post",
    "build_platforms",
]


@dataclass(frozen=True)
class PlatformRegistry:
    """All known platforms plus the subset enabled for this process."""

    all: tuple[Platform, ...]
    enabled: tuple[Platform, ...]
    demo: DemoPlatform


def build_platforms(settings: Settings) -> PlatformRegistry:
    """Instantiate integrations and decide which ones should receive posts.

    Selection is internal: either the explicit PLATFORMS allowlist, or every
    integration that has credentials (plus the demo platform if enabled).
    """
    demo = DemoPlatform(settings)
    instances = [platform_class(settings) for platform_class in PLATFORM_CLASSES]
    all_platforms: list[Platform] = [*instances, demo]
    by_key = {platform.key: platform for platform in all_platforms}

    requested = settings.platform_allowlist
    if requested:
        unknown = [key for key in requested if key not in by_key]
        if unknown:
            valid = ", ".join(by_key)
            raise ValueError(f"Unknown platform(s) in PLATFORMS: {', '.join(unknown)}. Valid keys: {valid}.")
        # Preserve the configured order and drop duplicates.
        seen: set[str] = set()
        enabled: list[Platform] = []
        for key in requested:
            if key not in seen:
                seen.add(key)
                enabled.append(by_key[key])
    else:
        enabled = [platform for platform in instances if platform.configured]
        if settings.demo_platform_enabled:
            enabled.append(demo)

    return PlatformRegistry(
        all=tuple(all_platforms),
        enabled=tuple(enabled),
        demo=demo,
    )
