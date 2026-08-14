"""Activated, immutable, replay-safe 2018 Opportunity Zone import service."""

import hashlib
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4, uuid5

import httpx
import sqlalchemy as sa

from seekandscore.acquisition.models import RawArtifact
from seekandscore.acquisition.store import (
    ArtifactCollisionError,
    ArtifactStore,
    ArtifactStoreError,
)
from seekandscore.geography.opportunity_zones.adapter import (
    Cdfi2018ArchiveAdapter,
    OpportunityZoneArchiveError,
)
from seekandscore.geography.opportunity_zones.models import (
    DesignationStatus,
    OpportunityZoneImportRun,
    OpportunityZoneImportStatus,
    OpportunityZoneRound,
)
from seekandscore.geography.opportunity_zones.repository import (
    OpportunityZonePersistenceError,
    OpportunityZoneRepository,
)
from seekandscore.geography.opportunity_zones.source import (
    CDFI_QOZ_2018_ACTIVATION_ID,
    CDFI_QOZ_2018_ARCHIVE_URL,
    CDFI_QOZ_2018_CENSUS_VINTAGE,
    CDFI_QOZ_2018_EXPECTED_BYTES,
    CDFI_QOZ_2018_EXPECTED_GEOMETRY_REPAIRS,
    CDFI_QOZ_2018_EXPECTED_SHA256,
    CDFI_QOZ_2018_EXPECTED_TRACTS,
    CDFI_QOZ_2018_LANDING_URL,
    CDFI_QOZ_2018_ROUND_ID,
    CDFI_QOZ_2018_SOURCE,
)

_ARTIFACT_NAMESPACE = UUID("d0b94987-f921-47b2-9375-9357486b0984")
Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]


class OpportunityZoneImportDisabledError(PermissionError):
    """No external download occurs unless both dedicated gates are exact."""


class OpportunityZoneImportService:
    def __init__(
        self,
        *,
        adapter: Cdfi2018ArchiveAdapter,
        repository: OpportunityZoneRepository,
        artifact_store: ArtifactStore,
        http_client: httpx.Client,
        expected_bytes: int = CDFI_QOZ_2018_EXPECTED_BYTES,
        expected_sha256: str = CDFI_QOZ_2018_EXPECTED_SHA256,
        expected_tracts: int = CDFI_QOZ_2018_EXPECTED_TRACTS,
        expected_geometry_repairs: int = CDFI_QOZ_2018_EXPECTED_GEOMETRY_REPAIRS,
        object_prefix: str = "raw-artifacts",
        max_download_bytes: int = 64 * 1024 * 1024,
        max_retries: int = 3,
        clock: Clock = lambda: datetime.now(UTC),
        sleeper: Sleeper = time.sleep,
        dispose: Callable[[], None] = lambda: None,
    ) -> None:
        self.adapter = adapter
        self.repository = repository
        self.artifact_store = artifact_store
        self.http_client = http_client
        self.expected_bytes = expected_bytes
        self.expected_sha256 = expected_sha256
        self.expected_tracts = expected_tracts
        self.expected_geometry_repairs = expected_geometry_repairs
        self.object_prefix = object_prefix.strip("/")
        self.max_download_bytes = max_download_bytes
        self.max_retries = max_retries
        self.clock = clock
        self.sleeper = sleeper
        self.dispose = dispose

    def close(self) -> None:
        self.http_client.close()
        self.dispose()

    def execute(
        self,
        *,
        import_enabled: bool,
        activation_id: str | None,
    ) -> OpportunityZoneImportRun:
        if not import_enabled:
            raise OpportunityZoneImportDisabledError("2018 QOZ import kill switch is disabled")
        if activation_id != CDFI_QOZ_2018_ACTIVATION_ID:
            raise OpportunityZoneImportDisabledError(
                "2018 QOZ import requires the exact reviewed activation ID"
            )

        started_at = self.clock()
        run = OpportunityZoneImportRun(
            id=uuid4(),
            source_id=CDFI_QOZ_2018_SOURCE.id,
            status=OpportunityZoneImportStatus.RUNNING,
            activation_id=activation_id,
            started_at=started_at,
            expected_tracts=self.expected_tracts,
        )
        self.repository.register_source(CDFI_QOZ_2018_SOURCE, registered_at=started_at)
        self.repository.save_run(run)
        artifact: RawArtifact | None = None
        try:
            content, etag = self._download()
            sha256 = hashlib.sha256(content).hexdigest()
            if len(content) != self.expected_bytes or sha256 != self.expected_sha256:
                raise OpportunityZoneArchiveError(
                    "download does not match the reviewed official archive bytes and SHA-256"
                )
            artifact = self._persist_artifact(content, sha256=sha256, etag=etag)
            round_record = OpportunityZoneRound(
                id=CDFI_QOZ_2018_ROUND_ID,
                round_code="2018",
                census_vintage=CDFI_QOZ_2018_CENSUS_VINTAGE,
                certification_status=DesignationStatus.TREASURY_CERTIFIED,
                designation_status=DesignationStatus.EFFECTIVE,
                effective_from=date(2017, 12, 22),
                effective_to=date(2028, 12, 31),
                tract_intervals_vary=True,
                source_id=CDFI_QOZ_2018_SOURCE.id,
                source_artifact_id=artifact.id,
                source_artifact_sha256=artifact.sha256,
                authority_uri=CDFI_QOZ_2018_LANDING_URL,
            )
            with self.adapter.open_archive(content, artifact_id=artifact.id) as dataset:
                outcome = self.repository.import_tracts(
                    round_record=round_record,
                    tracts=dataset.iter_tracts(),
                    expected_tracts=self.expected_tracts,
                    expected_geometry_repairs=self.expected_geometry_repairs,
                    loaded_at=self.clock(),
                )
            completed = run.model_copy(
                update={
                    "status": (
                        OpportunityZoneImportStatus.SUCCEEDED_UNCHANGED
                        if outcome.unchanged
                        else OpportunityZoneImportStatus.SUCCEEDED
                    ),
                    "completed_at": self.clock(),
                    "source_artifact_id": artifact.id,
                    "source_artifact_sha256": artifact.sha256,
                    "imported_tracts": outcome.total_tracts,
                }
            )
            self.repository.save_run(completed)
            return completed
        except (
            httpx.HTTPError,
            OpportunityZoneArchiveError,
            OpportunityZonePersistenceError,
            ArtifactCollisionError,
            ArtifactStoreError,
            sa.exc.SQLAlchemyError,
            OSError,
        ) as error:
            failed = run.model_copy(
                update={
                    "status": OpportunityZoneImportStatus.FAILED,
                    "completed_at": self.clock(),
                    "source_artifact_id": artifact.id if artifact else None,
                    "source_artifact_sha256": artifact.sha256 if artifact else None,
                    "error_code": type(error).__name__,
                    "error_detail": str(error)[:1000],
                }
            )
            self.repository.save_run(failed)
            return failed

    def _download(self) -> tuple[bytes, str | None]:
        for attempt in range(self.max_retries + 1):
            try:
                with self.http_client.stream(
                    "GET",
                    CDFI_QOZ_2018_ARCHIVE_URL,
                    headers={"Accept": "application/zip, application/octet-stream"},
                ) as response:
                    if response.status_code in {429, 500, 502, 503, 504}:
                        if attempt >= self.max_retries:
                            response.raise_for_status()
                        retry_after = response.headers.get("Retry-After")
                        delay = _retry_delay(retry_after, attempt)
                    else:
                        response.raise_for_status()
                        declared = response.headers.get("Content-Length")
                        if declared is not None:
                            try:
                                declared_bytes = int(declared)
                            except ValueError as error:
                                raise OpportunityZoneArchiveError(
                                    "official archive returned an invalid Content-Length"
                                ) from error
                            if declared_bytes < 0:
                                raise OpportunityZoneArchiveError(
                                    "official archive returned an invalid Content-Length"
                                )
                            if declared_bytes > self.max_download_bytes:
                                raise OpportunityZoneArchiveError(
                                    "official archive exceeds the download byte limit"
                                )
                        chunks: list[bytes] = []
                        byte_count = 0
                        for chunk in response.iter_bytes():
                            byte_count += len(chunk)
                            if byte_count > self.max_download_bytes:
                                raise OpportunityZoneArchiveError(
                                    "official archive exceeds the download byte limit"
                                )
                            chunks.append(chunk)
                        return b"".join(chunks), response.headers.get("ETag")
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    raise
                delay = _retry_delay(None, attempt)
            self.sleeper(delay)
        raise AssertionError("download retry loop must return or raise")

    def _persist_artifact(self, content: bytes, *, sha256: str, etag: str | None) -> RawArtifact:
        artifact_id = uuid5(_ARTIFACT_NAMESPACE, f"{CDFI_QOZ_2018_SOURCE.id}:{sha256}")
        key = str(
            PurePosixPath(
                self.object_prefix,
                CDFI_QOZ_2018_SOURCE.id,
                sha256[:2],
                f"{sha256}.zip",
            )
        )
        storage_uri = self.artifact_store.put_if_absent(
            key=key,
            content=content,
            media_type="application/zip",
            metadata={"sha256": sha256, "source_id": CDFI_QOZ_2018_SOURCE.id},
        )
        artifact = RawArtifact(
            id=artifact_id,
            source_id=CDFI_QOZ_2018_SOURCE.id,
            sha256=sha256,
            byte_count=len(content),
            media_type="application/zip",
            storage_uri=storage_uri,
            original_uri=CDFI_QOZ_2018_ARCHIVE_URL,
            request_params={},
            response_etag=etag,
            retrieved_at=self.clock(),
        )
        self.repository.save_artifact(artifact)
        return artifact


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return min(60.0, max(0.0, float(retry_after)))
        except ValueError:
            pass
    return min(30.0, float(2**attempt))
