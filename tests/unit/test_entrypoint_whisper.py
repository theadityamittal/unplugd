"""Tests for containers/whisper/entrypoint.py — download, transcribe, upload.

In Docker, the module runs as `python /app/entrypoint.py` with flat layout.
In tests, we import as `containers.whisper.entrypoint` (pythonpath=["."] in pyproject.toml).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ENTRYPOINT_ENV = {
    "OUTPUT_BUCKET": "test-output-bucket",
    "S3_INPUT_KEY": "output/user-abc/song-xyz/vocals.wav",
    "S3_OUTPUT_PREFIX": "output/user-abc/song-xyz",
    "USER_ID": "user-abc",
    "SONG_ID": "song-xyz",
    "SEND_PROGRESS_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456789012:function:send-progress",
}


@pytest.fixture(autouse=True)
def _entrypoint_env():
    """Set container environment variables for all tests."""
    with patch.dict(os.environ, ENTRYPOINT_ENV):
        yield


@pytest.fixture()
def mock_s3_client():
    """Patch the module-level s3_client in the entrypoint."""
    mock_client = MagicMock()
    with patch("containers.whisper.entrypoint.s3_client", mock_client):
        yield mock_client


@pytest.fixture()
def mock_send_progress():
    """Patch send_progress imported in the entrypoint module."""
    with patch("containers.whisper.entrypoint.send_progress") as mock:
        yield mock


@pytest.fixture()
def mock_send_failure():
    """Patch send_failure imported in the entrypoint module."""
    with patch("containers.whisper.entrypoint.send_failure") as mock:
        yield mock


@pytest.fixture()
def mock_whisper_model():
    """Patch WhisperModel at module level (set to None when faster-whisper not installed)."""
    with patch("containers.whisper.entrypoint.WhisperModel") as mock:
        yield mock


def _make_segment(text: str, start: float, end: float, words: list | None = None):
    """Helper to create a mock Whisper segment."""
    seg = MagicMock()
    seg.text = text
    seg.start = start
    seg.end = end
    seg.words = words or []
    return seg


def _make_word(word: str, start: float, end: float):
    """Helper to create a mock Whisper word."""
    w = MagicMock()
    w.word = word
    w.start = start
    w.end = end
    return w


class TestDownloadVocals:
    def test_download_vocals(self, mock_s3_client: MagicMock) -> None:
        """download_vocals should call s3_client.download_file with correct args."""
        from containers.whisper.entrypoint import download_vocals

        download_vocals("output-bucket", "output/user/song/vocals.wav", "/tmp/vocals.wav")

        mock_s3_client.download_file.assert_called_once_with(
            "output-bucket", "output/user/song/vocals.wav", "/tmp/vocals.wav"
        )


class TestRunWhisper:
    def test_run_whisper_with_lyrics(self, mock_whisper_model: MagicMock) -> None:
        """run_whisper should return lyrics dict with segments and words."""
        from containers.whisper.entrypoint import run_whisper

        words = [_make_word("Hello", 0.0, 0.5), _make_word("world", 0.6, 1.0)]
        segment = _make_segment("Hello world", 0.0, 1.0, words)
        info = MagicMock(language="en")

        model_instance = MagicMock()
        model_instance.transcribe.return_value = ([segment], info)
        mock_whisper_model.return_value = model_instance

        result = run_whisper("/tmp/vocals.wav")

        assert result["language"] == "en"
        assert result["instrumental"] is False
        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "Hello world"
        assert len(result["segments"][0]["words"]) == 2
        assert result["segments"][0]["words"][0] == {"word": "Hello", "start": 0.0, "end": 0.5}
        assert result["segments"][0]["words"][1] == {"word": "world", "start": 0.6, "end": 1.0}

    def test_run_whisper_instrumental_empty(self, mock_whisper_model: MagicMock) -> None:
        """run_whisper should detect instrumental tracks (no segments)."""
        from containers.whisper.entrypoint import run_whisper

        info = MagicMock(language="en")
        model_instance = MagicMock()
        model_instance.transcribe.return_value = ([], info)
        mock_whisper_model.return_value = model_instance

        result = run_whisper("/tmp/vocals.wav")

        assert result["instrumental"] is True
        assert result["language"] is None
        assert result["segments"] == []

    def test_run_whisper_short_text_is_instrumental(self, mock_whisper_model: MagicMock) -> None:
        """run_whisper should treat < 10 chars as instrumental (hallucination guard)."""
        from containers.whisper.entrypoint import run_whisper

        segment = _make_segment("   ah   ", 0.0, 1.0)
        info = MagicMock(language="en")
        model_instance = MagicMock()
        model_instance.transcribe.return_value = ([segment], info)
        mock_whisper_model.return_value = model_instance

        result = run_whisper("/tmp/vocals.wav")

        assert result["instrumental"] is True
        assert result["segments"] == []

    def test_run_whisper_model_params(self, mock_whisper_model: MagicMock) -> None:
        """run_whisper should use base model with int8 and correct transcribe params."""
        from containers.whisper.entrypoint import run_whisper

        info = MagicMock(language="en")
        model_instance = MagicMock()
        model_instance.transcribe.return_value = ([], info)
        mock_whisper_model.return_value = model_instance

        run_whisper("/tmp/vocals.wav")

        mock_whisper_model.assert_called_once_with("base", device="cpu", compute_type="int8")
        model_instance.transcribe.assert_called_once_with(
            "/tmp/vocals.wav",
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=True,
        )


class TestUploadLyrics:
    def test_upload_lyrics(self, mock_s3_client: MagicMock) -> None:
        """upload_lyrics should upload JSON to S3 with correct key and content type."""
        from containers.whisper.entrypoint import upload_lyrics

        lyrics_data = {
            "language": "en",
            "instrumental": False,
            "segments": [{"start": 0.0, "end": 1.0, "text": "test", "words": []}],
        }

        upload_lyrics(lyrics_data, "output-bucket", "output/user-abc/song-xyz")

        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "output-bucket"
        assert call_kwargs["Key"] == "output/user-abc/song-xyz/lyrics.json"
        assert call_kwargs["ContentType"] == "application/json"

        uploaded = json.loads(call_kwargs["Body"].decode("utf-8"))
        assert uploaded["language"] == "en"
        assert uploaded["instrumental"] is False
        assert len(uploaded["segments"]) == 1


class TestMain:
    def test_main_full_flow_with_lyrics(
        self,
        mock_s3_client: MagicMock,
        mock_send_progress: MagicMock,
        mock_whisper_model: MagicMock,
        tmp_path: Path,
    ) -> None:
        """main() should orchestrate download -> whisper -> upload with progress."""
        from containers.whisper.entrypoint import main

        words = [_make_word("test", 0.0, 0.5), _make_word("lyrics", 0.6, 1.0)]
        segment = _make_segment("test lyrics here", 0.0, 1.0, words)
        info = MagicMock(language="en")
        model_instance = MagicMock()
        model_instance.transcribe.return_value = ([segment], info)
        mock_whisper_model.return_value = model_instance

        with patch("containers.whisper.entrypoint.TEMP_DIR", str(tmp_path)):
            main()

        # Verify download from OUTPUT_BUCKET
        mock_s3_client.download_file.assert_called_once_with(
            "test-output-bucket",
            "output/user-abc/song-xyz/vocals.wav",
            str(tmp_path / "vocals.wav"),
        )

        # Verify lyrics uploaded
        mock_s3_client.put_object.assert_called_once()

        # Verify progress milestones (4 calls: 5%, 15%, 85%, 100%)
        assert mock_send_progress.call_count == 4
        progress_values = [c[1]["progress"] for c in mock_send_progress.call_args_list]
        assert progress_values == [5, 15, 85, 100]

    def test_main_instrumental_still_uploads(
        self,
        mock_s3_client: MagicMock,
        mock_send_progress: MagicMock,
        mock_whisper_model: MagicMock,
        tmp_path: Path,
    ) -> None:
        """main() should upload empty lyrics.json for instrumental tracks."""
        from containers.whisper.entrypoint import main

        info = MagicMock(language="en")
        model_instance = MagicMock()
        model_instance.transcribe.return_value = ([], info)
        mock_whisper_model.return_value = model_instance

        with patch("containers.whisper.entrypoint.TEMP_DIR", str(tmp_path)):
            main()

        # Verify lyrics.json still uploaded (even for instrumental)
        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args[1]
        uploaded = json.loads(call_kwargs["Body"].decode("utf-8"))
        assert uploaded["instrumental"] is True
        assert uploaded["segments"] == []

        # Verify progress milestones still 4 calls
        assert mock_send_progress.call_count == 4
        progress_values = [c[1]["progress"] for c in mock_send_progress.call_args_list]
        assert progress_values == [5, 15, 85, 100]

    def test_main_exception_exits_1(
        self,
        mock_s3_client: MagicMock,
        mock_send_progress: MagicMock,
        mock_send_failure: MagicMock,
        mock_whisper_model: MagicMock,
    ) -> None:
        """main() should send_failure and sys.exit(1) on any exception."""
        from containers.whisper.entrypoint import main

        mock_s3_client.download_file.side_effect = Exception("download failed")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_send_failure.assert_called_once()
        assert "Exception" in mock_send_failure.call_args[0][0]

    def test_main_missing_env_var_raises(self) -> None:
        """main() should raise RuntimeError when required env vars are missing."""
        from containers.whisper.entrypoint import main

        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(RuntimeError, match="OUTPUT_BUCKET"),
        ):
            main()

    def test_main_reads_env_vars(
        self,
        mock_s3_client: MagicMock,
        mock_send_progress: MagicMock,
        mock_whisper_model: MagicMock,
        tmp_path: Path,
    ) -> None:
        """main() should read bucket and keys from environment variables."""
        from containers.whisper.entrypoint import main

        info = MagicMock(language="en")
        model_instance = MagicMock()
        model_instance.transcribe.return_value = ([], info)
        mock_whisper_model.return_value = model_instance

        with patch("containers.whisper.entrypoint.TEMP_DIR", str(tmp_path)):
            main()

        # Verify download used OUTPUT_BUCKET and S3_INPUT_KEY from env
        download_call = mock_s3_client.download_file.call_args
        assert download_call[0][0] == "test-output-bucket"
        assert download_call[0][1] == "output/user-abc/song-xyz/vocals.wav"

        # Verify upload used OUTPUT_BUCKET and S3_OUTPUT_PREFIX from env
        upload_call = mock_s3_client.put_object.call_args[1]
        assert upload_call["Bucket"] == "test-output-bucket"
        assert upload_call["Key"].startswith("output/user-abc/song-xyz/")
