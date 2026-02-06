"""Tests for upload_request handler."""

from __future__ import annotations

import json
from typing import Any


def _make_event(body: dict[str, Any] | None = None, user_id: str = "user-123") -> dict[str, Any]:
    return {
        "httpMethod": "POST",
        "path": "/songs/upload-url",
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": user_id,
                    "email": "test@example.com",
                },
            },
        },
        "body": json.dumps(body) if body else None,
    }


def test_happy_path(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    from functions.upload_request.handler import lambda_handler

    event = _make_event({"filename": "my-song.mp3", "contentType": "audio/mpeg"})

    response = lambda_handler(event, None)

    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert "songId" in body
    assert "uploadUrl" in body
    assert body["expiresIn"] == 900

    # Verify DDB item was created
    songs_table = dynamodb_tables["songs_table"]
    result = songs_table.get_item(Key={"userId": "user-123", "songId": body["songId"]})
    item = result["Item"]
    assert item["status"] == "PENDING_UPLOAD"
    assert item["title"] == "my-song.mp3"
    assert item["contentType"] == "audio/mpeg"
    assert "uploads/user-123/" in item["s3Key"]


def test_missing_filename(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    from functions.upload_request.handler import lambda_handler

    event = _make_event({"contentType": "audio/mpeg"})

    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "filename" in body["message"].lower()


def test_missing_body(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    from functions.upload_request.handler import lambda_handler

    event = _make_event(None)

    response = lambda_handler(event, None)

    assert response["statusCode"] == 400


def test_invalid_content_type(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    from functions.upload_request.handler import lambda_handler

    event = _make_event({"filename": "song.txt", "contentType": "text/plain"})

    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "contentType" in body["message"]


def test_missing_content_type(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    from functions.upload_request.handler import lambda_handler

    event = _make_event({"filename": "song.mp3"})

    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "contentType" in body["message"]


def test_song_id_is_unique(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    from functions.upload_request.handler import lambda_handler

    event = _make_event({"filename": "song.mp3", "contentType": "audio/mpeg"})

    r1 = lambda_handler(event, None)
    r2 = lambda_handler(event, None)

    body1 = json.loads(r1["body"])
    body2 = json.loads(r2["body"])
    assert body1["songId"] != body2["songId"]


def test_sanitize_filename_strips_path_traversal() -> None:
    from functions.upload_request.handler import _sanitize_filename

    assert _sanitize_filename("../../../etc/passwd") == "passwd"
    assert _sanitize_filename("path/to/song.mp3") == "song.mp3"
    assert _sanitize_filename("path\\to\\song.mp3") == "song.mp3"


def test_sanitize_filename_replaces_special_chars() -> None:
    from functions.upload_request.handler import _sanitize_filename

    result = _sanitize_filename("my song (remix) [v2].mp3")
    assert ".." not in result
    assert "/" not in result
    assert "\\" not in result


def test_sanitize_filename_empty_fallback() -> None:
    from functions.upload_request.handler import _sanitize_filename

    assert _sanitize_filename("...") == "upload"
    assert _sanitize_filename("") == "upload"


def test_filename_sanitized_in_s3_key(
    dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]
) -> None:
    """Path traversal in filename should not appear in the S3 key."""
    from functions.upload_request.handler import lambda_handler

    event = _make_event({"filename": "../../evil.mp3", "contentType": "audio/mpeg"})

    response = lambda_handler(event, None)

    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    songs_table = dynamodb_tables["songs_table"]
    result = songs_table.get_item(Key={"userId": "user-123", "songId": body["songId"]})
    s3_key = result["Item"]["s3Key"]
    assert ".." not in s3_key
    assert "evil.mp3" in s3_key
