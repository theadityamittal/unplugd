"""Tests for send_progress handler — push progress to WebSocket connections."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

from shared.dynamodb_utils import get_connection, put_connection


def _make_progress_event(
    user_id: str = "user-123",
    message: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {}
    if user_id:
        event["userId"] = user_id
    if message is not None:
        event["message"] = message
    return event


@patch("functions.send_progress.handler.send_to_connection")
def test_happy_path(
    mock_send: Any,
    dynamodb_tables: dict[str, Any],
) -> None:
    """Progress sent to all active connections for a user."""
    from functions.send_progress.handler import lambda_handler

    mock_send.return_value = True

    # Create 2 connections for the user
    put_connection({"connectionId": "conn-1", "userId": "user-123", "ttl": 9999999999})
    put_connection({"connectionId": "conn-2", "userId": "user-123", "ttl": 9999999999})

    message = {"type": "PROGRESS", "songId": "song-1", "progress": 50}
    event = _make_progress_event(message=message)

    lambda_handler(event, None)

    assert mock_send.call_count == 2
    # Verify both connections received the message
    call_args = [call[0] for call in mock_send.call_args_list]
    connection_ids = {args[0] for args in call_args}
    assert connection_ids == {"conn-1", "conn-2"}
    for args in call_args:
        assert args[1] == message


@patch("functions.send_progress.handler.send_to_connection")
def test_no_connections_logs_warning(
    mock_send: Any,
    dynamodb_tables: dict[str, Any],
    caplog: Any,
) -> None:
    """Zero connections logs a warning and does not call send_to_connection."""
    from functions.send_progress.handler import lambda_handler

    message = {"type": "PROGRESS", "songId": "song-1"}
    event = _make_progress_event(user_id="user-no-conns", message=message)

    with caplog.at_level(logging.WARNING):
        lambda_handler(event, None)

    mock_send.assert_not_called()
    assert any("No active connections" in record.message for record in caplog.records)


@patch("functions.send_progress.handler.send_to_connection")
def test_stale_connection_cleanup(
    mock_send: Any,
    dynamodb_tables: dict[str, Any],
) -> None:
    """Stale connection (GoneException) is deleted from DDB."""
    from functions.send_progress.handler import lambda_handler

    # conn-stale returns False (gone), conn-alive returns True
    mock_send.side_effect = lambda conn_id, _msg: conn_id != "conn-stale"

    put_connection({"connectionId": "conn-stale", "userId": "user-123", "ttl": 9999999999})
    put_connection({"connectionId": "conn-alive", "userId": "user-123", "ttl": 9999999999})

    message = {"type": "COMPLETED", "songId": "song-1"}
    event = _make_progress_event(message=message)

    lambda_handler(event, None)

    # Stale connection should be deleted
    assert get_connection("conn-stale") is None
    # Alive connection should remain
    assert get_connection("conn-alive") is not None


def test_missing_user_id() -> None:
    """Missing userId in event returns None without crashing."""
    from functions.send_progress.handler import lambda_handler

    event: dict[str, Any] = {"message": {"type": "PROGRESS"}}

    result = lambda_handler(event, None)

    assert result is None
