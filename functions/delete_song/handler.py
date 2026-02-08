"""DELETE /songs/{songId} — delete a song and all associated S3 objects."""

from __future__ import annotations

import logging
from typing import Any

from shared.constants import OUTPUT_BUCKET_NAME, UPLOAD_BUCKET_NAME
from shared.dynamodb_utils import delete_song, get_song
from shared.error_handling import NotFoundError, handle_errors
from shared.response import success
from shared.s3_utils import delete_objects_by_prefix

logger = logging.getLogger(__name__)


@handle_errors
def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    user_id: str = event["requestContext"]["authorizer"]["claims"]["sub"]
    song_id: str = event["pathParameters"]["songId"]
    logger.info("Delete song request: userId=%s songId=%s", user_id, song_id)

    song = get_song(user_id, song_id)
    if song is None:
        raise NotFoundError(f"Song '{song_id}' not found")

    # Delete output objects (stems + lyrics)
    output_prefix = f"output/{user_id}/{song_id}/"
    deleted_output = delete_objects_by_prefix(OUTPUT_BUCKET_NAME, output_prefix)
    logger.info("Deleted %d output objects for songId=%s", deleted_output, song_id)

    # Delete upload objects (may already be cleaned up by lifecycle policy)
    upload_prefix = f"uploads/{user_id}/{song_id}/"
    deleted_upload = delete_objects_by_prefix(UPLOAD_BUCKET_NAME, upload_prefix)
    logger.info("Deleted %d upload objects for songId=%s", deleted_upload, song_id)

    # Delete DynamoDB record
    delete_song(user_id, song_id)

    logger.info("Deleted song: userId=%s songId=%s", user_id, song_id)
    return success({"deleted": True})
