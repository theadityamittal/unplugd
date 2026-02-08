"""Handle pipeline failure: update DynamoDB, clean up partial outputs, notify user."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from shared.constants import OUTPUT_BUCKET_NAME, STATUS_FAILED
from shared.dynamodb_utils import update_song
from shared.s3_utils import delete_objects_by_prefix

logger = Logger(service="failure_handler")

lambda_client = boto3.client("lambda")


@logger.inject_lambda_context(correlation_id_path="songId")
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    user_id: str = event["userId"]
    song_id: str = event["songId"]
    error: dict[str, Any] | str = event.get("error", {})

    # Extract error message from Step Functions Catch block or plain string
    if isinstance(error, dict):
        error_message = error.get("Cause", error.get("Error", "Unknown error"))
    else:
        error_message = str(error)

    logger.error(
        "Processing pipeline failed",
        extra={"userId": user_id, "songId": song_id, "error": error_message},
    )

    # 1. Mark song as FAILED in DynamoDB
    update_song(user_id, song_id, {"status": STATUS_FAILED, "errorMessage": error_message})
    logger.info("Song marked as FAILED", extra={"songId": song_id})

    # 2. Clean up partial S3 outputs
    output_prefix = f"output/{user_id}/{song_id}/"
    deleted_count = delete_objects_by_prefix(OUTPUT_BUCKET_NAME, output_prefix)
    logger.info(
        "Cleaned up partial outputs", extra={"deletedCount": deleted_count, "prefix": output_prefix}
    )

    # 3. Send failure notification (best-effort — must not raise)
    send_progress_arn = os.environ["SEND_PROGRESS_FUNCTION_ARN"]
    notify_payload = {
        "userId": user_id,
        "message": {
            "type": "FAILED",
            "songId": song_id,
            "message": error_message,
        },
    }

    try:
        lambda_client.invoke(
            FunctionName=send_progress_arn,
            InvocationType="Event",
            Payload=json.dumps(notify_payload),
        )
        logger.info("Failure notification sent", extra={"songId": song_id})
    except Exception:
        logger.warning("Failed to send failure notification", exc_info=True)

    return {"status": "FAILED", "songId": song_id, "deletedOutputs": deleted_count}
