"""Tests for shared response module."""

import json

from shared.response import bad_request, created, internal_error, not_found, success


def test_success_response() -> None:
    resp = success({"id": "123"})
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["id"] == "123"


def test_success_with_list() -> None:
    resp = success([{"id": "1"}, {"id": "2"}])
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["data"] == [{"id": "1"}, {"id": "2"}]


def test_created_response() -> None:
    resp = created({"id": "123"})
    assert resp["statusCode"] == 201


def test_bad_request_response() -> None:
    resp = bad_request("Invalid input")
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["error"] == "BadRequest"
    assert body["message"] == "Invalid input"


def test_not_found_response() -> None:
    resp = not_found()
    assert resp["statusCode"] == 404


def test_internal_error_response() -> None:
    resp = internal_error()
    assert resp["statusCode"] == 500


def test_cors_headers_present() -> None:
    resp = success({"ok": True})
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"
    assert "Authorization" in resp["headers"]["Access-Control-Allow-Headers"]
