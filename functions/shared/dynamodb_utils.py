"""DynamoDB helper functions for Songs and Connections tables."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from shared.constants import (
    CONNECTIONS_TABLE_NAME,
    SONGS_TABLE_NAME,
    STATUS_INDEX,
    USER_INDEX,
)

logger = logging.getLogger(__name__)

_dynamodb = boto3.resource("dynamodb")


def _songs_table():  # type: ignore[no-untyped-def]
    return _dynamodb.Table(SONGS_TABLE_NAME)


def _connections_table():  # type: ignore[no-untyped-def]
    return _dynamodb.Table(CONNECTIONS_TABLE_NAME)


# ---- Songs ----


def put_song(item: dict[str, Any]) -> None:
    _songs_table().put_item(Item=item)
    logger.info("Put song: userId=%s songId=%s", item.get("userId"), item.get("songId"))


def get_song(user_id: str, song_id: str) -> dict[str, Any] | None:
    response = _songs_table().get_item(Key={"userId": user_id, "songId": song_id})
    return response.get("Item")  # type: ignore[return-value]


def update_song(
    user_id: str,
    song_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {}

    for i, (key, value) in enumerate(updates.items()):
        alias = f"#attr{i}"
        placeholder = f":val{i}"
        expr_parts.append(f"{alias} = {placeholder}")
        expr_names[alias] = key
        expr_values[placeholder] = value

    expr_parts.append("#updatedAt = :updatedAt")
    expr_names["#updatedAt"] = "updatedAt"
    expr_values[":updatedAt"] = datetime.now(UTC).isoformat()

    response = _songs_table().update_item(
        Key={"userId": user_id, "songId": song_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )
    logger.info("Updated song: userId=%s songId=%s", user_id, song_id)
    return response["Attributes"]  # type: ignore[return-value]


def _query_all(table: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Query DynamoDB with automatic pagination."""
    items: list[dict[str, Any]] = []
    response = table.query(**kwargs)
    items.extend(response["Items"])
    while "LastEvaluatedKey" in response:
        response = table.query(ExclusiveStartKey=response["LastEvaluatedKey"], **kwargs)
        items.extend(response["Items"])
    return items


def query_songs_by_user(user_id: str) -> list[dict[str, Any]]:
    return _query_all(
        _songs_table(),
        KeyConditionExpression=Key("userId").eq(user_id),
    )


def query_songs_by_status(user_id: str, status: str) -> list[dict[str, Any]]:
    return _query_all(
        _songs_table(),
        IndexName=STATUS_INDEX,
        KeyConditionExpression=Key("userId").eq(user_id) & Key("status").eq(status),
    )


def delete_song(user_id: str, song_id: str) -> None:
    _songs_table().delete_item(Key={"userId": user_id, "songId": song_id})
    logger.info("Deleted song: userId=%s songId=%s", user_id, song_id)


# ---- Connections ----


def put_connection(item: dict[str, Any]) -> None:
    _connections_table().put_item(Item=item)
    logger.info(
        "Put connection: connectionId=%s userId=%s",
        item.get("connectionId"),
        item.get("userId"),
    )


def get_connection(connection_id: str) -> dict[str, Any] | None:
    response = _connections_table().get_item(Key={"connectionId": connection_id})
    return response.get("Item")  # type: ignore[return-value]


def query_connections_by_user(user_id: str) -> list[dict[str, Any]]:
    return _query_all(
        _connections_table(),
        IndexName=USER_INDEX,
        KeyConditionExpression=Key("userId").eq(user_id),
    )


def delete_connection(connection_id: str) -> None:
    _connections_table().delete_item(Key={"connectionId": connection_id})
    logger.info("Deleted connection: connectionId=%s", connection_id)
