"""Tests for process_upload handler."""

from __future__ import annotations

import io
import struct
from typing import Any

import boto3
from shared.constants import MAX_DURATION_SECONDS, MAX_FILE_SIZE_BYTES


def _make_s3_event(
    bucket: str,
    key: str,
    size: int = 1024,
) -> dict[str, Any]:
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key, "size": size},
                },
            },
        ],
    }


def _create_wav_bytes(duration_sec: float = 5.0, sample_rate: int = 44100) -> bytes:
    """Create a minimal valid WAV file in memory."""
    num_channels = 1
    bits_per_sample = 16
    num_samples = int(sample_rate * duration_sec)
    data_size = num_samples * num_channels * (bits_per_sample // 8)
    # RIFF header
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    # fmt chunk
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))  # chunk size
    buf.write(struct.pack("<H", 1))  # PCM
    buf.write(struct.pack("<H", num_channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * num_channels * bits_per_sample // 8))
    buf.write(struct.pack("<H", num_channels * bits_per_sample // 8))
    buf.write(struct.pack("<H", bits_per_sample))
    # data chunk
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(b"\x00" * data_size)
    return buf.getvalue()


def _setup_song(dynamodb_tables: dict[str, Any], user_id: str, song_id: str) -> None:
    """Create a PENDING_UPLOAD song record in DDB."""
    dynamodb_tables["songs_table"].put_item(
        Item={
            "userId": user_id,
            "songId": song_id,
            "status": "PENDING_UPLOAD",
            "title": "test.wav",
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-01T00:00:00+00:00",
        }
    )


def test_happy_path(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    user_id = "user-123"
    song_id = "song-abc"
    key = f"uploads/{user_id}/{song_id}/test.wav"
    bucket = s3_buckets["upload"]

    # Upload a valid WAV file to mock S3
    wav_data = _create_wav_bytes(duration_sec=5.0)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(Bucket=bucket, Key=key, Body=wav_data)

    _setup_song(dynamodb_tables, user_id, song_id)

    event = _make_s3_event(bucket, key, size=len(wav_data))

    from functions.process_upload.handler import lambda_handler

    lambda_handler(event, None)

    # Verify song was updated to PROCESSING
    result = dynamodb_tables["songs_table"].get_item(Key={"userId": user_id, "songId": song_id})
    item = result["Item"]
    assert item["status"] == "PROCESSING"
    assert item["originalFormat"] == "wav"
    assert int(item["fileSizeBytes"]) == len(wav_data)
    assert int(item["durationSec"]) > 0


def test_file_too_large(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    user_id = "user-123"
    song_id = "song-abc"
    key = f"uploads/{user_id}/{song_id}/test.wav"
    bucket = s3_buckets["upload"]

    # Put a tiny file but report large size in event
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(Bucket=bucket, Key=key, Body=b"fake")

    _setup_song(dynamodb_tables, user_id, song_id)

    event = _make_s3_event(bucket, key, size=MAX_FILE_SIZE_BYTES + 1)

    from functions.process_upload.handler import lambda_handler

    lambda_handler(event, None)

    result = dynamodb_tables["songs_table"].get_item(Key={"userId": user_id, "songId": song_id})
    item = result["Item"]
    assert item["status"] == "FAILED"
    assert "size" in item["errorMessage"].lower() or "exceeds" in item["errorMessage"].lower()


def test_invalid_format(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    user_id = "user-123"
    song_id = "song-abc"
    key = f"uploads/{user_id}/{song_id}/test.ogg"
    bucket = s3_buckets["upload"]

    # Upload a file that mutagen can't recognise as allowed format
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(Bucket=bucket, Key=key, Body=b"not a real audio file at all")

    _setup_song(dynamodb_tables, user_id, song_id)

    event = _make_s3_event(bucket, key, size=100)

    from functions.process_upload.handler import lambda_handler

    lambda_handler(event, None)

    result = dynamodb_tables["songs_table"].get_item(Key={"userId": user_id, "songId": song_id})
    item = result["Item"]
    assert item["status"] == "FAILED"
    err = item["errorMessage"].lower()
    assert "format" in err or "unrecognized" in err


def test_corrupt_file_with_known_extension(
    dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]
) -> None:
    """Mutagen raises on a .mp3 file with garbage content (not None)."""
    user_id = "user-123"
    song_id = "song-abc"
    key = f"uploads/{user_id}/{song_id}/fake.mp3"
    bucket = s3_buckets["upload"]

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(Bucket=bucket, Key=key, Body=b"this is not audio")

    _setup_song(dynamodb_tables, user_id, song_id)

    event = _make_s3_event(bucket, key, size=17)

    from functions.process_upload.handler import lambda_handler

    lambda_handler(event, None)

    result = dynamodb_tables["songs_table"].get_item(Key={"userId": user_id, "songId": song_id})
    item = result["Item"]
    assert item["status"] == "FAILED"
    err = item["errorMessage"].lower()
    assert "unrecognized" in err or "unsupported" in err


def test_duration_too_long(dynamodb_tables: dict[str, Any], s3_buckets: dict[str, Any]) -> None:
    user_id = "user-123"
    song_id = "song-abc"
    key = f"uploads/{user_id}/{song_id}/test.wav"
    bucket = s3_buckets["upload"]

    # Create a WAV that claims to be very long (use low sample rate for small file)
    wav_data = _create_wav_bytes(duration_sec=MAX_DURATION_SECONDS + 60, sample_rate=100)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(Bucket=bucket, Key=key, Body=wav_data)

    _setup_song(dynamodb_tables, user_id, song_id)

    event = _make_s3_event(bucket, key, size=len(wav_data))

    from functions.process_upload.handler import lambda_handler

    lambda_handler(event, None)

    result = dynamodb_tables["songs_table"].get_item(Key={"userId": user_id, "songId": song_id})
    item = result["Item"]
    assert item["status"] == "FAILED"
    assert "duration" in item["errorMessage"].lower()
