"""GET /songs — list songs for the authenticated user."""

from __future__ import annotations

import logging
from typing import Any

from shared.constants import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING_UPLOAD,
    STATUS_PROCESSING,
)
from shared.dynamodb_utils import query_songs_by_status, query_songs_by_user
from shared.error_handling import ValidationError, handle_errors
from shared.response import success

logger = logging.getLogger(__name__)

_VALID_STATUSES = frozenset(
    {STATUS_PENDING_UPLOAD, STATUS_PROCESSING, STATUS_COMPLETED, STATUS_FAILED}
)


@handle_errors
def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    user_id: str = event["requestContext"]["authorizer"]["claims"]["sub"]
    logger.info("List songs request from userId=%s", user_id)

    query_params = event.get("queryStringParameters") or {}
    status = query_params.get("status")

    if status is not None:
        if status not in _VALID_STATUSES:
            raise ValidationError(
                f"Invalid status '{status}'. Must be one of: {', '.join(sorted(_VALID_STATUSES))}"
            )
        songs = query_songs_by_status(user_id, status)
    else:
        songs = query_songs_by_user(user_id)

    logger.info("Returning %d songs for userId=%s", len(songs), user_id)
    return success(songs)
