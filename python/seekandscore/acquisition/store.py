"""Artifact storage ports and immutable filesystem/S3 implementations."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class ArtifactCollisionError(RuntimeError):
    """Raised if one content-addressed key already contains different bytes."""


class ArtifactStore(Protocol):
    def put_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str,
        metadata: Mapping[str, str],
    ) -> str: ...


class FileArtifactStore:
    """Local development store that never overwrites an artifact."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str,
        metadata: Mapping[str, str],
    ) -> str:
        del media_type, metadata
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("artifact key escapes storage root")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as output:
                output.write(content)
        except FileExistsError:
            if target.read_bytes() != content:
                raise ArtifactCollisionError(f"immutable artifact collision at {key}") from None
        return target.as_uri()


class S3ArtifactStore:
    """S3-compatible content-addressed store suitable for Railway Buckets."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        region_name: str,
        access_key_id: str,
        secret_access_key: str,
        force_path_style: bool = False,
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(s3={"addressing_style": "path" if force_path_style else "virtual"}),
        )

    def put_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str,
        metadata: Mapping[str, str],
    ) -> str:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            existing_sha = response.get("Metadata", {}).get("sha256")
            requested_sha = metadata.get("sha256")
            if existing_sha != requested_sha:
                raise ArtifactCollisionError(f"immutable artifact collision at {key}")
            return f"s3://{self.bucket}/{key}"

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType=media_type,
                Metadata=dict(metadata),
                IfNoneMatch="*",
            )
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"412", "PreconditionFailed"}:
                raise
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            if response.get("Metadata", {}).get("sha256") != metadata.get("sha256"):
                raise ArtifactCollisionError(f"immutable artifact collision at {key}") from error
        return f"s3://{self.bucket}/{key}"
