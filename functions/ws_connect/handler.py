"""WebSocket $connect — authenticate and store connection."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from shared.constants import CONNECTION_TTL_SECONDS
from shared.dynamodb_utils import put_connection
from shared.jwt_utils import validate_cognito_token
from shared.websocket import ws_success, ws_unauthorized

logger = logging.getLogger(__name__)


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    connection_id = event["requestContext"]["connectionId"]
    logger.info("WebSocket $connect: connectionId=%s", connection_id)

    # Extract token from query string
    query_params = event.get("queryStringParameters") or {}
    token = query_params.get("token")

    if not token:
        logger.warning("No token provided for connectionId=%s", connection_id)
        return ws_unauthorized()

    # Validate Cognito JWT
    claims = validate_cognito_token(token)
    if claims is None:
        logger.warning("Invalid token for connectionId=%s", connection_id)
        return ws_unauthorized()

    user_id = claims.get("sub")
    if not user_id:
        logger.warning("Token missing 'sub' claim: connectionId=%s", connection_id)
        return ws_unauthorized()
    logger.info("Authenticated userId=%s connectionId=%s", user_id, connection_id)

    # Store connection
    put_connection(
        {
            "connectionId": connection_id,
            "userId": user_id,
            "connectedAt": datetime.now(UTC).isoformat(),
            "ttl": int(time.time()) + CONNECTION_TTL_SECONDS,
        }
    )

    return ws_success()
