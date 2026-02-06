"""Tests for ws_disconnect handler — WebSocket $disconnect."""

from __future__ import annotations

from typing import Any

from shared.dynamodb_utils import put_connection


def _make_ws_disconnect_event(connection_id: str = "conn-123") -> dict[str, Any]:
    return {
        "requestContext": {
            "routeKey": "$disconnect",
            "connectionId": connection_id,
            "eventType": "DISCONNECT",
        },
    }


def test_disconnect_happy_path(dynamodb_tables: dict[str, Any]) -> None:
    """Existing connection is deleted from DDB."""
    from functions.ws_disconnect.handler import lambda_handler

    # Pre-create connection
    put_connection({"connectionId": "conn-del", "userId": "user-1", "ttl": 9999999999})

    event = _make_ws_disconnect_event(connection_id="conn-del")
    response = lambda_handler(event, None)

    assert response["statusCode"] == 200

    # Verify connection removed
    result = dynamodb_tables["connections_table"].get_item(Key={"connectionId": "conn-del"})
    assert "Item" not in result


def test_disconnect_nonexistent_connection(dynamodb_tables: dict[str, Any]) -> None:
    """Disconnecting a nonexistent connection still returns 200 (idempotent)."""
    from functions.ws_disconnect.handler import lambda_handler

    event = _make_ws_disconnect_event(connection_id="conn-nonexistent")
    response = lambda_handler(event, None)

    assert response["statusCode"] == 200
