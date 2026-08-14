"""Runtime composition isolated from the general parcel-ingestion process."""

import httpx
import sqlalchemy as sa

from seekandscore.acquisition.store import S3ArtifactStore
from seekandscore.geography.opportunity_zones.adapter import Cdfi2018ArchiveAdapter
from seekandscore.geography.opportunity_zones.repository import (
    PostgresOpportunityZoneRepository,
)
from seekandscore.geography.opportunity_zones.service import OpportunityZoneImportService
from seekandscore.geography.opportunity_zones.settings import OpportunityZoneImportSettings


def build_import_service(settings: OpportunityZoneImportSettings) -> OpportunityZoneImportService:
    if not settings.database_url:
        raise ValueError("2018 QOZ import requires DATABASE_URL")
    engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
    repository = PostgresOpportunityZoneRepository(engine)
    artifact_store = S3ArtifactStore(
        endpoint_url=settings.object_storage_endpoint or "",
        bucket=settings.object_storage_bucket or "",
        region_name=settings.object_storage_region,
        access_key_id=settings.object_storage_access_key_id or "",
        secret_access_key=settings.object_storage_secret_access_key or "",
        force_path_style=settings.object_storage_force_path_style,
    )
    client = httpx.Client(
        timeout=settings.oz_2018_http_timeout_seconds,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "SeekAndScore/0.1 "
                "(+https://github.com/worldofhacks/seekandscore; federal-geography-import)"
            )
        },
    )
    return OpportunityZoneImportService(
        adapter=Cdfi2018ArchiveAdapter(),
        repository=repository,
        artifact_store=artifact_store,
        http_client=client,
        object_prefix=settings.object_storage_prefix,
        max_retries=settings.oz_2018_max_retries,
        dispose=engine.dispose,
    )
