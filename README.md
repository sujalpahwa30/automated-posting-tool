# Automated Multi-Platform Posting API

A FastAPI service that validates one short marketing message and publishes it to
multiple third-party platforms **concurrently and independently**. A failure on
one platform never blocks or changes the outcome of the others.

The request body only contains the message. Platform selection is handled
internally from server-side configuration (credentials plus an optional
`PLATFORMS` allowlist), as required by the brief.

```
POST http://localhost:4000/posting
{"message": "Check out our latest business platform and grow your online visibility. https://example.com"}
```

- **9 real third-party integrations**: X (Twitter), LinkedIn, Telegram, Discord,
  Slack, Bluesky, Mastodon, Tumblr, Dev.to.
- **1 local demo integration** for offline review without credentials.
- **59 automated tests**, linted with Ruff, CI workflow included.
- Interactive docs: <http://localhost:4000/docs>.

A real captured request/response and server log are in
[`docs/sample-run.txt`](docs/sample-run.txt).

---

## Contents

- [Integrations](#integrations)
- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Platform setup notes](#platform-setup-notes)
- [Testing and linting](#testing-and-linting)
- [Docker](#docker)
- [Design decisions](#design-decisions)
- [Security notes](#security-notes)
- [Known limitations](#known-limitations)
- [What I would improve next](#what-i-would-improve-next)
- [Project structure](#project-structure)

---

## Integrations

| Key | Platform | Credentials | Published as | Returned URL | `public_access` |
|---|---|---|---|---|---|
| `x` | X (Twitter) | `X_API_BEARER_TOKEN` | Post via `POST /2/tweets` | `https://x.com/i/web/status/{id}` | `true` (public account assumed) |
| `linkedin` | LinkedIn | `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN` | `POST /rest/posts` | `https://www.linkedin.com/feed/update/{urn}` | `true` (`visibility: PUBLIC`) |
| `telegram` | Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `sendMessage` to a channel | `https://t.me/{username}/{id}` | `true` only for channels with a public username |
| `discord` | Discord | `DISCORD_WEBHOOK_URL` | Webhook message | `https://discord.com/channels/{guild}/{channel}/{message}` | `true` when the webhook belongs to a guild channel |
| `slack` | Slack | `SLACK_WEBHOOK_URL` | Incoming-webhook message | none (webhooks return no permalink) | `false` |
| `bluesky` | Bluesky | `BLUESKY_IDENTIFIER`, `BLUESKY_APP_PASSWORD` | `createSession` + `repo.createRecord` | `https://bsky.app/profile/{handle}/post/{rkey}` | `true` |
| `mastodon` | Mastodon | `MASTODON_INSTANCE_URL`, `MASTODON_ACCESS_TOKEN` | `POST /api/v1/statuses` | Status URL from the API | `true` for `public` / `unlisted` |
| `tumblr` | Tumblr | `TUMBLR_ACCESS_TOKEN`, `TUMBLR_BLOG_IDENTIFIER` | Text post via v2 `blog/{blog}/post` | `https://{blog}/post/{id}` | `true` (`state: published`) |
| `devto` | Dev.to | `DEVTO_API_KEY` | Published article | Article URL from the API | `true` |
| `demo` | Local sandbox | none | In-memory store | `http://localhost:4000/demo/posts/{id}` | `false` for localhost |

Documentation used for each API is exposed by `GET /platforms` and linked in
the adapter modules under [`app/platforms/`](app/platforms/).

> **Why a demo platform?** Reviewers can run the full endpoint, see a posted URL,
> and open the stored post without credentials or external accounts. The demo
> result is clearly labelled `Demo (local sandbox)`; it is not presented as a
> third-party service. Configure any real platform to see real posting.

### Public access semantics

`public_access` is deliberately conservative and reflects what the API proves:

- Telegram returns `false` for private chats or channels without a username,
  because no public `t.me` URL can be produced.
- Discord is a heuristic: the integration can prove the message belongs to a
  guild channel, but not whether that channel/server is public.
- Slack incoming webhooks return neither a permalink nor channel metadata, so
  `posted_url` is `null` and `public_access` is `false` even on success.
- X, LinkedIn and Bluesky assume the connected account and post are public.
- Mastodon uses the `visibility` returned by the instance; locked accounts may
  still restrict reach.
- Dev.to articles are published (`published: true`) and therefore public.

---

## How it works

```
Client
  │  POST /posting  {"message": "..."}
  ▼
FastAPI route
  │
  ├─ Pydantic validation
  │    • 1–200 characters
  │    • exactly one CTA link
  │    • valid http(s) URL, public host (localhost allowed for testing)
  │
  ▼
PostingService
  │  asyncio.gather(...) with a per-platform timeout
  │
  ├── X        ──► api.x.com
  ├── LinkedIn ──► api.linkedin.com
  ├── Telegram ──► api.telegram.org
  ├── Discord  ──► webhook URL
  ├── Slack    ──► incoming webhook URL
  ├── Bluesky  ──► PDS: createSession → repo.createRecord
  ├── Mastodon ──► /api/v1/statuses
  ├── Tumblr   ──► api.tumblr.com/v2/blog/{blog}/post
  ├── Dev.to   ──► /api/articles
  └── Demo     ──► in-memory store + GET /demo/posts/{id}
  │
  ▼
{"success": true, "summary": {...}, "results": [...]}
```

Key properties:

- **Isolation** — each integration has its own try/except boundary. API errors,
  timeouts, malformed responses and unexpected exceptions become failed results.
- **Concurrency** — all platforms are contacted in parallel, so total latency is
  close to the slowest enabled platform rather than the sum.
- **No retries on POST** — retrying a non-idempotent publish can create duplicate
  posts. Failures are reported instead.
- **Credential checks happen before any network call**, so a missing token is
  reported in milliseconds.

---

## Quick start

Requirements: Python 3.11+ (tested on 3.12.6).

```bash
git clone <your-repository-url>
cd automated-posting

python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Start the server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Open <http://localhost:4000/docs>. With no credentials configured, the demo
platform is enabled and the endpoint works end-to-end:

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message":"Check out our latest business platform and grow your online visibility. https://example.com"}'
```

```json
{
  "success": true,
  "summary": { "total": 1, "successful": 1, "failed": 0 },
  "results": [
    {
      "platform": "Demo (local sandbox)",
      "status": "success",
      "posted_url": "http://localhost:4000/demo/posts/cbd4292188c64d44",
      "public_access": false,
      "date": "2026-11-16",
      "time": "18:19:16",
      "error": null
    }
  ]
}
```

`GET /demo/posts/{id}` returns the stored content, proving the returned URL
works. Add real credentials to `.env` and they are picked up on restart.

---

## Configuration

All configuration is read from environment variables or a local `.env` file.
See [`.env.example`](.env.example) for the full annotated list.

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | Free-form environment label. |
| `LOG_LEVEL` | `INFO` | Root log level. |
| `PUBLIC_BASE_URL` | `http://localhost:4000` | Base URL used to build demo post links. |
| `PLATFORM_TIMEOUT_SECONDS` | `15` | Per-platform budget (1–120 s). |
| `PLATFORMS` | empty | Optional comma-separated allowlist. Empty = auto-detect. |
| `DEMO_PLATFORM_ENABLED` | `true` | Enable the local sandbox. |
| `X_API_BEARER_TOKEN` | — | OAuth 2.0 **user-context** token with `tweet.write`. |
| `LINKEDIN_ACCESS_TOKEN` | — | Member token with `w_member_social`. |
| `LINKEDIN_AUTHOR_URN` | — | e.g. `urn:li:person:abc` or `urn:li:organization:123`. |
| `LINKEDIN_API_VERSION` | `202601` | Active `YYYYMM` LinkedIn API version. |
| `TELEGRAM_BOT_TOKEN` | — | Bot token from `@BotFather`. |
| `TELEGRAM_CHAT_ID` | — | `@public_channel` or numeric chat id. |
| `DISCORD_WEBHOOK_URL` | — | Channel webhook URL. |
| `SLACK_WEBHOOK_URL` | — | Incoming webhook URL. |
| `BLUESKY_IDENTIFIER` | — | Handle or email. |
| `BLUESKY_APP_PASSWORD` | — | App password (not the main password). |
| `BLUESKY_SERVICE_URL` | `https://bsky.social` | PDS base URL. |
| `MASTODON_INSTANCE_URL` | — | e.g. `https://mastodon.social`; scheme optional. |
| `MASTODON_ACCESS_TOKEN` | — | Token with `write:statuses`. |
| `TUMBLR_CLIENT_ID` | — | OAuth2 consumer key (only needed by `scripts/tumblr_auth.py`). |
| `TUMBLR_CLIENT_SECRET` | — | OAuth2 secret key (only needed by `scripts/tumblr_auth.py`). |
| `TUMBLR_REDIRECT_URI` | `http://localhost:8765/callback` | Must match the app's callback URL. |
| `TUMBLR_ACCESS_TOKEN` | — | Token printed by `scripts/tumblr_auth.py`. |
| `TUMBLR_BLOG_IDENTIFIER` | — | e.g. `myblog.tumblr.com`; a bare name gets the suffix. |
| `DEVTO_API_KEY` | — | DEV API key. |

### Platform selection rules

1. If `PLATFORMS` is set, exactly those keys are enabled, in that order.
   Unknown keys fail fast at startup; platforms with missing credentials stay
   enabled and report a configuration error per request.
2. If `PLATFORMS` is empty, every real platform with complete credentials is
   enabled, plus the demo platform when `DEMO_PLATFORM_ENABLED=true`.
3. Empty-string credentials count as missing.
4. The request body cannot influence platform selection; extra fields are
   ignored.

Examples:

```dotenv
# Only Telegram and Mastodon
PLATFORMS=telegram,mastodon

# Everything with credentials (default behaviour)
PLATFORMS=

# Force a platform even if its credential is missing (shows the failure path)
PLATFORMS=demo,x
```

`GET /platforms` reports every supported key, whether it is configured, whether
it is enabled, and which environment variables it needs.

---

## API reference

### `POST /posting`

Publishes the message to every enabled platform.

| Body field | Type | Rules |
|---|---|---|
| `message` | string | Required. 1–200 characters after trimming. Exactly one CTA link. |

Validation rules:

- The message is trimmed; empty messages are rejected.
- Length is measured in Unicode code points (`len`), not bytes.
- Exactly **one** link is allowed. `http://`, `https://` and bare `www.` links
  are counted; bare `www.` links are rejected with a "must start with http"
  message.
- The link must be a valid `http`/`https` URL with a public hostname
  (`localhost` is allowed for development).
- Trailing sentence punctuation such as `https://example.com.` is not treated
  as part of the URL. Balanced parentheses in paths are preserved.
- Other control characters (except newline/tab) are rejected.
- The message itself is forwarded unchanged apart from outer whitespace.

Response fields (`results[]`):

| Field | Description |
|---|---|
| `platform` | Human-readable platform name. |
| `status` | `success` or `failed`. |
| `posted_url` | Public URL of the created content, when available. |
| `public_access` | Best-effort public visibility flag (see notes above). |
| `date` / `time` | UTC date (`YYYY-MM-DD`) and time (`HH:MM:SS`). `null` on failure. |
| `error` | Redacted, human-readable failure reason. `null` on success. |

Top-level behaviour:

- HTTP `200` for valid input, even when some (or all) platforms fail. Inspect
  `success` and `summary` for the outcome.
- `success` is `true` when at least one platform published successfully.
- HTTP `422` for validation errors, with a consistent `errors[]` array.
- HTTP `503` when no platform is enabled at all.
- HTTP `502` is **not** used; partial success is a normal, expected outcome for
  a fan-out API.

#### Sample real response

Captured live with `PLATFORMS=bluesky,demo` and a real Bluesky account (full run
in [`docs/sample-run.txt`](docs/sample-run.txt)):

```json
{
  "success": true,
  "summary": { "total": 2, "successful": 2, "failed": 0 },
  "results": [
    {
      "platform": "Bluesky",
      "status": "success",
      "posted_url": "https://bsky.app/profile/sujalpahwa30.bsky.social/post/3n2hdbam6lu2b",
      "public_access": true,
      "date": "2026-11-16",
      "time": "20:05:58",
      "error": null
    },
    {
      "platform": "Demo (local sandbox)",
      "status": "success",
      "posted_url": "http://localhost:4000/demo/posts/3ced8d35eb0f4f95",
      "public_access": false,
      "date": "2026-11-16",
      "time": "20:05:57",
      "error": null
    }
  ]
}
```

`date`/`time` are UTC. The Bluesky URL was confirmed publicly readable without
credentials via `app.bsky.feed.getPostThread` on the public AppView.

#### Sample validation error

```json
{
  "detail": "Request validation failed",
  "errors": [
    {
      "field": "message",
      "message": "message must contain exactly one CTA link (found 2)",
      "type": "value_error"
    }
  ]
}
```

### `GET /health`

```json
{"status": "ok", "version": "1.0.0", "platforms_enabled": 2}
```

### `GET /platforms`

```json
{
  "platforms": [
    {
      "key": "x",
      "name": "X (Twitter)",
      "enabled": false,
      "configured": false,
      "required_env": ["X_API_BEARER_TOKEN"],
      "docs_url": "https://docs.x.com/x-api/posts/create-post"
    }
  ]
}
```

### `GET /demo/posts/{post_id}`

Returns the in-memory post created by the demo platform, or `404`.

---

## Platform setup notes

These are the additional account-level steps that the API cannot do for you.
All endpoints were implemented against the providers' current REST APIs and
require credentials with write scope.

**X (Twitter)** — create an app in the X developer portal and obtain an OAuth
2.0 **user-context** token with `tweet.write` (app-only bearer tokens cannot
post). Posting access depends on your X API plan; the Free tier has tight
limits. The endpoint used is `POST https://api.x.com/2/tweets`.

**LinkedIn** — create a LinkedIn app, add the "Share on LinkedIn" product and
request `w_member_social`, then complete 3-legged OAuth. `LINKEDIN_AUTHOR_URN`
is `urn:li:person:{id}` for a member or `urn:li:organization:{id}` for a page.
`LINKEDIN_API_VERSION` must be a version your app is allowed to use; LinkedIn
retires old versions regularly. The integration uses the versioned Posts API
(`POST https://api.linkedin.com/rest/posts`) and reads the post URN from the
`x-restli-id` response header.

**Telegram** — create a bot with `@BotFather`, add it as an administrator of the
target channel, and use `@channelusername` as `TELEGRAM_CHAT_ID`. The bot API
returns the channel username, which is used to build the public `t.me` URL.

**Discord** — create a webhook under *Server Settings → Integrations →
Webhooks*. The integration calls it with `?wait=true` so the created message id
is returned, and disables `@everyone`/role pings via `allowed_mentions`. That
response omits `guild_id`, so the guild is read from the webhook details (once,
then cached) to build the channel message URL.

**Slack** — create a free workspace, then add an *Incoming Webhook* under
<https://api.slack.com/apps> (*Create New App → From scratch → Incoming
Webhooks → Add New Webhook to Workspace*) and copy the `hooks.slack.com`
URL. Slack answers `200 ok` with a plain-text body, which is why this adapter
reads the raw response instead of JSON. Incoming webhooks cannot return a
permalink, so `posted_url` is `null` while the message is still delivered.

**Bluesky** — use an **App Password** (Settings → Privacy and security → App
passwords) rather than the account password. The integration creates a session
with `com.atproto.server.createSession`, then writes an
`app.bsky.feed.post` record through `com.atproto.repo.createRecord`.

**Mastodon** — create an application under *Preferences → Development* with the
`write:statuses` scope and copy its access token. Any Mastodon-compatible
instance works; `MASTODON_INSTANCE_URL` may omit `https://`.

**Tumblr** — create an app at <https://www.tumblr.com/oauth/apps> with the
callback URL `http://localhost:8765/callback`, put the consumer key and secret
in `.env`, then run `python scripts/tumblr_auth.py`. It opens the authorization
page, captures the callback locally and prints the `TUMBLR_ACCESS_TOKEN` line.
Posts are created as legacy `type=text` posts; Tumblr rejects the neo-format
`content` array from API-created apps with code `8001` ("Post cannot be empty").
The body is HTML-escaped and the CTA URL is turned into a link.

The token exchange pins TLS 1.2 because some networks (antivirus proxies, ISP
middleboxes) reset the default TLS 1.2/1.3 negotiation against Tumblr's edge;
the adapter retries once over the same pinned context if a connection is reset
before any response.

**Dev.to** — generate a key under *Settings → Extensions → DEV API Keys*. Dev.to
publishes articles rather than micro-posts, so the integration derives a short
title from the message and publishes the message as the article body.

---

## Testing and linting

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

Expected result:

```
59 passed
All checks passed!
```

The suite covers:

- validation boundaries (200/201 characters, zero/two/duplicate links, bare
  domains, control characters, trailing punctuation, localhost);
- each platform adapter against a mocked `httpx.MockTransport`, including
  request shape, headers, URL construction and error mapping;
- token redaction in error messages;
- partial failure, timeout and unexpected-exception isolation in the service;
- API status codes, response shape, summary counts, the demo flow, `/health`
  and `/platforms`.

No test makes a real network call. `tests/conftest.py` blanks credential
environment variables so a developer's `.env` cannot trigger live posting.

---

## Docker

```bash
docker build -t automated-posting .
docker run --rm -p 4000:4000 --env-file .env automated-posting
```

The image runs the exact command from the brief:
`uvicorn app.main:app --host 0.0.0.0 --port 4000`.

---

## Design decisions

- **Small platform contract.** `Platform.publish()` is a template method: it
  checks credentials, calls the integration-specific `_publish()`, and converts
  `PlatformError` into a failed result. Adding a platform means adding one file
  and one registry entry.
- **One shared `httpx.AsyncClient`** created in the FastAPI lifespan, with a
  configured timeout and connection pooling. It is closed on shutdown.
- **Concurrency with `asyncio.gather`**, plus `asyncio.wait_for` as a safety net
  for integrations that do not respect the HTTP timeout.
- **Validation belongs to the domain, not the route.** `app/services/validation.py`
  can be unit-tested directly; the Pydantic schema wraps it so FastAPI produces
  `422` responses automatically.
- **UTC timestamps** in results and logs. The brief does not specify a timezone;
  UTC avoids ambiguity in distributed deployments.
- **Fail fast on unknown platform keys**, but never fail the request because a
  single platform is misconfigured.
- **Consistent error envelope** for validation errors
  (`{"detail": ..., "errors": [{field, message, type}]}`) while preserving
  FastAPI's familiar `detail` field.

### Assumptions

- The CTA link must include an explicit `http://` or `https://` scheme.
- The 200-character limit covers the whole message including the URL.
- Platform selection is static server configuration, not a request field.
- Each platform receives the same text; per-platform tailoring was out of scope.
- The demo platform exists only for local/offline verification and stores data
  in memory.

---

## Security notes

- `.env` is git-ignored; only `.env.example` with empty values is committed.
- Error messages are sanitised: known secrets and credential-bearing URLs are
  never echoed, and provider error bodies are redacted and truncated.
- `httpx` request logging is disabled (`WARNING`) because Telegram, Discord and
  Slack embed credentials in the request URL.
- Request bodies and message text are not logged.
- Unexpected exceptions are logged server-side with a traceback but returned to
  clients as a generic message.
- The API itself has no authentication. Put it behind an API gateway, reverse
  proxy with auth, or add API-key auth before exposing it publicly.

---

## Known limitations

- Publishing is synchronous: the response waits for the slowest platform, bounded
  by `PLATFORM_TIMEOUT_SECONDS`.
- No automatic retry/backoff. POSTs are not idempotent, so retries could duplicate
  content; `429`/`5xx` responses are reported instead.
- Tokens are static environment values. There is no OAuth callback flow, token
  refresh, or encrypted token storage.
- X posting requires a paid API plan in most cases; LinkedIn requires an active
  API version; provider policies change.
- `public_access` is a best-effort flag, not a guarantee (see the table notes).
- The demo store is in-memory and per process; it is not shared across workers
  and is lost on restart.
- Message length uses code points, not grapheme clusters.
- Text only: no images, videos, threads, polls, or scheduling.
- No persistence/audit history of published posts.
- No per-platform text adaptation (except the derived Dev.to title).
- `--workers N > 1` would give each worker its own demo store and its own HTTP
  client; real platforms are stateless, so the demo is the only limitation.

---

## What I would improve next

1. **Authentication and quotas** — an API key/JWT layer plus per-client rate
   limiting before this is exposed.
2. **Asynchronous jobs** — accept the request, enqueue it, and expose
   `GET /posting/{job_id}` with per-platform retry state; use idempotency keys
   to make retries safe.
3. **OAuth lifecycle** — encrypted token storage and refresh for X/LinkedIn.
4. **Retries with respect** — honour `Retry-After` for `429`/`503`, exponential
   backoff with jitter, and only where the provider supports idempotent creates.
5. **Persistent audit log** — store every attempt, response, and public URL in
   Postgres, with retention and query endpoints.
6. **Per-platform content** — truncation/threading rules (X), media uploads,
   and platform-specific formatting.
7. **Observability** — metrics (`posting_total{platform,status}`), structured
   JSON logs, tracing, and alerting on repeated auth failures.
8. **Richer verification** — fetch the resulting public URL (where the API
   supports it) to verify `public_access` instead of inferring it.

---

## Project structure

```
automated-posting/
├── app/
│   ├── main.py                  # FastAPI app, lifespan, routes, error envelope
│   ├── config.py                # pydantic-settings configuration
│   ├── schemas.py               # request/response models
│   ├── platforms/
│   │   ├── base.py              # Platform ABC, Post, HTTP/error helpers
│   │   ├── x.py                 # X (Twitter) API v2
│   │   ├── linkedin.py          # LinkedIn Posts API
│   │   ├── telegram.py          # Telegram Bot API
│   │   ├── discord.py           # Discord webhook
│   │   ├── slack.py             # Slack incoming webhook
│   │   ├── bluesky.py           # AT Protocol session + post
│   │   ├── mastodon.py          # Mastodon statuses API
│   │   ├── tumblr.py            # Tumblr v2 text posts
│   │   ├── devto.py             # Forem articles API
│   │   ├── demo.py              # Local sandbox + in-memory store
│   │   └── __init__.py          # registry and internal selection
│   └── services/
│       ├── validation.py        # 200-char / single-CTA validation
│       └── posting_service.py   # concurrent fan-out and isolation
├── scripts/
│   └── tumblr_auth.py           # OAuth2 helper for the Tumblr token
├── tests/
│   ├── conftest.py              # isolation from local .env
│   ├── test_validation.py
│   ├── test_platforms.py
│   └── test_posting_api.py
├── docs/sample-run.txt          # real captured run
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml               # pytest + Ruff configuration
└── .github/workflows/tests.yml  # CI: lint + tests
```

---

## API documentation

FastAPI generates OpenAPI at `/openapi.json` and interactive Swagger UI at
`/docs` (ReDoc at `/redoc`). The `/posting` schema includes a ready-to-use
example request, and the validation rules are documented in the field
description.
