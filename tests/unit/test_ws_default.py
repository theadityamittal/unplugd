"""Tests for ws_default handler — WebSocket $default route (ping/pong)."""

from __future__ import annotations

import json
from typing import Any


def _make_ws_default_event(
    connection_id: str = "conn-123",
    body: str | None = None,
) -> dict[str, Any]:
    return {
        "requestContext": {
            "routeKey": "$default",
            "connectionId": connection_id,
            "eventType": "MESSAGE",
        },
        "body": body,
    }


def test_ping_pong() -> None:
    """action=ping returns action=pong."""
    from functions.ws_default.handler import lambda_handler

    event = _make_ws_default_event(body=json.dumps({"action": "ping"}))
    response = lambda_handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["action"] == "pong"


def test_unknown_action() -> None:
    """Unrecognized action returns 'unknown'."""
    from functions.ws_default.handler import lambda_handler

    event = _make_ws_default_event(body=json.dumps({"action": "foo"}))
    response = lambda_handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["action"] == "unknown"


def test_empty_body() -> None:
    """Empty/null body is handled gracefully."""
    from functions.ws_default.handler import lambda_handler

    event = _make_ws_default_event(body=None)
    response = lambda_handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["action"] == "unknown"
