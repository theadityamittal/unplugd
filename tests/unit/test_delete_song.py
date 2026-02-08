"""Tests for delete_song handler — DELETE /songs/{songId}."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch


def _make_event(
    user_id: str = "user-123",
    song_id: str = "song-001",
) -> dict[str, Any]:
    return {
        "httpMethod": "DELETE",
        "path": f"/songs/{song_id}",
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": user_id,
                },
            },
        },
        "pathParameters": {"songId": song_id},
    }


def _seed_song(
    table: Any,
    user_id: str = "user-123",
    song_id: str = "song-001",
    status: str = "COMPLETED",
) -> None:
    table.put_item(
        Item={
            "userId": user_id,
            "songId": song_id,
            "status": status,
            "title": "Test Song",
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-01T00:00:00+00:00",
        }
    )


@patch("functions.delete_song.handler.delete_objects_by_prefix")
def test_happy_path_deletes_record(
    mock_delete_prefix: Any,
    dynamodb_tables: dict[str, Any],
) -> None:
    from functions.delete_song.handler import lambda_handler

    table = dynamodb_tables["songs_table"]
    _seed_song(table)

    response = lambda_handler(_make_event(), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["deleted"] is True

    # Verify DDB record is gone
    result = table.get_item(Key={"userId": "user-123", "songId": "song-001"})
    assert "Item" not in result


@patch("functions.delete_song.handler.delete_objects_by_prefix")
def test_s3_cleanup_called(
    mock_delete_prefix: Any,
    dynamodb_tables: dict[str, Any],
) -> None:
    from functions.delete_song.handler import lambda_handler

    _seed_song(dynamodb_tables["songs_table"])

    lambda_handler(_make_event(), None)

    # Should be called twice: output bucket + upload bucket
    assert mock_delete_prefix.call_count == 2
    call_args_list = [call[0] for call in mock_delete_prefix.call_args_list]
    prefixes = {args[1] for args in call_args_list}
    assert "output/user-123/song-001/" in prefixes
    assert "uploads/user-123/song-001/" in prefixes


def test_not_found_returns_404(dynamodb_tables: dict[str, Any]) -> None:
    from functions.delete_song.handler import lambda_handler

    response = lambda_handler(_make_event(song_id="nonexistent"), None)

    assert response["statusCode"] == 404


def test_different_user_cannot_delete(dynamodb_tables: dict[str, Any]) -> None:
    from functions.delete_song.handler import lambda_handler

    table = dynamodb_tables["songs_table"]
    _seed_song(table, user_id="user-123", song_id="song-001")

    response = lambda_handler(_make_event(user_id="user-456", song_id="song-001"), None)

    assert response["statusCode"] == 404
    # Original record should still exist
    result = table.get_item(Key={"userId": "user-123", "songId": "song-001"})
    assert "Item" in result
