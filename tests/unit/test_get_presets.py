"""Tests for get_presets handler — GET /presets."""

from __future__ import annotations

import json
from typing import Any


def _make_event(user_id: str = "user-123") -> dict[str, Any]:
    return {
        "httpMethod": "GET",
        "path": "/presets",
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": user_id,
                },
            },
        },
    }


def test_returns_presets_list() -> None:
    from functions.get_presets.handler import lambda_handler

    response = lambda_handler(_make_event(), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 5


def test_preset_structure() -> None:
    from functions.get_presets.handler import lambda_handler

    response = lambda_handler(_make_event(), None)

    body = json.loads(response["body"])
    for preset in body["data"]:
        assert "id" in preset
        assert "name" in preset
        assert "description" in preset
        assert "volumes" in preset
        assert set(preset["volumes"].keys()) == {"vocals", "drums", "bass", "other"}
