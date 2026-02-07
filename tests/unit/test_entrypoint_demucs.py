"""Tests for containers/demucs/entrypoint.py — download, separate, upload.

In Docker, the module runs as `python /app/entrypoint.py` with flat layout.
In tests, we import as `containers.demucs.entrypoint` (pythonpath=["."] in pyproject.toml).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ENTRYPOINT_ENV = {
    "UPLOAD_BUCKET": "test-upload-bucket",
    "OUTPUT_BUCKET": "test-output-bucket",
    "S3_INPUT_KEY": "uploads/user-abc/song-xyz/track.mp3",
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
    with patch("containers.demucs.entrypoint.s3_client", mock_client):
        yield mock_client


@pytest.fixture()
def mock_send_progress():
    """Patch send_progress imported in the entrypoint module."""
    with patch("containers.demucs.entrypoint.send_progress") as mock:
        yield mock


class TestDownloadInput:
    def test_download_input(self, mock_s3_client: MagicMock) -> None:
        """download_input should call s3_client.download_file with correct args."""
        from containers.demucs.entrypoint import download_input

        download_input("my-bucket", "uploads/user/song/file.mp3", "/tmp/file.mp3")

        mock_s3_client.download_file.assert_called_once_with(
            "my-bucket", "uploads/user/song/file.mp3", "/tmp/file.mp3"
        )


class TestRunDemucs:
    @patch("containers.demucs.entrypoint.subprocess.run")
    def test_run_demucs_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """run_demucs should return the stems directory path on success."""
        from containers.demucs.entrypoint import run_demucs

        output_dir = str(tmp_path / "output")
        stems_dir = tmp_path / "output" / "htdemucs_ft" / "track"
        stems_dir.mkdir(parents=True)

        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        result = run_demucs("/tmp/track.mp3", output_dir)
        assert result == str(stems_dir)

    @patch("containers.demucs.entrypoint.subprocess.run")
    def test_run_demucs_cli_args(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """run_demucs should pass exact CLI args to subprocess."""
        from containers.demucs.entrypoint import run_demucs

        output_dir = str(tmp_path / "output")
        stems_dir = tmp_path / "output" / "htdemucs_ft" / "input"
        stems_dir.mkdir(parents=True)

        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        run_demucs("/tmp/input.mp3", output_dir)

        expected_cmd = [
            "python",
            "-m",
            "demucs",
            "--name",
            "htdemucs_ft",
            "-d",
            "cpu",
            "--out",
            output_dir,
            "/tmp/input.mp3",
        ]
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        assert actual_cmd == expected_cmd

    @patch("containers.demucs.entrypoint.subprocess.run")
    def test_run_demucs_failure_raises(self, mock_run: MagicMock) -> None:
        """run_demucs should raise RuntimeError on non-zero exit code."""
        from containers.demucs.entrypoint import run_demucs

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stderr=b"demucs error: out of memory"
        )

        with pytest.raises(RuntimeError, match="exit code 1"):
            run_demucs("/tmp/input.mp3", "/tmp/output")

    @patch("containers.demucs.entrypoint.subprocess.run")
    def test_run_demucs_missing_output_raises(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """run_demucs should raise RuntimeError if stems directory doesn't exist."""
        from containers.demucs.entrypoint import run_demucs

        output_dir = str(tmp_path / "output")
        # Don't create the stems directory — it should be missing
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        with pytest.raises(RuntimeError, match="not found"):
            run_demucs("/tmp/input.mp3", output_dir)


class TestUploadStems:
    def test_upload_stems_success(self, mock_s3_client: MagicMock, tmp_path: Path) -> None:
        """upload_stems should upload all 4 stem WAV files with correct keys."""
        from containers.demucs.entrypoint import upload_stems

        # Create 4 stem files
        for stem in ("drums", "bass", "other", "vocals"):
            (tmp_path / f"{stem}.wav").write_bytes(b"fake wav data")

        upload_stems(str(tmp_path), "output-bucket", "output/user-abc/song-xyz")

        assert mock_s3_client.upload_file.call_count == 4
        for stem in ("drums", "bass", "other", "vocals"):
            mock_s3_client.upload_file.assert_any_call(
                str(tmp_path / f"{stem}.wav"),
                "output-bucket",
                f"output/user-abc/song-xyz/{stem}.wav",
                ExtraArgs={"ContentType": "audio/wav"},
            )

    def test_upload_stems_missing_file_raises(
        self, mock_s3_client: MagicMock, tmp_path: Path
    ) -> None:
        """upload_stems should raise if a stem WAV file is missing."""
        from containers.demucs.entrypoint import upload_stems

        # Create only 3 of 4 stems (missing vocals.wav)
        for stem in ("drums", "bass", "other"):
            (tmp_path / f"{stem}.wav").write_bytes(b"fake wav data")

        with pytest.raises(FileNotFoundError):
            upload_stems(str(tmp_path), "output-bucket", "output/user-abc/song-xyz")


class TestMain:
    @patch("containers.demucs.entrypoint.subprocess.run")
    def test_main_full_flow(
        self,
        mock_run: MagicMock,
        mock_s3_client: MagicMock,
        mock_send_progress: MagicMock,
        tmp_path: Path,
    ) -> None:
        """main() should orchestrate download → demucs → upload with progress milestones."""
        from containers.demucs.entrypoint import main

        # Set up: subprocess returns success, create stems directory and files
        stems_dir = tmp_path / "demucs_output" / "htdemucs_ft" / "track"
        stems_dir.mkdir(parents=True)
        for stem in ("drums", "bass", "other", "vocals"):
            (stems_dir / f"{stem}.wav").write_bytes(b"fake wav data")

        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        with patch("containers.demucs.entrypoint.TEMP_DIR", str(tmp_path)):
            main()

        # Verify download
        mock_s3_client.download_file.assert_called_once_with(
            "test-upload-bucket",
            "uploads/user-abc/song-xyz/track.mp3",
            str(tmp_path / "track.mp3"),
        )

        # Verify demucs subprocess was called
        mock_run.assert_called_once()

        # Verify all 4 stems uploaded
        assert mock_s3_client.upload_file.call_count == 4

        # Verify progress milestones (4 calls: 5%, 15%, 85%, 100%)
        assert mock_send_progress.call_count == 4
        progress_values = [c[1]["progress"] for c in mock_send_progress.call_args_list]
        assert progress_values == [5, 15, 85, 100]

    @patch("containers.demucs.entrypoint.subprocess.run")
    def test_main_exception_exits_1(
        self,
        mock_run: MagicMock,
        mock_s3_client: MagicMock,
        mock_send_progress: MagicMock,
    ) -> None:
        """main() should sys.exit(1) on any exception."""
        from containers.demucs.entrypoint import main

        mock_s3_client.download_file.side_effect = Exception("download failed")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch("containers.demucs.entrypoint.subprocess.run")
    def test_main_reads_env_vars(
        self,
        mock_run: MagicMock,
        mock_s3_client: MagicMock,
        mock_send_progress: MagicMock,
        tmp_path: Path,
    ) -> None:
        """main() should read bucket names and keys from environment variables."""
        from containers.demucs.entrypoint import main

        stems_dir = tmp_path / "demucs_output" / "htdemucs_ft" / "track"
        stems_dir.mkdir(parents=True)
        for stem in ("drums", "bass", "other", "vocals"):
            (stems_dir / f"{stem}.wav").write_bytes(b"fake wav data")

        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        with patch("containers.demucs.entrypoint.TEMP_DIR", str(tmp_path)):
            main()

        # Verify download used UPLOAD_BUCKET and S3_INPUT_KEY from env
        download_call = mock_s3_client.download_file.call_args
        assert download_call[0][0] == "test-upload-bucket"
        assert download_call[0][1] == "uploads/user-abc/song-xyz/track.mp3"

        # Verify upload used OUTPUT_BUCKET and S3_OUTPUT_PREFIX from env
        upload_calls = mock_s3_client.upload_file.call_args_list
        for c in upload_calls:
            assert c[0][1] == "test-output-bucket"
            assert c[0][2].startswith("output/user-abc/song-xyz/")

    def test_main_missing_env_var_raises(self) -> None:
        """main() should raise RuntimeError when required env vars are missing."""
        from containers.demucs.entrypoint import main

        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(RuntimeError, match="UPLOAD_BUCKET"),
        ):
            main()
