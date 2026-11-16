"""FastAPI application entry point.

Run locally with:
    uvicorn app.main:app --host 0.0.0.0 --port 4000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import gmtime, perf_counter
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.platforms import PlatformRegistry, build_platforms
from app.platforms.base import Post
from app.schemas import (
    DemoPost,
    PlatformInfo,
    PlatformListResponse,
    PostingRequest,
    PostingResponse,
)
from app.services.posting_service import PostingService

logger = logging.getLogger("automated_posting")

DESCRIPTION = """
Publishes one short message (max 200 characters, exactly one CTA link) to every
enabled platform. Platforms are selected internally from the server
configuration; the request only contains the message.

Each integration runs independently and concurrently. A failure on one platform
is reported in its own result without stopping the others.
"""


class _UtcFormatter(logging.Formatter):
    """Log timestamps in UTC so they match the API's date/time fields."""

    converter = gmtime


def _configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            _UtcFormatter(
                fmt="%(asctime)sZ %(levelname)-8s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
    # httpx logs full request URLs at INFO level. Telegram and Discord put
    # credentials in the URL, so these loggers are kept at WARNING.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # httpx2 is only used by Starlette's TestClient in the test suite.
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("httpcore2").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _configure_logging(settings.log_level)

    registry: PlatformRegistry = build_platforms(settings)
    timeout = httpx.Timeout(
        settings.platform_timeout_seconds,
        connect=min(5.0, settings.platform_timeout_seconds),
    )
    client = httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": f"automated-posting/{__version__}"},
        follow_redirects=False,
    )

    app.state.registry = registry
    app.state.demo_platform = registry.demo
    app.state.posting_service = PostingService(
        platforms=registry.enabled,
        client=client,
        timeout_seconds=settings.platform_timeout_seconds,
    )

    logger.info("Starting %s v%s (%s)", settings.app_name, __version__, settings.environment)
    logger.info(
        "Enabled platforms: %s",
        ", ".join(platform.key for platform in registry.enabled) or "none",
    )
    try:
        yield
    finally:
        await client.aclose()
        logger.info("HTTP client closed")


app = FastAPI(
    title="Automated Multi-Platform Posting API",
    version=__version__,
    description=DESCRIPTION,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "posting", "description": "Fan-out publishing endpoint."},
        {"name": "system", "description": "Health and platform readiness."},
        {"name": "demo", "description": "Local sandbox used for offline demos."},
    ],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    started = perf_counter()
    response = await call_next(request)
    # Only the path is logged; query strings can contain secrets.
    logger.info(
        "%s %s -> %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - started) * 1000,
    )
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a compact, consistent 422 body for validation failures."""
    errors = []
    for error in exc.errors():
        if error.get("type") == "json_invalid":
            field = "body"
        else:
            location = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path")]
            field = ".".join(location) or "body"

        message = str(error.get("msg", "Invalid value"))
        # Pydantic prefixes errors raised in validators with "Value error, ".
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ")
        errors.append(
            {
                "field": field,
                "message": message,
                "type": error.get("type", "value_error"),
            }
        )
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed", "errors": errors},
    )


def get_service(request: Request) -> PostingService:
    return request.app.state.posting_service


ServiceDep = Annotated[PostingService, Depends(get_service)]


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": "Automated Multi-Platform Posting API", "docs": "/docs"}


@app.get("/health", tags=["system"], summary="Liveness probe")
async def health(request: Request) -> dict[str, object]:
    platforms = getattr(request.app.state, "registry", None)
    enabled = len(platforms.enabled) if platforms else 0
    return {"status": "ok", "version": __version__, "platforms_enabled": enabled}


@app.get(
    "/platforms",
    response_model=PlatformListResponse,
    tags=["system"],
    summary="List integrations and whether they are configured",
)
async def list_platforms(request: Request) -> PlatformListResponse:
    registry: PlatformRegistry | None = getattr(request.app.state, "registry", None)
    if registry is None:
        return PlatformListResponse(platforms=[])
    enabled_keys = {platform.key for platform in registry.enabled}
    return PlatformListResponse(
        platforms=[
            PlatformInfo(
                key=platform.key,
                name=platform.name,
                enabled=platform.key in enabled_keys,
                configured=platform.configured,
                required_env=platform.required_env,
                docs_url=platform.docs_url or None,
            )
            for platform in registry.all
        ]
    )


@app.post(
    "/posting",
    response_model=PostingResponse,
    tags=["posting"],
    summary="Publish a message to all enabled platforms",
    responses={
        422: {"description": "Invalid message, URL, or request body."},
        503: {"description": "No posting platform is enabled."},
    },
)
async def publish_posting(payload: PostingRequest, service: ServiceDep) -> PostingResponse:
    """Validate the message, then publish to every enabled platform concurrently."""
    response = await service.publish(Post(message=payload.message, cta_url=payload.cta_url))
    if not response.results:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=("No posting platforms are enabled. Configure credentials in .env or enable the demo platform."),
        )
    return response


@app.get(
    "/demo/posts/{post_id}",
    response_model=DemoPost,
    tags=["demo"],
    summary="Read a post stored by the local demo platform",
)
async def get_demo_post(post_id: str, request: Request) -> DemoPost:
    demo = getattr(request.app.state, "demo_platform", None)
    post = demo.get(post_id) if demo is not None else None
    if post is None:
        raise HTTPException(status_code=404, detail="Demo post not found")
    return post
