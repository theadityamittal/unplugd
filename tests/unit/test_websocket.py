"""Tests for shared.websocket — WebSocket response helpers and send_to_connection."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from shared.websocket import (
    send_to_connection,
    ws_error,
    ws_response,
    ws_success,
    ws_unauthorized,
)


def test_ws_success() -> None:
    """ws_success returns statusCode 200."""
    result = ws_success()
    assert result == {"statusCode": 200}


def test_ws_unauthorized() -> None:
    """ws_unauthorized returns statusCode 401."""
    result = ws_unauthorized()
    assert result == {"statusCode": 401}


def test_ws_response() -> None:
    """ws_response returns statusCode 200 with JSON body."""
    result = ws_response({"action": "pong"})
    assert result["statusCode"] == 200
    assert json.loads(result["body"]) == {"action": "pong"}


def test_ws_error() -> None:
    """ws_error returns statusCode 500 with error message."""
    result = ws_error("something broke")
    assert result["statusCode"] == 500
    assert json.loads(result["body"]) == {"error": "something broke"}


@patch("shared.websocket._management_api_client")
def test_send_to_connection_success(mock_client_fn: MagicMock) -> None:
    """send_to_connection returns True on successful post."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client

    result = send_to_connection("conn-1", {"type": "PROGRESS", "songId": "song-1"})

    assert result is True
    mock_client.post_to_connection.assert_called_once()
    call_kwargs = mock_client.post_to_connection.call_args[1]
    assert call_kwargs["ConnectionId"] == "conn-1"
    data = json.loads(call_kwargs["Data"].decode("utf-8"))
    assert data["type"] == "PROGRESS"
    assert data["songId"] == "song-1"


@patch("shared.websocket._management_api_client")
def test_send_to_connection_gone(mock_client_fn: MagicMock) -> None:
    """send_to_connection returns False when connection is gone (410)."""
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.post_to_connection.side_effect = ClientError(
        {"Error": {"Code": "GoneException", "Message": "Gone"}},
        "PostToConnection",
    )

    result = send_to_connection("conn-gone", {"type": "PROGRESS"})

    assert result is False
