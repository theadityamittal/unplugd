"""Environment-driven constants for table names, bucket names, and config."""

from __future__ import annotations

import os


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ---- Application ----
APP_NAME: str = _env("APP_NAME", "unplugd")
ENVIRONMENT: str = _env("ENVIRONMENT", "dev")

# ---- DynamoDB Tables ----
SONGS_TABLE_NAME: str = _env("SONGS_TABLE_NAME", f"{APP_NAME}-{ENVIRONMENT}-songs")
CONNECTIONS_TABLE_NAME: str = _env(
    "CONNECTIONS_TABLE_NAME", f"{APP_NAME}-{ENVIRONMENT}-connections"
)

# ---- DynamoDB Index Names ----
STATUS_INDEX: str = "StatusIndex"
USER_INDEX: str = "UserIndex"

# ---- S3 Buckets ----
UPLOAD_BUCKET_NAME: str = _env("UPLOAD_BUCKET_NAME")
OUTPUT_BUCKET_NAME: str = _env("OUTPUT_BUCKET_NAME")

# ---- Cognito ----
COGNITO_USER_POOL_ID: str = _env("COGNITO_USER_POOL_ID")

# ---- SQS ----
DLQ_URL: str = _env("DLQ_URL")

# ---- Song Status Values ----
STATUS_PENDING_UPLOAD: str = "PENDING_UPLOAD"
STATUS_PROCESSING: str = "PROCESSING"
STATUS_COMPLETED: str = "COMPLETED"
STATUS_FAILED: str = "FAILED"

# ---- Upload Constraints ----
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
MAX_DURATION_SECONDS: int = 600  # 10 minutes
ALLOWED_FORMATS: frozenset[str] = frozenset({"mp3", "wav", "m4a", "flac"})
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/mp4",
        "audio/x-m4a",
        "audio/flac",
    }
)

# ---- Presigned URL ----
PRESIGNED_URL_EXPIRATION: int = 900  # 15 minutes

# ---- WebSocket Connection TTL ----
CONNECTION_TTL_SECONDS: int = 7200  # 2 hours

# ---- S3 Key Patterns ----
UPLOAD_KEY_PREFIX: str = "uploads"
OUTPUT_KEY_PREFIX: str = "output"

# ---- Stems ----
STEM_NAMES: tuple[str, ...] = ("drums", "bass", "other", "vocals")
