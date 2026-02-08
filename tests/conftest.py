"""Root conftest — shared fixtures for all tests."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import boto3
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from moto import mock_aws

# Add functions/ to path so `from shared.xxx import ...` works in tests
sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

# ---- Environment variables for tests ----
os.environ["ENVIRONMENT"] = "test"
os.environ["APP_NAME"] = "unplugd"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["SONGS_TABLE_NAME"] = "unplugd-test-songs"
os.environ["CONNECTIONS_TABLE_NAME"] = "unplugd-test-connections"
os.environ["UPLOAD_BUCKET_NAME"] = "unplugd-test-uploads-123456789012"
os.environ["OUTPUT_BUCKET_NAME"] = "unplugd-test-output-123456789012"
os.environ["STATE_MACHINE_ARN"] = ""
os.environ["WEBSOCKET_API_ENDPOINT"] = "https://test123.execute-api.us-east-1.amazonaws.com/test"
os.environ["COGNITO_APP_CLIENT_ID"] = ""


@dataclass
class FakeLambdaContext:
    """Minimal Lambda context for aws-lambda-powertools compatibility."""

    function_name: str = "test-function"
    function_version: str = "$LATEST"
    invoked_function_arn: str = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    memory_limit_in_mb: int = 128
    aws_request_id: str = "test-request-id"
    log_group_name: str = "/aws/lambda/test-function"
    log_stream_name: str = "2025/01/01/[$LATEST]test"

    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 300000


@pytest.fixture()
def lambda_context() -> FakeLambdaContext:
    """Provide a fake Lambda context for handlers using aws-lambda-powertools."""
    return FakeLambdaContext()


@pytest.fixture()
def dynamodb_tables() -> Generator[dict[str, Any], None, None]:
    """Create mocked DynamoDB tables."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        songs_table = dynamodb.create_table(
            TableName="unplugd-test-songs",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "songId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "songId", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "StatusIndex",
                    "KeySchema": [
                        {"AttributeName": "userId", "KeyType": "HASH"},
                        {"AttributeName": "status", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        connections_table = dynamodb.create_table(
            TableName="unplugd-test-connections",
            KeySchema=[
                {"AttributeName": "connectionId", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "connectionId", "AttributeType": "S"},
                {"AttributeName": "userId", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "UserIndex",
                    "KeySchema": [
                        {"AttributeName": "userId", "KeyType": "HASH"},
                        {"AttributeName": "connectionId", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield {
            "songs_table": songs_table,
            "connections_table": connections_table,
        }


@pytest.fixture()
def s3_buckets() -> Generator[dict[str, Any], None, None]:
    """Create mocked S3 buckets."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="unplugd-test-uploads-123456789012")
        s3.create_bucket(Bucket="unplugd-test-output-123456789012")
        yield {
            "upload": "unplugd-test-uploads-123456789012",
            "output": "unplugd-test-output-123456789012",
        }


# ---- Cognito JWT test keys ----

TEST_USER_POOL_ID = "us-east-1_TestPool123"
TEST_ISSUER = f"https://cognito-idp.us-east-1.amazonaws.com/{TEST_USER_POOL_ID}"
TEST_KID = "test-key-id-1"


@dataclass
class CognitoJwtKeys:
    """Test RSA keys and helper for signing Cognito-like JWTs."""

    private_key: rsa.RSAPrivateKey
    public_key: rsa.RSAPublicKey
    kid: str
    issuer: str
    user_pool_id: str

    def sign_token(
        self,
        claims: dict[str, Any] | None = None,
        *,
        expired: bool = False,
    ) -> str:
        """Sign a JWT with the test RSA private key.

        Default claims produce a valid Cognito ID token for user "test-user-123".
        """
        now = int(time.time())
        default_claims: dict[str, Any] = {
            "sub": "test-user-123",
            "iss": self.issuer,
            "token_use": "id",
            "email": "test@example.com",
            "iat": now,
            "exp": now - 3600 if expired else now + 3600,
            "auth_time": now,
        }
        if claims:
            default_claims.update(claims)

        return jwt.encode(
            default_claims,
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid},
        )


@pytest.fixture()
def cognito_jwt_keys() -> Generator[CognitoJwtKeys, None, None]:
    """Provide test RSA keys and patch jwt_utils to use them for JWT validation."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    keys = CognitoJwtKeys(
        private_key=private_key,
        public_key=public_key,
        kid=TEST_KID,
        issuer=TEST_ISSUER,
        user_pool_id=TEST_USER_POOL_ID,
    )

    # Build a mock PyJWKClient that returns our test public key
    import json as json_mod

    from jwt import PyJWK

    jwk_dict = {
        "kty": "RSA",
        "kid": TEST_KID,
        "use": "sig",
        "alg": "RS256",
        "n": _base64url_uint(public_key.public_numbers().n),
        "e": _base64url_uint(public_key.public_numbers().e),
    }
    mock_jwk = PyJWK.from_json(json_mod.dumps(jwk_dict))

    class MockPyJWKClient:
        def get_signing_key_from_jwt(self, token: str) -> Any:
            header = jwt.get_unverified_header(token)
            if header.get("kid") != TEST_KID:
                raise jwt.exceptions.PyJWKClientError("Key not found")
            return mock_jwk

    with (
        patch("shared.jwt_utils._get_jwks_client", return_value=MockPyJWKClient()),
        patch("shared.jwt_utils.COGNITO_USER_POOL_ID", TEST_USER_POOL_ID),
    ):
        yield keys


def _base64url_uint(val: int) -> str:
    """Encode an integer as a base64url string (for JWK 'n' and 'e' fields)."""
    import base64

    byte_length = (val.bit_length() + 7) // 8
    val_bytes = val.to_bytes(byte_length, byteorder="big")
    return base64.urlsafe_b64encode(val_bytes).rstrip(b"=").decode("ascii")
