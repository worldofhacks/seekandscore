"""Content-addressed filesystem and S3 artifact store tests."""

from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from seekandscore.acquisition.store import (
    ArtifactCollisionError,
    FileArtifactStore,
    S3ArtifactStore,
)


def client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class FakeS3Client:
    def __init__(self, *, concurrent: bool = False, sha256: str = "abc") -> None:
        self.concurrent = concurrent
        self.sha256 = sha256
        self.exists = False
        self.put_calls: list[dict[str, Any]] = []

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        if not self.exists:
            raise client_error("404", "HeadObject")
        return {"Metadata": {"sha256": self.sha256}}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(kwargs)
        if self.concurrent:
            self.exists = True
            raise client_error("PreconditionFailed", "PutObject")
        self.exists = True
        return {}


def test_file_store_is_immutable_and_idempotent(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path)

    first = store.put_if_absent(
        key="source/aa/hash.json",
        content=b"same",
        media_type="application/json",
        metadata={"sha256": "abc"},
    )
    second = store.put_if_absent(
        key="source/aa/hash.json",
        content=b"same",
        media_type="application/json",
        metadata={"sha256": "abc"},
    )

    assert first == second
    with pytest.raises(ArtifactCollisionError):
        store.put_if_absent(
            key="source/aa/hash.json",
            content=b"different",
            media_type="application/json",
            metadata={"sha256": "other"},
        )


def test_file_store_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        FileArtifactStore(tmp_path).put_if_absent(
            key="../artifact.json",
            content=b"payload",
            media_type="application/json",
            metadata={},
        )


def test_s3_store_uses_conditional_put_and_handles_same_content_race() -> None:
    client = FakeS3Client(concurrent=True)
    store = S3ArtifactStore(
        bucket="bucket",
        endpoint_url="https://example.invalid",
        region_name="auto",
        access_key_id="test",
        secret_access_key="test",
        client=client,
    )

    uri = store.put_if_absent(
        key="raw/source/ab/abc.json",
        content=b"payload",
        media_type="application/json",
        metadata={"sha256": "abc"},
    )

    assert uri == "s3://bucket/raw/source/ab/abc.json"
    assert client.put_calls[0]["IfNoneMatch"] == "*"


def test_s3_store_rejects_concurrent_different_content() -> None:
    client = FakeS3Client(concurrent=True, sha256="different")
    store = S3ArtifactStore(
        bucket="bucket",
        endpoint_url="https://example.invalid",
        region_name="auto",
        access_key_id="test",
        secret_access_key="test",
        client=client,
    )

    with pytest.raises(ArtifactCollisionError):
        store.put_if_absent(
            key="raw/source/ab/abc.json",
            content=b"payload",
            media_type="application/json",
            metadata={"sha256": "abc"},
        )
