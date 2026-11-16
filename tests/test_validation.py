"""Validation rules for the 200-character, single-CTA-link message."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import PostingRequest
from app.services.validation import (
    MAX_MESSAGE_LENGTH,
    extract_cta_url,
    find_urls,
    validate_message,
)

VALID = "Check out our latest business platform and grow your online visibility. https://example.com"


def test_valid_message_is_stripped() -> None:
    assert validate_message(f"  {VALID}\n") == VALID


@pytest.mark.parametrize(
    ("message", "expected_error"),
    [
        ("", "must not be empty"),
        ("   \n\t ", "must not be empty"),
        ("No link in this message", r"exactly one CTA link \(found 0\)"),
        (
            "Two links https://a.example.com and https://b.example.com",
            r"exactly one CTA link \(found 2\)",
        ),
        ("Same link twice https://example.com https://example.com", r"found 2"),
        ("Bare domain www.example.com", "must start with http"),
        ("No dot https://example", "public domain name"),
        ("Unsupported scheme ftp://example.com", r"exactly one CTA link \(found 0\)"),
        ("Null byte\x00 https://example.com", "control characters"),
    ],
)
def test_invalid_messages_are_rejected(message: str, expected_error: str) -> None:
    with pytest.raises(ValueError, match=expected_error):
        validate_message(message)


def test_message_must_be_a_string() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        validate_message(123)  # type: ignore[arg-type]


def test_exact_length_boundary() -> None:
    suffix = " https://example.com"
    message = "a" * (MAX_MESSAGE_LENGTH - len(suffix)) + suffix
    assert len(message) == MAX_MESSAGE_LENGTH
    assert validate_message(message) == message

    with pytest.raises(ValueError, match="at most 200"):
        validate_message("a" + message)


@pytest.mark.parametrize(
    ("message", "expected_url"),
    [
        ("Read more at https://example.com.", "https://example.com"),
        ("Read more at (https://example.com)", "https://example.com"),
        (
            "See https://en.wikipedia.org/wiki/Foo_(bar) for context",
            "https://en.wikipedia.org/wiki/Foo_(bar)",
        ),
        (
            "Path https://example.com/path?q=1#frag",
            "https://example.com/path?q=1#frag",
        ),
    ],
)
def test_cta_link_extraction(message: str, expected_url: str) -> None:
    assert extract_cta_url(message) == expected_url


def test_https_www_link_is_counted_once() -> None:
    assert len(find_urls("Visit https://www.example.com now")) == 1


def test_posting_request_exposes_cta_url() -> None:
    request = PostingRequest(message=VALID)
    assert request.message == VALID
    assert request.cta_url == "https://example.com"


def test_posting_request_wraps_validation_errors() -> None:
    with pytest.raises(ValidationError, match="at most 200"):
        PostingRequest(message="a" * 181 + " https://example.com")
