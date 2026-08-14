"""Official 2018 QOZ archive, activation, lineage, and replay tests."""

import hashlib
import json
import os
import zipfile
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import shapefile
import sqlalchemy as sa
from pydantic import ValidationError

from seekandscore.acquisition.models import RawArtifact
from seekandscore.acquisition.store import FileArtifactStore
from seekandscore.geography.opportunity_zones.adapter import (
    ArchiveSafetyLimits,
    Cdfi2018ArchiveAdapter,
    OpportunityZoneArchiveError,
)
from seekandscore.geography.opportunity_zones.models import (
    DesignationStatus,
    OpportunityZoneImportStatus,
    OpportunityZoneRound,
)
from seekandscore.geography.opportunity_zones.repository import (
    MemoryOpportunityZoneRepository,
    OpportunityZonePersistenceError,
    PostgresOpportunityZoneRepository,
)
from seekandscore.geography.opportunity_zones.service import (
    OpportunityZoneImportDisabledError,
    OpportunityZoneImportService,
)
from seekandscore.geography.opportunity_zones.settings import (
    OpportunityZoneImportSettings,
)
from seekandscore.geography.opportunity_zones.source import (
    CDFI_QOZ_2018_ACTIVATION_ID,
    CDFI_QOZ_2018_ROUND_ID,
    CDFI_QOZ_2018_SOURCE,
)

FIXTURE = Path(__file__).parent / "fixtures" / "oz_2018_tracts.json"
PRJ = (
    'PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere",'
    'GEOGCS["GCS_WGS_1984"],PROJECTION["Mercator_Auxiliary_Sphere"]]'
)


def build_archive(
    records: list[dict[str, object]] | None = None,
    *,
    extra_members: dict[str, bytes] | None = None,
) -> bytes:
    source = records or json.loads(FIXTURE.read_text(encoding="utf-8"))
    shp = BytesIO()
    shx = BytesIO()
    dbf = BytesIO()
    writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    writer.field("CENSUSTRAC", "C", size=11)
    writer.field("STATENAME", "C", size=50)
    writer.field("COUNTYNAME", "C", size=50)
    for record in source:
        writer.poly(record["rings"])  # type: ignore[arg-type]
        writer.record(
            record["tract_geoid"],
            record["state_name"],
            record["county_name"],
        )
    writer.close()

    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("8764oz.shp", shp.getvalue())
        archive.writestr("8764oz.shx", shx.getvalue())
        archive.writestr("8764oz.dbf", dbf.getvalue())
        archive.writestr("8764oz.prj", PRJ)
        archive.writestr("Designated QOZs.12.14.18.xlsx", b"fixture-workbook")
        archive.writestr("Readme8764.txt", b"fixture-readme")
        for name, content in (extra_members or {}).items():
            archive.writestr(name, content)
    return output.getvalue()


def adapter_for(content: bytes, *, count: int = 2) -> Cdfi2018ArchiveAdapter:
    return Cdfi2018ArchiveAdapter(
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_tracts=count,
    )


def parse(content: bytes, *, count: int = 2):  # type: ignore[no-untyped-def]
    with adapter_for(content, count=count).open_archive(
        content,
        artifact_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    ) as dataset:
        return tuple(dataset.iter_tracts())


def test_archive_preserves_unique_2010_geoids_multipolygons_and_lineage() -> None:
    content = build_archive()

    tracts = parse(content)

    assert len(tracts) == 2
    assert {item.tract_geoid for item in tracts} == {"01001020100", "72001080100"}
    assert all(item.census_vintage == 2010 for item in tracts)
    assert all(item.geometry_srid == 3857 for item in tracts)
    assert all(json.loads(item.geometry_geojson)["type"] == "MultiPolygon" for item in tracts)
    assert all(item.certification_status is DesignationStatus.TREASURY_CERTIFIED for item in tracts)
    assert all(item.designation_status is DesignationStatus.EFFECTIVE for item in tracts)
    assert tracts[0].effective_from == date(2018, 1, 1)
    assert tracts[0].effective_to == date(2028, 12, 31)
    assert tracts[1].effective_from == date(2017, 12, 22)
    assert tracts[1].effective_to == date(2027, 12, 31)
    assert all(
        item.source_artifact_sha256 == hashlib.sha256(content).hexdigest() for item in tracts
    )


def test_archive_rejects_duplicate_or_malformed_geoids() -> None:
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records[1]["tract_geoid"] = records[0]["tract_geoid"]
    duplicate = build_archive(records)
    with pytest.raises(OpportunityZoneArchiveError, match="duplicate tract GEOID"):
        parse(duplicate)

    records[1]["tract_geoid"] = "123"
    malformed = build_archive(records)
    with pytest.raises(OpportunityZoneArchiveError, match="11-character"):
        parse(malformed)


def test_archive_rejects_path_traversal_before_extraction() -> None:
    content = build_archive(extra_members={"../escape.txt": b"not allowed"})

    with pytest.raises(OpportunityZoneArchiveError, match="unsafe or nested"):
        parse(content)


def test_archive_rejects_uncompressed_limit_and_unreviewed_sha() -> None:
    content = build_archive()
    constrained = Cdfi2018ArchiveAdapter(
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_tracts=2,
        limits=ArchiveSafetyLimits(max_uncompressed_bytes=100),
    )
    with (
        pytest.raises(OpportunityZoneArchiveError, match="uncompressed byte limit"),
        constrained.open_archive(content, artifact_id=uuid4()),
    ):
        pass

    with (
        pytest.raises(OpportunityZoneArchiveError, match="SHA-256"),
        Cdfi2018ArchiveAdapter(expected_tracts=2).open_archive(
            content,
            artifact_id=uuid4(),
        ),
    ):
        pass


def test_2027_round_cannot_be_marked_effective() -> None:
    with pytest.raises(ValidationError, match="cannot be represented as effective"):
        OpportunityZoneRound(
            id="us-federal-qoz-2027",
            round_code="2027",
            census_vintage=2020,
            certification_status=DesignationStatus.ELIGIBLE,
            designation_status=DesignationStatus.EFFECTIVE,
            effective_from=date(2027, 1, 1),
            effective_to=date(2036, 12, 31),
            source_id="federal_qoz_2027_eligible_tracts",
            source_artifact_id=uuid4(),
            source_artifact_sha256="a" * 64,
            authority_uri="https://home.treasury.gov/",
        )


def build_service(
    tmp_path: Path,
    content: bytes,
    repository: MemoryOpportunityZoneRepository,
) -> tuple[OpportunityZoneImportService, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=content, headers={"ETag": '"fixture"'})

    return (
        OpportunityZoneImportService(
            adapter=adapter_for(content),
            repository=repository,
            artifact_store=FileArtifactStore(tmp_path),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            expected_bytes=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_tracts=2,
            expected_geometry_repairs=0,
            clock=lambda: datetime(2026, 8, 13, 12, tzinfo=UTC),
            sleeper=lambda _seconds: None,
        ),
        requests,
    )


def test_import_is_disabled_by_default_and_requires_exact_activation(tmp_path: Path) -> None:
    content = build_archive()
    repository = MemoryOpportunityZoneRepository()
    service, requests = build_service(tmp_path, content, repository)

    with pytest.raises(OpportunityZoneImportDisabledError, match="kill switch"):
        service.execute(import_enabled=False, activation_id=None)
    with pytest.raises(OpportunityZoneImportDisabledError, match="exact reviewed"):
        service.execute(import_enabled=True, activation_id="wrong")

    assert requests == []
    assert repository.runs == {}
    assert OpportunityZoneImportSettings().oz_2018_import_enabled is False


def test_identical_replay_is_unchanged_and_keeps_one_immutable_artifact(tmp_path: Path) -> None:
    content = build_archive()
    repository = MemoryOpportunityZoneRepository()
    service, requests = build_service(tmp_path, content, repository)

    first = service.execute(
        import_enabled=True,
        activation_id=CDFI_QOZ_2018_ACTIVATION_ID,
    )
    replay = service.execute(
        import_enabled=True,
        activation_id=CDFI_QOZ_2018_ACTIVATION_ID,
    )

    assert first.status is OpportunityZoneImportStatus.SUCCEEDED
    assert replay.status is OpportunityZoneImportStatus.SUCCEEDED_UNCHANGED
    assert first.imported_tracts == replay.imported_tracts == 2
    assert len(repository.tracts) == 2
    assert len(repository.artifacts) == 1
    assert len(repository.runs) == 2
    assert len(requests) == 2
    artifact = next(iter(repository.artifacts.values()))
    stored = Path(artifact.storage_uri.removeprefix("file://"))
    assert stored.read_bytes() == content


def test_import_records_a_failed_run_for_invalid_content_length(tmp_path: Path) -> None:
    content = build_archive()
    repository = MemoryOpportunityZoneRepository()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Length": "not-a-number"},
        )

    service = OpportunityZoneImportService(
        adapter=adapter_for(content),
        repository=repository,
        artifact_store=FileArtifactStore(tmp_path),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_bytes=len(content),
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_tracts=2,
        expected_geometry_repairs=0,
        clock=lambda: datetime(2026, 8, 13, 12, tzinfo=UTC),
        sleeper=lambda _seconds: None,
    )

    run = service.execute(
        import_enabled=True,
        activation_id=CDFI_QOZ_2018_ACTIVATION_ID,
    )

    assert run.status is OpportunityZoneImportStatus.FAILED
    assert run.error_code == "OpportunityZoneArchiveError"
    assert run.error_detail == "official archive returned an invalid Content-Length"
    assert repository.artifacts == {}


TEST_DATABASE_URL = os.getenv("SEEKANDSCORE_TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="SEEKANDSCORE_TEST_DATABASE_URL is not set")
def test_postgis_import_is_transactional_valid_indexed_and_replay_safe() -> None:
    assert TEST_DATABASE_URL is not None
    database_name = sa.engine.make_url(TEST_DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("SEEKANDSCORE_TEST_DATABASE_URL must name a database ending in _test")

    content = build_archive()
    sha256 = hashlib.sha256(content).hexdigest()
    artifact_id = uuid4()
    now = datetime(2026, 8, 13, 12, tzinfo=UTC)
    artifact = RawArtifact(
        id=artifact_id,
        source_id=CDFI_QOZ_2018_SOURCE.id,
        sha256=sha256,
        byte_count=len(content),
        media_type="application/zip",
        storage_uri=f"s3://private-test/{sha256}.zip",
        original_uri=CDFI_QOZ_2018_SOURCE.original_uri,
        request_params={},
        retrieved_at=now,
    )
    round_record = OpportunityZoneRound(
        id=CDFI_QOZ_2018_ROUND_ID,
        round_code="2018",
        census_vintage=2010,
        certification_status=DesignationStatus.TREASURY_CERTIFIED,
        designation_status=DesignationStatus.EFFECTIVE,
        effective_from=date(2017, 12, 22),
        effective_to=date(2028, 12, 31),
        tract_intervals_vary=True,
        source_id=CDFI_QOZ_2018_SOURCE.id,
        source_artifact_id=artifact_id,
        source_artifact_sha256=sha256,
        authority_uri=CDFI_QOZ_2018_SOURCE.terms_uri,
    )
    engine = sa.create_engine(TEST_DATABASE_URL)
    repository = PostgresOpportunityZoneRepository(engine, batch_size=1)
    adapter = adapter_for(content)
    try:
        with (
            repository.import_lock(),
            pytest.raises(OpportunityZonePersistenceError, match="already holds"),
            PostgresOpportunityZoneRepository(engine).import_lock(),
        ):
            pytest.fail("contending static import must not enter its critical section")
        with repository.import_lock():
            pass

        repository.register_source(CDFI_QOZ_2018_SOURCE, registered_at=now)
        repository.save_artifact(artifact)
        with adapter.open_archive(content, artifact_id=artifact_id) as dataset:
            first = repository.import_tracts(
                round_record=round_record,
                tracts=dataset.iter_tracts(),
                expected_tracts=2,
                expected_geometry_repairs=0,
                loaded_at=now,
            )
        with adapter.open_archive(content, artifact_id=artifact_id) as dataset:
            replay = repository.import_tracts(
                round_record=round_record,
                tracts=dataset.iter_tracts(),
                expected_tracts=2,
                expected_geometry_repairs=0,
                loaded_at=now,
            )

        assert first.inserted_tracts == 2
        assert replay.unchanged is True
        with engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    """
                    SELECT count(*) AS tract_count,
                           bool_and(ST_IsValid(geometry)) AS all_valid,
                           bool_and(ST_SRID(geometry) = 3857) AS correct_srid,
                           bool_and(ST_GeometryType(geometry) = 'ST_MultiPolygon') AS all_multi
                    FROM geo.opportunity_zone_tract
                    WHERE round_id = :round_id
                    """
                ),
                {"round_id": CDFI_QOZ_2018_ROUND_ID},
            ).one()
            assert tuple(row) == (2, True, True, True)
            assert (
                connection.scalar(
                    sa.text(
                        """
                    SELECT count(*) FROM pg_indexes
                    WHERE schemaname = 'geo'
                      AND indexname = 'ix_geo_oz_tract_geometry_gist'
                    """
                    )
                )
                == 1
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_tract WHERE round_id = :round_id"),
                {"round_id": CDFI_QOZ_2018_ROUND_ID},
            )
            connection.execute(
                sa.text("DELETE FROM geo.opportunity_zone_round WHERE id = :round_id"),
                {"round_id": CDFI_QOZ_2018_ROUND_ID},
            )
            connection.execute(
                sa.text("DELETE FROM raw.artifact WHERE id = :artifact_id"),
                {"artifact_id": artifact_id},
            )
            connection.execute(
                sa.text("DELETE FROM registry.source_definition WHERE id = :source_id"),
                {"source_id": CDFI_QOZ_2018_SOURCE.id},
            )
        engine.dispose()
