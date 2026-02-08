"""Tests for completion handler — marks song as COMPLETED in DynamoDB."""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError


def _seed_song(
    table: Any,
    user_id: str = "user-123",
    song_id: str = "song-abc",
    status: str = "PROCESSING",
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


def test_marks_song_completed(dynamodb_tables: dict[str, Any], lambda_context: Any) -> None:
    """Handler updates DynamoDB status to COMPLETED and returns confirmation."""
    from functions.completion.handler import lambda_handler

    table = dynamodb_tables["songs_table"]
    _seed_song(table)

    result = lambda_handler({"userId": "user-123", "songId": "song-abc"}, lambda_context)

    assert result["status"] == "COMPLETED"
    assert result["songId"] == "song-abc"

    # Verify DynamoDB was updated
    item = table.get_item(Key={"userId": "user-123", "songId": "song-abc"})["Item"]
    assert item["status"] == "COMPLETED"


def test_song_not_found_raises(dynamodb_tables: dict[str, Any], lambda_context: Any) -> None:
    """update_song raises ConditionalCheckFailedException for missing records."""
    from functions.completion.handler import lambda_handler

    with pytest.raises(ClientError) as exc_info:
        lambda_handler({"userId": "user-123", "songId": "nonexistent"}, lambda_context)

    assert exc_info.value.response["Error"]["Code"] == "ConditionalCheckFailedException"
