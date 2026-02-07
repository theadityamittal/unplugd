"""Send progress message to all of a user's WebSocket connections."""

from __future__ import annotations

import logging
from typing import Any

from shared.dynamodb_utils import delete_connection, query_connections_by_user
from shared.websocket import send_to_connection

logger = logging.getLogger(__name__)


def lambda_handler(event: dict[str, Any], _context: Any) -> None:
    """Invoked asynchronously by Fargate containers or Step Functions.

    Expected event payload:
    {
        "userId": "...",
        "message": {
            "type": "PROGRESS",
            "songId": "...",
            "stage": "demucs",
            "progress": 50,
            "message": "Separating stems..."
        }
    }
    """
    user_id = event.get("userId")
    message = event.get("message")

    if not user_id or not isinstance(message, dict) or not message:
        logger.error("Missing userId or invalid message in event: %s", event)
        return

    logger.info(
        "Sending progress: userId=%s type=%s songId=%s",
        user_id,
        message.get("type"),
        message.get("songId"),
    )

    connections = query_connections_by_user(user_id)
    if not connections:
        logger.warning("No active connections for userId=%s", user_id)
        return

    for conn in connections:
        connection_id = conn["connectionId"]
        try:
            delivered = send_to_connection(connection_id, message)
            if not delivered:
                logger.info("Removing stale connection: connectionId=%s", connection_id)
                delete_connection(connection_id)
        except Exception:
            logger.exception("Error sending to connectionId=%s — removing", connection_id)
            delete_connection(connection_id)

    logger.info("Progress sent to %d connections for userId=%s", len(connections), user_id)
