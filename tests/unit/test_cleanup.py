"""Tests for cleanup handler — deletes original upload files from S3."""

from __future__ import annotations

from typing import Any

import boto3


def test_deletes_upload_objects(s3_buckets: dict[str, Any], lambda_context: Any) -> None:
    """Handler deletes all objects under the upload prefix."""
    from functions.cleanup.handler import lambda_handler

    bucket = s3_buckets["upload"]
    s3 = boto3.client("s3", region_name="us-east-1")

    # Upload 2 files for this song
    s3.put_object(Bucket=bucket, Key="uploads/user-123/song-abc/test.wav", Body=b"audio")
    s3.put_object(Bucket=bucket, Key="uploads/user-123/song-abc/test.wav.tmp", Body=b"tmp")

    result = lambda_handler(
        {"userId": "user-123", "songId": "song-abc", "key": "uploads/user-123/song-abc/test.wav"},
        lambda_context,
    )

    assert result["deletedCount"] == 2

    # Verify objects are gone
    response = s3.list_objects_v2(Bucket=bucket, Prefix="uploads/user-123/song-abc/")
    assert response.get("KeyCount", 0) == 0


def test_no_objects_to_delete(s3_buckets: dict[str, Any], lambda_context: Any) -> None:
    """Handler returns deletedCount=0 when no objects exist."""
    from functions.cleanup.handler import lambda_handler

    result = lambda_handler(
        {
            "userId": "user-123",
            "songId": "nonexistent",
            "key": "uploads/user-123/nonexistent/x.wav",
        },
        lambda_context,
    )

    assert result["deletedCount"] == 0
