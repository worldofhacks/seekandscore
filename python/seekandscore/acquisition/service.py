"""Replay-safe, fail-closed acquisition application service."""

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4, uuid5

import httpx

from seekandscore.acquisition.adapters.travis_tcad import (
    ArcGisErrorResponse,
    SourceSchemaError,
    TravisTcadArcGisAdapter,
)
from seekandscore.acquisition.models import RawArtifact, SourceRun, SourceRunStatus
from seekandscore.acquisition.repository import AcquisitionRepository
from seekandscore.acquisition.store import ArtifactCollisionError, ArtifactStore
from seekandscore.registry.sources import TRAVIS_TCAD_ACQUISITION_APPROVAL_ID

ARTIFACT_NAMESPACE = UUID("86066bca-12b7-4e7c-adc8-bc57ce7bb2b9")
Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]


class IngestionDisabledError(PermissionError):
    """The environment has not passed the external-ingestion activation gate."""


class AcquisitionService:
    def __init__(
        self,
        *,
        adapter: TravisTcadArcGisAdapter,
        repository: AcquisitionRepository,
        artifact_store: ArtifactStore,
        http_client: httpx.Client,
        object_prefix: str = "raw-artifacts",
        clock: Clock = lambda: datetime.now(UTC),
        sleeper: Sleeper = time.sleep,
        min_request_interval_seconds: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.adapter = adapter
        self.repository = repository
        self.artifact_store = artifact_store
        self.http_client = http_client
        self.object_prefix = object_prefix.strip("/")
        self.clock = clock
        self.sleeper = sleeper
        self.min_request_interval_seconds = min_request_interval_seconds
        self.max_retries = max_retries
        self._last_request_at: datetime | None = None

    def close(self) -> None:
        self.http_client.close()

    def execute(
        self,
        *,
        ingestion_enabled: bool,
        dataset_mode: str,
        activation_id: str | None,
    ) -> SourceRun:
        if not ingestion_enabled or dataset_mode != "live":
            raise IngestionDisabledError(
                "live acquisition requires INGESTION_ENABLED=true and DATASET_MODE=live"
            )
        if activation_id != TRAVIS_TCAD_ACQUISITION_APPROVAL_ID:
            raise IngestionDisabledError(
                "live acquisition requires the approved source acquisition record"
            )

        started_at = self.clock()
        config_hash = _configuration_hash(self.adapter)
        run = SourceRun(
            id=uuid4(),
            source_id=self.adapter.descriptor.id,
            status=SourceRunStatus.RUNNING,
            requested_at=started_at,
            started_at=started_at,
            adapter_version=self.adapter.descriptor.adapter_version,
            parser_version=self.adapter.descriptor.parser_version,
            configuration_hash=config_hash,
            activation_id=activation_id,
        )
        self.repository.save_run(run)
        artifacts: list[UUID] = []
        fetched = 0
        created = 0
        quarantined = 0

        try:
            source_count = self._fetch_count()
            target_count = min(source_count, self.adapter.query.max_records)
            count_was_capped = source_count > self.adapter.query.max_records
            seen_source_record_ids: set[str] = set()
            for page_params in self.adapter.request_pages():
                if fetched >= target_count:
                    break
                params = dict(page_params)
                params["resultRecordCount"] = min(
                    int(params["resultRecordCount"]), target_count - fetched
                )
                headers = {"Accept": "application/json"}
                response = self._request(
                    self.adapter.descriptor.query_uri,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                artifact = self._persist_artifact(
                    content=response.content,
                    params=params,
                    response_etag=response.headers.get("ETag"),
                    retrieved_at=self.clock(),
                )
                artifacts.append(artifact.id)
                observations, bad_records, _exceeded = self.adapter.parse_page(
                    content=response.content,
                    artifact=artifact,
                )
                page_record_count = len(observations) + len(bad_records)
                requested_count = int(params["resultRecordCount"])
                if page_record_count > requested_count:
                    raise SourceSchemaError(
                        "ArcGIS returned more features than resultRecordCount requested"
                    )
                source_record_ids = [item.source_record_id for item in observations]
                source_record_ids.extend(
                    item.source_record_id
                    for item in bad_records
                    if item.source_record_id is not None
                )
                duplicate_ids = seen_source_record_ids.intersection(source_record_ids)
                if len(source_record_ids) != len(set(source_record_ids)) or duplicate_ids:
                    raise SourceSchemaError("ArcGIS pagination returned duplicate OBJECTID values")
                seen_source_record_ids.update(source_record_ids)

                fetched += page_record_count
                created += self.repository.save_observations(observations)
                quarantined += self.repository.save_quarantine(bad_records)

                if page_record_count < requested_count:
                    break

            completed = self.clock()
            partial = count_was_capped or fetched < target_count
            final_status = SourceRunStatus.PARTIAL if partial else SourceRunStatus.SUCCEEDED
            completed_run = run.model_copy(
                update={
                    "status": final_status,
                    "completed_at": completed,
                    "records_fetched": fetched,
                    "observations_created": created,
                    "records_quarantined": quarantined,
                    "artifact_ids": tuple(artifacts),
                    "partial": partial,
                }
            )
            self.repository.save_run(completed_run)
            return completed_run
        except (
            httpx.HTTPError,
            SourceSchemaError,
            ArcGisErrorResponse,
            ArtifactCollisionError,
            OSError,
        ) as error:
            failed = run.model_copy(
                update={
                    "status": SourceRunStatus.FAILED,
                    "completed_at": self.clock(),
                    "records_fetched": fetched,
                    "observations_created": created,
                    "records_quarantined": quarantined,
                    "artifact_ids": tuple(artifacts),
                    "partial": bool(artifacts),
                    "error_code": type(error).__name__,
                    "error_detail": str(error)[:1000],
                }
            )
            self.repository.save_run(failed)
            return failed

    def _fetch_count(self) -> int:
        response = self._request(
            self.adapter.descriptor.query_uri,
            params=self.adapter.query.count_params(),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        try:
            payload = response.json()
            count = int(payload["count"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise SourceSchemaError("ArcGIS count response is invalid") from error
        if count < 0:
            raise SourceSchemaError("ArcGIS count cannot be negative")
        return count

    def _request(
        self,
        url: str,
        *,
        params: dict[str, str | int | bool],
        headers: dict[str, str],
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            self._rate_limit()
            try:
                response = self.http_client.get(url, params=params, headers=headers)
            except httpx.TransportError:
                self._last_request_at = self.clock()
                if attempt >= self.max_retries:
                    raise
                self.sleeper(_retry_delay(None, attempt))
                continue
            self._last_request_at = self.clock()
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            if attempt >= self.max_retries:
                return response
            delay = _retry_delay(response, attempt)
            response.close()
            self.sleeper(delay)
        raise AssertionError("retry loop must return")

    def _rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = (self.clock() - self._last_request_at).total_seconds()
        remaining = self.min_request_interval_seconds - elapsed
        if remaining > 0:
            self.sleeper(remaining)

    def _persist_artifact(
        self,
        *,
        content: bytes,
        params: dict[str, str | int | bool],
        response_etag: str | None,
        retrieved_at: datetime,
    ) -> RawArtifact:
        sha256 = hashlib.sha256(content).hexdigest()
        artifact_id = uuid5(ARTIFACT_NAMESPACE, f"{self.adapter.descriptor.id}:{sha256}")
        key = str(
            PurePosixPath(
                self.object_prefix,
                self.adapter.descriptor.id,
                sha256[:2],
                f"{sha256}.json",
            )
        )
        storage_uri = self.artifact_store.put_if_absent(
            key=key,
            content=content,
            media_type="application/json",
            metadata={"sha256": sha256, "source_id": self.adapter.descriptor.id},
        )
        artifact = RawArtifact(
            id=artifact_id,
            source_id=self.adapter.descriptor.id,
            sha256=sha256,
            byte_count=len(content),
            media_type="application/json",
            storage_uri=storage_uri,
            original_uri=self.adapter.descriptor.query_uri,
            request_params=params,
            response_etag=response_etag,
            retrieved_at=retrieved_at,
        )
        self.repository.save_artifact(artifact)
        return artifact


def _configuration_hash(adapter: TravisTcadArcGisAdapter) -> str:
    payload = {
        "source": adapter.descriptor.id,
        "adapter": adapter.descriptor.adapter_version,
        "parser": adapter.descriptor.parser_version,
        "query": {
            "where": adapter.query.effective_where(),
            "order": adapter.query.order_by,
            "page_size": adapter.query.page_size,
            "max_records": adapter.query.max_records,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after:
        try:
            return min(60.0, max(0.0, float(retry_after)))
        except ValueError:
            pass
    return min(30.0, float(2**attempt))
