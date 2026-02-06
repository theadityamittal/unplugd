"""Tests for shared error handling module."""

import json

from shared.error_handling import NotFoundError, ValidationError, handle_errors


def test_handle_errors_passes_through_success() -> None:
    @handle_errors
    def handler(event, context):  # type: ignore[no-untyped-def]
        return {"statusCode": 200, "body": "ok"}

    result = handler({}, None)
    assert result["statusCode"] == 200


def test_handle_errors_catches_validation_error() -> None:
    @handle_errors
    def handler(event, context):  # type: ignore[no-untyped-def]
        raise ValidationError("bad input")

    result = handler({}, None)
    assert result["statusCode"] == 400
    assert "bad input" in json.loads(result["body"])["message"]


def test_handle_errors_catches_not_found_error() -> None:
    @handle_errors
    def handler(event, context):  # type: ignore[no-untyped-def]
        raise NotFoundError("song not found")

    result = handler({}, None)
    assert result["statusCode"] == 404
    assert "song not found" in json.loads(result["body"])["message"]


def test_handle_errors_catches_unhandled_exception() -> None:
    @handle_errors
    def handler(event, context):  # type: ignore[no-untyped-def]
        raise RuntimeError("unexpected")

    result = handler({}, None)
    assert result["statusCode"] == 500
