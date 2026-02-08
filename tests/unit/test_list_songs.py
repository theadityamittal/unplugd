"""Tests for list_songs handler — GET /songs."""

from __future__ import annotations

import json
from typing import Any


def _make_event(
    user_id: str = "user-123",
    query_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "httpMethod": "GET",
        "path": "/songs",
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": user_id,
                },
            },
        },
        "queryStringParameters": query_params,
    }


def _seed_song(
    table: Any,
    user_id: str = "user-123",
    song_id: str = "song-001",
    status: str = "COMPLETED",
    title: str = "Test Song",
) -> None:
    table.put_item(
        Item={
            "userId": user_id,
            "songId": song_id,
            "status": status,
            "title": title,
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-01T00:00:00+00:00",
        }
    )


def test_returns_empty_list_when_no_songs(dynamodb_tables: dict[str, Any]) -> None:
    from functions.list_songs.handler import lambda_handler

    response = lambda_handler(_make_event(), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"] == []


def test_returns_all_songs_for_user(dynamodb_tables: dict[str, Any]) -> None:
    from functions.list_songs.handler import lambda_handler

    table = dynamodb_tables["songs_table"]
    _seed_song(table, song_id="song-001", status="COMPLETED")
    _seed_song(table, song_id="song-002", status="PROCESSING")

    response = lambda_handler(_make_event(), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert len(body["data"]) == 2


def test_filters_by_status(dynamodb_tables: dict[str, Any]) -> None:
    from functions.list_songs.handler import lambda_handler

    table = dynamodb_tables["songs_table"]
    _seed_song(table, song_id="song-001", status="COMPLETED")
    _seed_song(table, song_id="song-002", status="PROCESSING")

    response = lambda_handler(_make_event(query_params={"status": "COMPLETED"}), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert len(body["data"]) == 1
    assert body["data"][0]["status"] == "COMPLETED"


def test_invalid_status_returns_400(dynamodb_tables: dict[str, Any]) -> None:
    from functions.list_songs.handler import lambda_handler

    response = lambda_handler(_make_event(query_params={"status": "INVALID"}), None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "status" in body["message"].lower()


def test_different_users_isolated(dynamodb_tables: dict[str, Any]) -> None:
    from functions.list_songs.handler import lambda_handler

    table = dynamodb_tables["songs_table"]
    _seed_song(table, user_id="user-123", song_id="song-a")
    _seed_song(table, user_id="user-456", song_id="song-b")

    response = lambda_handler(_make_event(user_id="user-123"), None)

    body = json.loads(response["body"])
    assert len(body["data"]) == 1
    assert body["data"][0]["userId"] == "user-123"
