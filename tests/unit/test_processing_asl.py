"""Tests for statemachines/processing.asl.json — structural validation."""

from __future__ import annotations

import json
from pathlib import Path

ASL_PATH = Path(__file__).parent.parent.parent / "statemachines" / "processing.asl.json"


def _load_asl() -> dict:
    return json.loads(ASL_PATH.read_text())


def test_valid_json() -> None:
    """ASL file is valid JSON."""
    asl = _load_asl()
    assert isinstance(asl, dict)
    assert "StartAt" in asl
    assert "States" in asl


def test_required_states_exist() -> None:
    """All expected states are defined."""
    asl = _load_asl()
    expected_states = {
        "ValidateInput",
        "RunDemucs",
        "RunWhisper",
        "MarkCompleted",
        "SendNotification",
        "CleanupUpload",
        "Done",
        "MarkFailed",
        "Failed",
    }
    assert expected_states == set(asl["States"].keys())


def test_substitution_variables() -> None:
    """All DefinitionSubstitution variables are present in the ASL text."""
    raw = ASL_PATH.read_text()
    expected_vars = [
        "${EcsClusterArn}",
        "${DemucsTaskDefinitionArn}",
        "${WhisperTaskDefinitionArn}",
        "${PublicSubnet1}",
        "${PublicSubnet2}",
        "${FargateSecurityGroupId}",
        "${CompletionFunctionArn}",
        "${NotifyFunctionArn}",
        "${CleanupFunctionArn}",
        "${FailureHandlerFunctionArn}",
    ]
    for var in expected_vars:
        assert var in raw, f"Missing substitution variable: {var}"


def test_error_catch_paths() -> None:
    """RunDemucs and RunWhisper catch errors and route to MarkFailed."""
    asl = _load_asl()
    states = asl["States"]

    for state_name in ("RunDemucs", "RunWhisper"):
        state = states[state_name]
        assert "Catch" in state, f"{state_name} missing Catch block"
        catch_next = {c["Next"] for c in state["Catch"]}
        assert "MarkFailed" in catch_next, f"{state_name} Catch does not route to MarkFailed"

        # Verify retry config exists
        assert "Retry" in state, f"{state_name} missing Retry block"
