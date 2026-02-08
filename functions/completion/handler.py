"""Mark song as COMPLETED in DynamoDB."""

from __future__ import annotations

from typing import Any

from aws_lambda_powertools import Logger
from shared.constants import STATUS_COMPLETED
from shared.dynamodb_utils import update_song

logger = Logger(service="completion")


@logger.inject_lambda_context(correlation_id_path="songId")
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    user_id: str = event["userId"]
    song_id: str = event["songId"]

    logger.info("Marking song as completed", extra={"userId": user_id, "songId": song_id})

    update_song(user_id, song_id, {"status": STATUS_COMPLETED})

    logger.info("Song marked as completed", extra={"songId": song_id})
    return {"status": "COMPLETED", "songId": song_id}
