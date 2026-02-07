"""Standard API Gateway response formatting."""

from __future__ import annotations

import json
from typing import Any

from shared.constants import CORS_ORIGIN


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": CORS_ORIGIN,
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }


def success(body: dict[str, Any] | list[Any] | None = None) -> dict[str, Any]:
    """200 OK."""
    return _response(200, body if isinstance(body, dict) else {"data": body})


def created(body: dict[str, Any]) -> dict[str, Any]:
    """201 Created."""
    return _response(201, body)


def bad_request(message: str) -> dict[str, Any]:
    """400 Bad Request."""
    return _response(400, {"error": "BadRequest", "message": message})


def not_found(message: str = "Resource not found") -> dict[str, Any]:
    """404 Not Found."""
    return _response(404, {"error": "NotFound", "message": message})


def internal_error(message: str = "Internal server error") -> dict[str, Any]:
    """500 Internal Server Error."""
    return _response(500, {"error": "InternalError", "message": message})
