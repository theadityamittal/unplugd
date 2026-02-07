"""POST /songs/upload-url — return a presigned S3 PUT URL."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from shared.constants import (
    ALLOWED_CONTENT_TYPES,
    PRESIGNED_URL_EXPIRATION,
    STATUS_PENDING_UPLOAD,
    UPLOAD_KEY_PREFIX,
)
from shared.dynamodb_utils import put_song
from shared.error_handling import ValidationError, handle_errors
from shared.response import created
from shared.s3_utils import generate_presigned_upload_url
from ulid import ULID

logger = logging.getLogger(__name__)


def _sanitize_filename(filename: str) -> str:
    """Strip path components and unsafe characters from a user-provided filename."""
    # Remove any directory components (forward and back slashes)
    basename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # Replace unsafe characters with underscores, keep alphanumeric, dots, hyphens, spaces
    basename = re.sub(r"[^\w\s.\-]", "_", basename)
    # Strip leading/trailing dots and spaces
    basename = basename.strip(". ")
    if not basename:
        basename = "upload"
    return basename


@handle_errors
def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    user_id: str = event["requestContext"]["authorizer"]["claims"]["sub"]
    logger.info("Upload URL request from userId=%s", user_id)

    body = json.loads(event.get("body") or "{}")
    filename: str | None = body.get("filename")
    content_type: str | None = body.get("contentType")

    if not filename:
        raise ValidationError("filename is required")
    if not content_type or content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            f"contentType must be one of: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )

    song_id = str(ULID())
    safe_filename = _sanitize_filename(filename)
    s3_key = f"{UPLOAD_KEY_PREFIX}/{user_id}/{song_id}/{safe_filename}"
    logger.info("Generated songId=%s s3Key=%s", song_id, s3_key)

    upload_url = generate_presigned_upload_url(s3_key, content_type)

    now = datetime.now(UTC).isoformat()
    put_song(
        {
            "userId": user_id,
            "songId": song_id,
            "title": filename,
            "status": STATUS_PENDING_UPLOAD,
            "s3Key": s3_key,
            "contentType": content_type,
            "createdAt": now,
            "updatedAt": now,
        }
    )

    logger.info("Upload URL created: songId=%s userId=%s", song_id, user_id)
    return created(
        {
            "songId": song_id,
            "uploadUrl": upload_url,
            "expiresIn": PRESIGNED_URL_EXPIRATION,
        }
    )
