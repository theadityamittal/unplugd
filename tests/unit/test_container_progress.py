"""Tests for containers/shared/progress.py — fire-and-forget progress helpers.

In Docker, the module is imported as `from shared.progress import ...` (flat layout).
In tests, we import as `containers.shared.progress` to avoid collision with functions/shared/.
"""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

CONTAINER_ENV = {
    "USER_ID": "user-abc",
    "SONG_ID": "song-xyz",
    "SEND_PROGRESS_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456789012:function:send-progress",
}


@pytest.fixture(autouse=True)
def _container_env():
    """Set container environment variables for all tests."""
    with patch.dict(os.environ, CONTAINER_ENV):
        yield


@pytest.fixture()
def mock_lambda_client():
    """Patch the module-level lambda_client in containers.shared.progress."""
    mock_client = MagicMock()
    with patch("containers.shared.progress.lambda_client", mock_client):
        yield mock_client


class TestSendProgress:
    def test_send_progress_invokes_lambda(self, mock_lambda_client: MagicMock) -> None:
        """send_progress() should invoke Lambda async with correct payload."""
        from containers.shared.progress import send_progress

        send_progress(stage="demucs", progress=50, message="Separating stems...")

        mock_lambda_client.invoke.assert_called_once()
        call_kwargs = mock_lambda_client.invoke.call_args[1]

        assert call_kwargs["FunctionName"] == CONTAINER_ENV["SEND_PROGRESS_FUNCTION_ARN"]
        assert call_kwargs["InvocationType"] == "Event"

        payload = json.loads(call_kwargs["Payload"])
        assert payload["userId"] == "user-abc"
        assert payload["message"]["type"] == "PROGRESS"
        assert payload["message"]["songId"] == "song-xyz"
        assert payload["message"]["stage"] == "demucs"
        assert payload["message"]["progress"] == 50
        assert payload["message"]["message"] == "Separating stems..."

    def test_send_progress_swallows_exceptions(
        self, mock_lambda_client: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """send_progress() should not raise on Lambda invoke failure."""
        mock_lambda_client.invoke.side_effect = Exception("Connection refused")

        from containers.shared.progress import send_progress

        with caplog.at_level(logging.WARNING):
            send_progress(stage="demucs", progress=50, message="test")

        assert "Failed to send PROGRESS event" in caplog.text

    def test_send_failure_sends_failed_type(self, mock_lambda_client: MagicMock) -> None:
        """send_failure() should send a FAILED message type."""
        from containers.shared.progress import send_failure

        send_failure(error_message="Something broke")

        mock_lambda_client.invoke.assert_called_once()
        call_kwargs = mock_lambda_client.invoke.call_args[1]
        payload = json.loads(call_kwargs["Payload"])

        assert payload["message"]["type"] == "FAILED"
        assert payload["message"]["message"] == "Something broke"
        assert payload["userId"] == "user-abc"
        assert payload["message"]["songId"] == "song-xyz"
