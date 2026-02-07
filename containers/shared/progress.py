"""Fire-and-forget progress helpers for Fargate containers."""

from __future__ import annotations

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)

lambda_client = boto3.client("lambda")


def send_progress(stage: str, progress: int, message: str) -> None:
    """Send a PROGRESS event to the SendProgress Lambda (async, fire-and-forget)."""
    _invoke(msg_type="PROGRESS", stage=stage, progress=progress, message=message)


def send_failure(error_message: str) -> None:
    """Send a FAILED event to the SendProgress Lambda (async, fire-and-forget)."""
    _invoke(msg_type="FAILED", stage="", progress=0, message=error_message)


def _invoke(msg_type: str, stage: str, progress: int, message: str) -> None:
    user_id = os.environ["USER_ID"]
    song_id = os.environ["SONG_ID"]
    function_arn = os.environ["SEND_PROGRESS_FUNCTION_ARN"]

    payload = {
        "userId": user_id,
        "message": {
            "type": msg_type,
            "songId": song_id,
            "stage": stage,
            "progress": progress,
            "message": message,
        },
    }

    try:
        lambda_client.invoke(
            FunctionName=function_arn,
            InvocationType="Event",
            Payload=json.dumps(payload),
        )
    except Exception:
        logger.warning("Failed to send %s event for song=%s", msg_type, song_id, exc_info=True)
