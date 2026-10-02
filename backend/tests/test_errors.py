"""Unit tests for the error taxonomy + classification (deterministic, no I/O)."""

from __future__ import annotations

import pytest

from app.core.errors import (
    ErrorCategory,
    KompiloError,
    classify_exception,
    http_status,
    is_retryable,
    user_message,
)
from app.engines.providers.base import ProviderError


def test_every_category_has_a_policy() -> None:
    for cat in ErrorCategory:
        assert user_message(cat)  # a non-empty, user-facing message
        assert 400 <= http_status(cat) <= 599


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("HTTP 429 Too Many Requests", ErrorCategory.RATE_LIMIT),
        ("request timed out after 30s", ErrorCategory.TIMEOUT),
        ("blocked by content policy", ErrorCategory.POLICY),
        ("maximum context length exceeded", ErrorCategory.CONTEXT),
        ("401 Unauthorized: bad api key", ErrorCategory.MODEL),
        ("some totally novel failure", ErrorCategory.MODEL),  # bare ProviderError → MODEL
    ],
)
def test_classify_provider_errors(message: str, expected: ErrorCategory) -> None:
    assert classify_exception(ProviderError(message)) == expected


def test_classify_timeout_and_unknown() -> None:
    assert classify_exception(TimeoutError()) == ErrorCategory.TIMEOUT
    assert classify_exception(ValueError("weird")) == ErrorCategory.UNKNOWN


def test_retryable_flags() -> None:
    assert is_retryable(ErrorCategory.MODEL) is True
    assert is_retryable(ErrorCategory.TIMEOUT) is True
    assert is_retryable(ErrorCategory.RATE_LIMIT) is True
    assert is_retryable(ErrorCategory.POLICY) is False
    assert is_retryable(ErrorCategory.VALIDATION) is False
    assert is_retryable(ErrorCategory.INPUT) is False


def test_kompilo_error_to_http_hides_internals() -> None:
    err = KompiloError(ErrorCategory.POLICY, detail="provider refused: secret=abc123")
    status_code, body = err.to_http()
    assert status_code == 403
    assert body["category"] == "POLICY"
    assert body["retryable"] is False
    # The user-facing body never leaks the internal detail / secrets.
    assert "secret" not in str(body).lower()
    assert body["message"] == user_message(ErrorCategory.POLICY)


def test_classify_passthrough_for_kompilo_error() -> None:
    err = KompiloError(ErrorCategory.RATE_LIMIT, detail="x")
    assert classify_exception(err) == ErrorCategory.RATE_LIMIT
