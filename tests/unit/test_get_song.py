"""Tests for get_song handler — GET /songs/{songId}."""

from __future__ import annotations

import json
from typing import Any


def _make_event(
    user_id: str = "user-123",
    song_id: str = "song-001",
) -> dict[str, Any]:
    return {
        "httpMethod": "GET",
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


def test_completed_song_includes_urls(
    dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]
) -> None:
    from functions.get_song.handler import lambda_handler

    _seed_song(dynamodb_tables["songs_table"], status="COMPLETED")

    response = lambda_handler(_make_event(), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "stemUrls" in body
    assert "lyricsUrl" in body
    assert set(body["stemUrls"].keys()) == {"drums", "bass", "other", "vocals"}


def test_non_completed_song_no_urls(dynamodb_tables: dict[str, Any]) -> None:
    from functions.get_song.handler import lambda_handler

    _seed_song(dynamodb_tables["songs_table"], status="PROCESSING")

    response = lambda_handler(_make_event(), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "stemUrls" not in body
    assert "lyricsUrl" not in body


def test_not_found_returns_404(dynamodb_tables: dict[str, Any]) -> None:
    from functions.get_song.handler import lambda_handler

    response = lambda_handler(_make_event(song_id="nonexistent"), None)

    assert response["statusCode"] == 404


def test_different_user_cannot_access(dynamodb_tables: dict[str, Any]) -> None:
    from functions.get_song.handler import lambda_handler

    _seed_song(dynamodb_tables["songs_table"], user_id="user-123", song_id="song-001")

    response = lambda_handler(_make_event(user_id="user-456", song_id="song-001"), None)

    assert response["statusCode"] == 404


def test_missing_path_params(dynamodb_tables: dict[str, Any]) -> None:
    from functions.get_song.handler import lambda_handler

    event: dict[str, Any] = {
        "httpMethod": "GET",
        "requestContext": {"authorizer": {"claims": {"sub": "user-123"}}},
        "pathParameters": None,
    }

    response = lambda_handler(event, None)

    # pathParameters is None → TypeError caught by @handle_errors → 500
    assert response["statusCode"] == 500
