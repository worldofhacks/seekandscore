"""Wire validated settings to acquisition ports and adapters."""

from pathlib import Path

import httpx
import sqlalchemy as sa

from seekandscore.acquisition.adapters import TravisTcadArcGisAdapter, TravisTcadQuery
from seekandscore.acquisition.repository import PostgresAcquisitionRepository
from seekandscore.acquisition.service import AcquisitionService
from seekandscore.acquisition.store import ArtifactStore, FileArtifactStore, S3ArtifactStore
from seekandscore.platform.settings import AppEnvironment, Settings


def build_acquisition_service(settings: Settings) -> AcquisitionService:
    if settings.ingestion_source_id != "travis_tcad_parcels":
        raise ValueError(f"unsupported source: {settings.ingestion_source_id}")
    if not settings.database_url:
        raise ValueError("live ingestion requires DATABASE_URL")

    query = TravisTcadQuery(
        page_size=settings.ingestion_page_size,
        max_records=settings.ingestion_max_records,
        where=settings.ingestion_where,
        order_by=settings.ingestion_order_by,
        cities=tuple(
            city.strip().upper() for city in settings.ingestion_cities.split(",") if city.strip()
        ),
    )
    adapter = TravisTcadArcGisAdapter(query)
    engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
    repository = PostgresAcquisitionRepository(engine)

    s3_values = (
        settings.object_storage_endpoint,
        settings.object_storage_bucket,
        settings.object_storage_access_key_id,
        settings.object_storage_secret_access_key,
    )
    artifact_store: ArtifactStore
    if all(s3_values):
        artifact_store = S3ArtifactStore(
            endpoint_url=settings.object_storage_endpoint or "",
            bucket=settings.object_storage_bucket or "",
            region_name=settings.object_storage_region,
            access_key_id=settings.object_storage_access_key_id or "",
            secret_access_key=settings.object_storage_secret_access_key or "",
            force_path_style=settings.object_storage_force_path_style,
        )
    elif settings.app_env in {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST}:
        artifact_store = FileArtifactStore(Path(settings.raw_artifact_root))
    else:
        raise ValueError("staging and production ingestion require durable object storage")

    client = httpx.Client(
        timeout=settings.ingestion_http_timeout_seconds,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "SeekAndScore/0.1 (+https://github.com/worldofhacks/seekandscore; source-ingestion)"
            )
        },
    )
    return AcquisitionService(
        adapter=adapter,
        repository=repository,
        artifact_store=artifact_store,
        http_client=client,
        object_prefix=settings.object_storage_prefix,
        min_request_interval_seconds=settings.ingestion_min_request_interval_seconds,
        max_retries=settings.ingestion_max_retries,
    )
