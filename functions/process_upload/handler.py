"""S3 trigger — validate uploaded audio and kick off processing."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any
from urllib.parse import unquote_plus
from uuid import uuid4

import boto3
import mutagen
from botocore.exceptions import BotoCoreError, ClientError
from shared.constants import (
    ALLOWED_FORMATS,
    MAX_DURATION_SECONDS,
    MAX_FILE_SIZE_BYTES,
    STATUS_FAILED,
    STATUS_PROCESSING,
    UPLOAD_BUCKET_NAME,
)
from shared.dynamodb_utils import update_song

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3")


def lambda_handler(event: dict[str, Any], _context: Any) -> None:
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        size = record["s3"]["object"]["size"]

        logger.info("Processing upload: bucket=%s key=%s size=%d", bucket, key, size)

        # Parse key: uploads/{userId}/{songId}/{filename}
        parts = key.split("/")
        if len(parts) < 4 or parts[0] != "uploads":
            logger.error("Unexpected S3 key format: %s", key)
            continue
        user_id = parts[1]
        song_id = parts[2]
        filename = "/".join(parts[3:])

        try:
            _validate_and_process(bucket, key, size, user_id, song_id, filename)
        except (BotoCoreError, ClientError, OSError):
            logger.exception(
                "Transient error processing upload: songId=%s — will retry via DLQ", song_id
            )
            raise
        except Exception:
            logger.exception("Failed to process upload: songId=%s", song_id)
            update_song(
                user_id,
                song_id,
                {
                    "status": STATUS_FAILED,
                    "errorMessage": "Unexpected error during upload processing",
                },
            )


def _validate_and_process(
    bucket: str,
    key: str,
    size: int,
    user_id: str,
    song_id: str,
    filename: str,
) -> None:
    # 1. Validate file size
    if size > MAX_FILE_SIZE_BYTES:
        logger.warning("File too large: %d bytes (max %d)", size, MAX_FILE_SIZE_BYTES)
        update_song(
            user_id,
            song_id,
            {
                "status": STATUS_FAILED,
                "errorMessage": (
                    f"File size {size} bytes exceeds maximum of {MAX_FILE_SIZE_BYTES} bytes"
                ),
            },
        )
        return

    # 2. Download and validate with mutagen
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1]) as tmp:
        logger.info("Downloading s3://%s/%s to %s", bucket, key, tmp.name)
        _s3.download_file(bucket, key, tmp.name)

        try:
            audio = mutagen.File(tmp.name)
        except (mutagen.MutagenError, OSError):
            logger.warning("Mutagen failed to parse file: %s", filename, exc_info=True)
            audio = None

        if audio is None:
            logger.warning("Unrecognized audio format: %s", filename)
            update_song(
                user_id,
                song_id,
                {
                    "status": STATUS_FAILED,
                    "errorMessage": "Unrecognized or unsupported audio format",
                },
            )
            return

        # Determine format from mutagen type name
        original_format = _extract_format(audio)
        logger.info("Detected format=%s for %s", original_format, filename)
        if original_format not in ALLOWED_FORMATS:
            logger.warning("Disallowed format: %s", original_format)
            update_song(
                user_id,
                song_id,
                {
                    "status": STATUS_FAILED,
                    "errorMessage": f"Format '{original_format}' is not allowed. "
                    f"Allowed: {', '.join(sorted(ALLOWED_FORMATS))}",
                },
            )
            return

        # 3. Validate duration
        duration_sec = audio.info.length
        logger.info("Audio duration=%.1fs size=%d", duration_sec, size)
        if duration_sec > MAX_DURATION_SECONDS:
            logger.warning("Duration too long: %.1fs (max %ds)", duration_sec, MAX_DURATION_SECONDS)
            update_song(
                user_id,
                song_id,
                {
                    "status": STATUS_FAILED,
                    "errorMessage": f"Duration {duration_sec:.0f}s exceeds maximum of "
                    f"{MAX_DURATION_SECONDS}s",
                },
            )
            return

    # 4. Update song status to PROCESSING
    update_song(
        user_id,
        song_id,
        {
            "status": STATUS_PROCESSING,
            "durationSec": int(duration_sec),
            "fileSizeBytes": size,
            "originalFormat": original_format,
        },
    )

    logger.info(
        "Upload validated: songId=%s format=%s duration=%.1fs size=%d",
        song_id,
        original_format,
        duration_sec,
        size,
    )

    # 5. Step Functions stub — will be wired in Phase 6
    state_machine_arn = os.environ.get("STATE_MACHINE_ARN", "")
    if state_machine_arn:
        sfn = boto3.client("stepfunctions")
        sfn.start_execution(
            stateMachineArn=state_machine_arn,
            name=f"{song_id}-{uuid4().hex[:8]}",
            input=json.dumps(
                {
                    "userId": user_id,
                    "songId": song_id,
                    "bucket": UPLOAD_BUCKET_NAME,
                    "key": key,
                }
            ),
        )
        logger.info("Started Step Functions execution for songId=%s", song_id)
    else:
        logger.info(
            "STATE_MACHINE_ARN not set — skipping Step Functions execution for songId=%s",
            song_id,
        )


def _extract_format(audio: mutagen.FileType) -> str:  # type: ignore[name-defined]
    """Map mutagen type to our canonical format name."""
    type_name = type(audio).__name__.lower()
    if "mp3" in type_name:
        return "mp3"
    if "flac" in type_name:
        return "flac"
    if "mp4" in type_name or "m4a" in type_name or "aac" in type_name:
        return "m4a"
    if "wave" in type_name or "wav" in type_name:
        return "wav"
    # Fallback: use the first part of the mime type
    if hasattr(audio, "mime") and audio.mime:
        return audio.mime[0].split("/")[-1]
    return "unknown"
