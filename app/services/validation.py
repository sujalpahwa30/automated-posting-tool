"""Message validation and CTA-link extraction.

The assignment requires a maximum of 200 characters and exactly one valid
call-to-action link. Keeping this logic outside the route makes it directly
unit-testable and reusable by the Pydantic schema.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import HttpUrl, TypeAdapter, ValidationError

MAX_MESSAGE_LENGTH = 200
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}

# Matches http(s) links and bare "www." links. finditer() produces
# non-overlapping matches, so "https://www.example.com" is counted once.
_URL_PATTERN = re.compile(
    r"""(?<![\w@])(?:https?://|www\.)[^\s<>"'\u2018\u2019\u201c\u201d`]+""",
    re.IGNORECASE,
)

_TRAILING_PUNCTUATION = ".,;:!?'\"\u2019\u201d"
_BRACKET_PAIRS = {")": "(", "]": "[", "}": "{"}
_HTTP_URL = TypeAdapter(HttpUrl)


def find_urls(message: str) -> list[str]:
    """Return every link candidate found in the message, in order."""
    return [match.group(0) for match in _URL_PATTERN.finditer(message)]


def _trim_trailing_punctuation(url: str) -> str:
    """Drop sentence punctuation that is not part of the URL.

    Closing brackets are only removed when they are unbalanced, so URLs such as
    https://en.wikipedia.org/wiki/Foo_(bar) keep their parentheses.
    """
    while url:
        last = url[-1]
        if last in _TRAILING_PUNCTUATION:
            url = url[:-1]
        elif last in _BRACKET_PAIRS and url.count(last) > url.count(_BRACKET_PAIRS[last]):
            url = url[:-1]
        else:
            break
    return url


def extract_cta_url(message: str) -> str:
    """Validate and return the single CTA link contained in ``message``."""
    urls = find_urls(message)
    if len(urls) != 1:
        raise ValueError(f"message must contain exactly one CTA link (found {len(urls)})")

    candidate = urls[0]
    if candidate.lower().startswith("www."):
        raise ValueError("CTA link must start with http:// or https://")

    candidate = _trim_trailing_punctuation(candidate)
    try:
        parsed = _HTTP_URL.validate_python(candidate)
    except ValidationError:
        raise ValueError(f"CTA link is not a valid URL: {candidate[:100]}") from None

    host = (urlsplit(str(parsed)).hostname or "").lower()
    if host not in LOCAL_HOSTNAMES and "." not in host:
        raise ValueError("CTA link must use a public domain name (or localhost for testing)")
    return candidate


def validate_message(raw: object) -> str:
    """Normalise and validate the post body, raising ValueError on bad input."""
    if not isinstance(raw, str):
        raise ValueError("message must be a string")

    message = raw.strip()
    if not message:
        raise ValueError("message must not be empty")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"message must be at most {MAX_MESSAGE_LENGTH} characters (got {len(message)})")
    if any((ord(char) < 32 and char not in "\n\t") or ord(char) == 127 for char in message):
        raise ValueError("message must not contain control characters")

    extract_cta_url(message)
    return message
