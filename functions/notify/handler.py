"""Send WebSocket notification via SendProgress Lambda."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="notify")

lambda_client = boto3.client("lambda")


@logger.inject_lambda_context(correlation_id_path="songId")
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    user_id: str = event["userId"]
    song_id: str = event["songId"]
    status: str = event.get("status", "COMPLETED")
    error_message: str = event.get("errorMessage", "")

    send_progress_arn = os.environ["SEND_PROGRESS_FUNCTION_ARN"]

    payload: dict[str, Any] = {
        "userId": user_id,
        "message": {
            "type": status,
            "songId": song_id,
        },
    }
    if error_message:
        payload["message"]["message"] = error_message

    logger.info(
        "Sending notification",
        extra={"status": status, "songId": song_id, "userId": user_id},
    )

    lambda_client.invoke(
        FunctionName=send_progress_arn,
        InvocationType="Event",
        Payload=json.dumps(payload),
    )

    logger.info("Notification sent", extra={"songId": song_id, "status": status})
    return {"notified": True, "status": status}
