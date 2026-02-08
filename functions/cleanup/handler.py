"""Clean up original upload files from S3."""

from __future__ import annotations

from typing import Any

from aws_lambda_powertools import Logger
from shared.constants import UPLOAD_BUCKET_NAME
from shared.s3_utils import delete_objects_by_prefix

logger = Logger(service="cleanup")


@logger.inject_lambda_context(correlation_id_path="songId")
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    user_id: str = event["userId"]
    song_id: str = event["songId"]

    prefix = f"uploads/{user_id}/{song_id}/"
    logger.info(
        "Cleaning up original uploads", extra={"bucket": UPLOAD_BUCKET_NAME, "prefix": prefix}
    )

    deleted_count = delete_objects_by_prefix(UPLOAD_BUCKET_NAME, prefix)

    logger.info("Cleanup complete", extra={"deletedCount": deleted_count, "songId": song_id})
    return {"deletedCount": deleted_count}
