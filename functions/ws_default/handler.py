"""WebSocket $default — handle unrecognized routes (ping/pong)."""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.websocket import ws_response

logger = logging.getLogger(__name__)


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    connection_id = event["requestContext"]["connectionId"]
    body_raw = event.get("body") or ""

    logger.info("WebSocket $default: connectionId=%s", connection_id)

    try:
        body = json.loads(body_raw) if body_raw else {}
    except json.JSONDecodeError:
        body = {}

    action = body.get("action", "")

    if action == "ping":
        return ws_response({"action": "pong"})

    return ws_response({"action": "unknown", "message": "Unrecognized action"})
