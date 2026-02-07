"""Tests for shared DynamoDB utilities."""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError
from shared.dynamodb_utils import (
    delete_connection,
    delete_song,
    get_connection,
    get_song,
    put_connection,
    put_song,
    query_connections_by_user,
    query_songs_by_status,
    query_songs_by_user,
    update_song,
)


def test_put_and_get_song(dynamodb_tables: dict[str, Any]) -> None:
    item = {"userId": "user1", "songId": "song1", "title": "Test Song", "status": "PENDING_UPLOAD"}
    put_song(item)
    result = get_song("user1", "song1")
    assert result is not None
    assert result["title"] == "Test Song"


def test_get_song_not_found(dynamodb_tables: dict[str, Any]) -> None:
    result = get_song("nonexistent", "nonexistent")
    assert result is None


def test_update_song(dynamodb_tables: dict[str, Any]) -> None:
    put_song({"userId": "user1", "songId": "song1", "status": "PENDING_UPLOAD"})
    updated = update_song("user1", "song1", {"status": "PROCESSING"})
    assert updated["status"] == "PROCESSING"
    assert "updatedAt" in updated


def test_query_songs_by_user(dynamodb_tables: dict[str, Any]) -> None:
    put_song({"userId": "user1", "songId": "song1", "status": "COMPLETED"})
    put_song({"userId": "user1", "songId": "song2", "status": "PROCESSING"})
    put_song({"userId": "user2", "songId": "song3", "status": "COMPLETED"})
    results = query_songs_by_user("user1")
    assert len(results) == 2


def test_query_songs_by_status(dynamodb_tables: dict[str, Any]) -> None:
    put_song({"userId": "user1", "songId": "song1", "status": "COMPLETED"})
    put_song({"userId": "user1", "songId": "song2", "status": "PROCESSING"})
    results = query_songs_by_status("user1", "COMPLETED")
    assert len(results) == 1
    assert results[0]["songId"] == "song1"


def test_delete_song(dynamodb_tables: dict[str, Any]) -> None:
    put_song({"userId": "user1", "songId": "song1", "status": "COMPLETED"})
    delete_song("user1", "song1")
    assert get_song("user1", "song1") is None


def test_put_and_get_connection(dynamodb_tables: dict[str, Any]) -> None:
    put_connection({"connectionId": "conn1", "userId": "user1", "ttl": 9999999999})
    result = get_connection("conn1")
    assert result is not None
    assert result["userId"] == "user1"


def test_query_connections_by_user(dynamodb_tables: dict[str, Any]) -> None:
    put_connection({"connectionId": "conn1", "userId": "user1", "ttl": 9999999999})
    put_connection({"connectionId": "conn2", "userId": "user1", "ttl": 9999999999})
    results = query_connections_by_user("user1")
    assert len(results) == 2


def test_delete_connection(dynamodb_tables: dict[str, Any]) -> None:
    put_connection({"connectionId": "conn1", "userId": "user1", "ttl": 9999999999})
    delete_connection("conn1")
    assert get_connection("conn1") is None


def test_update_nonexistent_song_raises(dynamodb_tables: dict[str, Any]) -> None:
    """update_song raises when song doesn't exist (prevents upsert)."""
    with pytest.raises(ClientError) as exc_info:
        update_song("no-user", "no-song", {"status": "PROCESSING"})
    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"
