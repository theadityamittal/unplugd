"""Tests for shared constants module."""

from shared.constants import (
    ALLOWED_FORMATS,
    CONNECTIONS_TABLE_NAME,
    MAX_DURATION_SECONDS,
    MAX_FILE_SIZE_BYTES,
    SONGS_TABLE_NAME,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING_UPLOAD,
    STATUS_PROCESSING,
    STEM_NAMES,
)


def test_table_names_include_environment() -> None:
    assert "test" in SONGS_TABLE_NAME
    assert "test" in CONNECTIONS_TABLE_NAME


def test_status_values_are_distinct() -> None:
    statuses = {STATUS_PENDING_UPLOAD, STATUS_PROCESSING, STATUS_COMPLETED, STATUS_FAILED}
    assert len(statuses) == 4


def test_allowed_formats() -> None:
    assert "mp3" in ALLOWED_FORMATS
    assert "wav" in ALLOWED_FORMATS
    assert "exe" not in ALLOWED_FORMATS


def test_upload_constraints() -> None:
    assert MAX_FILE_SIZE_BYTES == 50 * 1024 * 1024
    assert MAX_DURATION_SECONDS == 600


def test_stem_names() -> None:
    assert STEM_NAMES == ("drums", "bass", "other", "vocals")
