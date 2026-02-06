"""WebSocket response helpers and API Gateway Management API utilities."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError
from shared.constants import WEBSOCKET_API_ENDPOINT

logger = logging.getLogger(__name__)


def ws_success() -> dict[str, Any]:
    """Accept a WebSocket connection (200)."""
    return {"statusCode": 200}


def ws_unauthorized() -> dict[str, Any]:
    """Reject a WebSocket connection (401)."""
    return {"statusCode": 401}


def ws_error(message: str = "Internal server error") -> dict[str, Any]:
    """Return error to $default route."""
    return {"statusCode": 500, "body": json.dumps({"error": message})}


def ws_response(body: dict[str, Any]) -> dict[str, Any]:
    """Return a message body to $default route."""
    return {"statusCode": 200, "body": json.dumps(body)}


def _management_api_client() -> Any:
    """Create API Gateway Management API client."""
    return boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=WEBSOCKET_API_ENDPOINT,
    )


def send_to_connection(connection_id: str, message: dict[str, Any]) -> bool:
    """Post a message to a WebSocket connection. Returns False if connection is gone."""
    try:
        _management_api_client().post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message, default=str).encode("utf-8"),
        )
        return True
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code in ("GoneException", "410"):
            logger.info("Connection gone: connectionId=%s", connection_id)
            return False
        raise
