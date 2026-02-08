"""Tests for failure_handler — marks song FAILED, cleans up outputs, notifies user."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import patch

import boto3


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


def test_marks_failed_cleans_outputs_notifies(
    dynamodb_tables: dict[str, Any],
    s3_buckets: dict[str, Any],
    lambda_context: Any,
) -> None:
    """Full failure path: DynamoDB update + S3 cleanup + notification."""
    table = dynamodb_tables["songs_table"]
    _seed_song(table)

    # Put partial output objects
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(
        Bucket=s3_buckets["output"], Key="output/user-123/song-abc/drums.wav", Body=b"audio"
    )
    s3.put_object(
        Bucket=s3_buckets["output"], Key="output/user-123/song-abc/bass.wav", Body=b"audio"
    )

    with patch.dict(
        os.environ,
        {"SEND_PROGRESS_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456:function:send-progress"},
    ):
        from functions.failure_handler.handler import lambda_handler

        with patch("functions.failure_handler.handler.lambda_client") as mock_lambda:
            result = lambda_handler(
                {
                    "userId": "user-123",
                    "songId": "song-abc",
                    "error": {
                        "Error": "States.TaskFailed",
                        "Cause": "Container exited with code 1",
                    },
                },
                lambda_context,
            )

            assert result["status"] == "FAILED"
            assert result["deletedOutputs"] == 2

            # Verify DynamoDB status
            item = table.get_item(Key={"userId": "user-123", "songId": "song-abc"})["Item"]
            assert item["status"] == "FAILED"
            assert "Container exited with code 1" in item["errorMessage"]

            # Verify S3 outputs cleaned
            response = s3.list_objects_v2(
                Bucket=s3_buckets["output"], Prefix="output/user-123/song-abc/"
            )
            assert response.get("KeyCount", 0) == 0

            # Verify notification sent
            mock_lambda.invoke.assert_called_once()
            payload = json.loads(mock_lambda.invoke.call_args[1]["Payload"])
            assert payload["message"]["type"] == "FAILED"


def test_string_error_format(
    dynamodb_tables: dict[str, Any],
    s3_buckets: dict[str, Any],
    lambda_context: Any,
) -> None:
    """Plain string error (not dict) is stored as errorMessage."""
    table = dynamodb_tables["songs_table"]
    _seed_song(table)

    with patch.dict(
        os.environ,
        {"SEND_PROGRESS_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456:function:send-progress"},
    ):
        from functions.failure_handler.handler import lambda_handler

        with patch("functions.failure_handler.handler.lambda_client"):
            lambda_handler(
                {"userId": "user-123", "songId": "song-abc", "error": "Something went wrong"},
                lambda_context,
            )

    item = table.get_item(Key={"userId": "user-123", "songId": "song-abc"})["Item"]
    assert item["errorMessage"] == "Something went wrong"


def test_notification_failure_does_not_raise(
    dynamodb_tables: dict[str, Any],
    s3_buckets: dict[str, Any],
    lambda_context: Any,
) -> None:
    """Handler still completes even if notification invoke fails."""
    table = dynamodb_tables["songs_table"]
    _seed_song(table)

    with patch.dict(
        os.environ,
        {"SEND_PROGRESS_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456:function:send-progress"},
    ):
        from functions.failure_handler.handler import lambda_handler

        with patch("functions.failure_handler.handler.lambda_client") as mock_lambda:
            mock_lambda.invoke.side_effect = Exception("Lambda unavailable")

            result = lambda_handler(
                {
                    "userId": "user-123",
                    "songId": "song-abc",
                    "error": {"Error": "Timeout", "Cause": "Task timed out"},
                },
                lambda_context,
            )

            # Should still return success (failure handling completed)
            assert result["status"] == "FAILED"

            # DynamoDB should still be updated
            item = table.get_item(Key={"userId": "user-123", "songId": "song-abc"})["Item"]
            assert item["status"] == "FAILED"
