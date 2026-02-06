"""Custom exceptions and error-handling decorator for Lambda handlers."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

from shared.response import bad_request, internal_error, not_found

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ValidationError(AppError):
    """Input validation failure (400)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class NotFoundError(AppError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


HandlerFunc = Callable[..., dict[str, Any]]


def handle_errors(func: HandlerFunc) -> HandlerFunc:
    """Decorator that catches exceptions and returns API Gateway responses."""

    @functools.wraps(func)
    def wrapper(event: dict[str, Any], context: Any) -> dict[str, Any]:
        try:
            return func(event, context)
        except ValidationError as exc:
            logger.warning("Validation error: %s", exc.message)
            return bad_request(exc.message)
        except NotFoundError as exc:
            logger.warning("Not found: %s", exc.message)
            return not_found(exc.message)
        except AppError as exc:
            logger.error("Application error: %s", exc.message)
            return internal_error(exc.message)
        except Exception:
            logger.exception("Unhandled exception")
            return internal_error("An unexpected error occurred")

    return wrapper  # type: ignore[return-value]
