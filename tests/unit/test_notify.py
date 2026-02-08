"""Tests for notify handler — sends WebSocket notification via SendProgress Lambda."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError


def test_sends_completed_notification(lambda_context: Any) -> None:
    """Handler invokes SendProgress Lambda async with COMPLETED status."""
    with patch.dict(
        os.environ,
        {"SEND_PROGRESS_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456:function:send-progress"},
    ):
        from functions.notify.handler import lambda_handler

        with patch("functions.notify.handler.lambda_client") as mock_lambda:
            result = lambda_handler(
                {"userId": "user-123", "songId": "song-abc", "status": "COMPLETED"},
                lambda_context,
            )

            assert result["notified"] is True
            assert result["status"] == "COMPLETED"

            mock_lambda.invoke.assert_called_once()
            call_kwargs = mock_lambda.invoke.call_args[1]
            assert call_kwargs["InvocationType"] == "Event"
            assert (
                call_kwargs["FunctionName"]
                == "arn:aws:lambda:us-east-1:123456:function:send-progress"
            )

            payload = json.loads(call_kwargs["Payload"])
            assert payload["userId"] == "user-123"
            assert payload["message"]["type"] == "COMPLETED"
            assert payload["message"]["songId"] == "song-abc"


def test_sends_failed_with_error_message(lambda_context: Any) -> None:
    """Handler includes errorMessage in the notification payload."""
    with patch.dict(
        os.environ,
        {"SEND_PROGRESS_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456:function:send-progress"},
    ):
        from functions.notify.handler import lambda_handler

        with patch("functions.notify.handler.lambda_client") as mock_lambda:
            result = lambda_handler(
                {
                    "userId": "user-123",
                    "songId": "song-abc",
                    "status": "FAILED",
                    "errorMessage": "Demucs crashed",
                },
                lambda_context,
            )

            assert result["status"] == "FAILED"

            payload = json.loads(mock_lambda.invoke.call_args[1]["Payload"])
            assert payload["message"]["type"] == "FAILED"
            assert payload["message"]["message"] == "Demucs crashed"


def test_invoke_failure_propagates(lambda_context: Any) -> None:
    """Lambda invoke errors propagate so Step Functions can catch them."""
    with patch.dict(
        os.environ,
        {"SEND_PROGRESS_FUNCTION_ARN": "arn:aws:lambda:us-east-1:123456:function:send-progress"},
    ):
        from functions.notify.handler import lambda_handler

        with patch("functions.notify.handler.lambda_client") as mock_lambda:
            mock_lambda.invoke.side_effect = ClientError(
                {"Error": {"Code": "ServiceException", "Message": "Lambda down"}},
                "Invoke",
            )

            with pytest.raises(ClientError):
                lambda_handler(
                    {"userId": "user-123", "songId": "song-abc", "status": "COMPLETED"},
                    lambda_context,
                )
