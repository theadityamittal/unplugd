"""Root conftest — shared fixtures for all tests."""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import boto3
import pytest
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
os.environ["CLOUDFRONT_DOMAIN"] = "d1234567890.cloudfront.net"


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
