"""WebSocket $disconnect — remove connection from ConnectionsTable."""

from __future__ import annotations

import logging
from typing import Any

from shared.dynamodb_utils import delete_connection
from shared.websocket import ws_success

logger = logging.getLogger(__name__)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    connection_id = event["requestContext"]["connectionId"]
    logger.info("WebSocket $disconnect: connectionId=%s", connection_id)

    delete_connection(connection_id)

    return ws_success()
