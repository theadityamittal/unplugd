"""Tests for ws_connect handler — WebSocket $connect authentication."""

from __future__ import annotations

import time
from typing import Any

from tests.conftest import CognitoJwtKeys


def _make_ws_connect_event(
    connection_id: str = "conn-123",
    token: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "requestContext": {
            "routeKey": "$connect",
            "connectionId": connection_id,
            "eventType": "CONNECT",
        },
    }
    if token is not None:
        event["queryStringParameters"] = {"token": token}
    else:
        event["queryStringParameters"] = None
    return event


def test_connect_happy_path(
    dynamodb_tables: dict[str, Any],
    cognito_jwt_keys: CognitoJwtKeys,
) -> None:
    """Valid token -> 200, connection stored in DDB with correct userId."""
    from functions.ws_connect.handler import lambda_handler

    token = cognito_jwt_keys.sign_token({"sub": "user-abc"})
    event = _make_ws_connect_event(connection_id="conn-happy", token=token)

    response = lambda_handler(event, None)

    assert response["statusCode"] == 200

    # Verify connection in DDB
    result = dynamodb_tables["connections_table"].get_item(Key={"connectionId": "conn-happy"})
    item = result["Item"]
    assert item["userId"] == "user-abc"
    assert "connectedAt" in item
    assert "ttl" in item


def test_connect_missing_token(dynamodb_tables: dict[str, Any]) -> None:
    """No token in query params -> 401, no connection stored."""
    from functions.ws_connect.handler import lambda_handler

    event = _make_ws_connect_event(connection_id="conn-notoken")

    response = lambda_handler(event, None)

    assert response["statusCode"] == 401

    # Verify no connection in DDB
    result = dynamodb_tables["connections_table"].get_item(Key={"connectionId": "conn-notoken"})
    assert "Item" not in result


def test_connect_invalid_token(
    dynamodb_tables: dict[str, Any],
    cognito_jwt_keys: CognitoJwtKeys,
) -> None:
    """Invalid JWT -> 401."""
    from functions.ws_connect.handler import lambda_handler

    event = _make_ws_connect_event(connection_id="conn-bad", token="not.a.jwt")

    response = lambda_handler(event, None)

    assert response["statusCode"] == 401


def test_connect_stores_ttl(
    dynamodb_tables: dict[str, Any],
    cognito_jwt_keys: CognitoJwtKeys,
) -> None:
    """TTL is approximately now + 7200 seconds."""
    from functions.ws_connect.handler import lambda_handler

    token = cognito_jwt_keys.sign_token()
    event = _make_ws_connect_event(connection_id="conn-ttl", token=token)

    before = int(time.time())
    lambda_handler(event, None)
    after = int(time.time())

    result = dynamodb_tables["connections_table"].get_item(Key={"connectionId": "conn-ttl"})
    ttl = int(result["Item"]["ttl"])
    assert before + 7200 <= ttl <= after + 7200


def test_connect_stores_connected_at(
    dynamodb_tables: dict[str, Any],
    cognito_jwt_keys: CognitoJwtKeys,
) -> None:
    """connectedAt is an ISO 8601 timestamp."""
    from functions.ws_connect.handler import lambda_handler

    token = cognito_jwt_keys.sign_token()
    event = _make_ws_connect_event(connection_id="conn-ts", token=token)

    lambda_handler(event, None)

    result = dynamodb_tables["connections_table"].get_item(Key={"connectionId": "conn-ts"})
    connected_at = result["Item"]["connectedAt"]
    # ISO 8601 format includes T separator and timezone info
    assert "T" in connected_at
