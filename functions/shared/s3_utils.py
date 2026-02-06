"""S3 helper functions for presigned URLs and object operations."""

from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError
from shared.constants import (
    OUTPUT_BUCKET_NAME,
    PRESIGNED_URL_EXPIRATION,
    STEM_NAMES,
    UPLOAD_BUCKET_NAME,
)

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3")


def generate_presigned_upload_url(key: str, content_type: str) -> str:
    url: str = _s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": UPLOAD_BUCKET_NAME,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=PRESIGNED_URL_EXPIRATION,
    )
    logger.info("Generated presigned upload URL for key=%s", key)
    return url


def delete_object(bucket: str, key: str) -> None:
    _s3.delete_object(Bucket=bucket, Key=key)
    logger.info("Deleted s3://%s/%s", bucket, key)


def delete_objects_by_prefix(bucket: str, prefix: str) -> int:
    paginator = _s3.get_paginator("list_objects_v2")
    deleted_count = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue
        delete_keys: list[dict[str, str]] = [{"Key": obj["Key"]} for obj in objects]
        response = _s3.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})
        errors = response.get("Errors", [])
        if errors:
            logger.error(
                "Failed to delete %d objects from s3://%s/%s",
                len(errors),
                bucket,
                prefix,
            )
        deleted_count += len(delete_keys) - len(errors)

    logger.info("Deleted %d objects from s3://%s/%s", deleted_count, bucket, prefix)
    return deleted_count


def get_stem_urls(user_id: str, song_id: str) -> dict[str, str]:
    return {
        stem: _s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": OUTPUT_BUCKET_NAME,
                "Key": f"output/{user_id}/{song_id}/{stem}.wav",
            },
            ExpiresIn=PRESIGNED_URL_EXPIRATION,
        )
        for stem in STEM_NAMES
    }


def get_lyrics_url(user_id: str, song_id: str) -> str:
    url: str = _s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": OUTPUT_BUCKET_NAME,
            "Key": f"output/{user_id}/{song_id}/lyrics.json",
        },
        ExpiresIn=PRESIGNED_URL_EXPIRATION,
    )
    return url


def head_object(bucket: str, key: str) -> dict[str, Any] | None:
    try:
        response: dict[str, Any] = _s3.head_object(Bucket=bucket, Key=key)
        return response
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "404":
            return None
        raise
