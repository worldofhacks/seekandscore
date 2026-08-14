"""Replay-safe PostGIS persistence for frozen Opportunity Zone geography."""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from seekandscore.acquisition.models import RawArtifact, SourceDescriptor
from seekandscore.acquisition.repository import raw_artifact_table
from seekandscore.geography.opportunity_zones.models import (
    ImportOutcome,
    OpportunityZoneImportRun,
    OpportunityZoneRound,
    OpportunityZoneTract,
)


class OpportunityZonePersistenceError(RuntimeError):
    """The database contains a partial/conflicting frozen layer or rejects its geometry."""


class OpportunityZoneRepository(Protocol):
    def is_ready(self) -> bool: ...

    def register_source(self, source: SourceDescriptor, *, registered_at: datetime) -> None: ...

    def save_artifact(self, artifact: RawArtifact) -> None: ...

    def save_run(self, run: OpportunityZoneImportRun) -> None: ...

    def import_tracts(
        self,
        *,
        round_record: OpportunityZoneRound,
        tracts: Iterable[OpportunityZoneTract],
        expected_tracts: int,
        expected_geometry_repairs: int,
        loaded_at: datetime,
    ) -> ImportOutcome: ...


class MemoryOpportunityZoneRepository:
    """Deterministic test repository with the same frozen-layer invariants."""

    def __init__(self) -> None:
        self.sources: dict[str, SourceDescriptor] = {}
        self.artifacts: dict[tuple[str, str], RawArtifact] = {}
        self.runs: dict[UUID, OpportunityZoneImportRun] = {}
        self.rounds: dict[str, OpportunityZoneRound] = {}
        self.tracts: dict[tuple[str, str], OpportunityZoneTract] = {}

    def is_ready(self) -> bool:
        return True

    def register_source(self, source: SourceDescriptor, *, registered_at: datetime) -> None:
        del registered_at
        self.sources.setdefault(source.id, source)

    def save_artifact(self, artifact: RawArtifact) -> None:
        self.artifacts.setdefault((artifact.source_id, artifact.sha256), artifact)

    def save_run(self, run: OpportunityZoneImportRun) -> None:
        self.runs[run.id] = run

    def import_tracts(
        self,
        *,
        round_record: OpportunityZoneRound,
        tracts: Iterable[OpportunityZoneTract],
        expected_tracts: int,
        expected_geometry_repairs: int,
        loaded_at: datetime,
    ) -> ImportOutcome:
        del loaded_at, expected_geometry_repairs
        materialized = tuple(tracts)
        _validate_tract_set(round_record, materialized, expected_tracts)
        existing_round = self.rounds.get(round_record.id)
        existing = {key: value for key, value in self.tracts.items() if key[0] == round_record.id}
        if existing_round is not None or existing:
            expected = {(item.round_id, item.tract_geoid): item for item in materialized}
            if existing_round != round_record or existing != expected:
                raise OpportunityZonePersistenceError(
                    "frozen Opportunity Zone layer conflicts with the reviewed artifact"
                )
            return ImportOutcome(
                inserted_tracts=0,
                total_tracts=expected_tracts,
                unchanged=True,
            )
        self.rounds[round_record.id] = round_record
        for tract in materialized:
            self.tracts[(tract.round_id, tract.tract_geoid)] = tract
        return ImportOutcome(
            inserted_tracts=len(materialized),
            total_tracts=len(materialized),
        )


metadata = sa.MetaData()

source_definition_table = sa.Table(
    "source_definition",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("descriptor", sa.JSON(), nullable=False),
    sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    schema="registry",
)

import_run_table = sa.Table(
    "opportunity_zone_import_run",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("source_id", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("activation_id", sa.Text(), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("source_artifact_id", sa.Uuid()),
    sa.Column("source_artifact_sha256", sa.String(64)),
    sa.Column("expected_tracts", sa.Integer(), nullable=False),
    sa.Column("imported_tracts", sa.Integer(), nullable=False),
    sa.Column("error_code", sa.Text()),
    sa.Column("error_detail", sa.Text()),
    schema="geo",
)


class PostgresOpportunityZoneRepository:
    def __init__(self, engine: Engine, *, batch_size: int = 250) -> None:
        self.engine = engine
        self.batch_size = batch_size

    def is_ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                return bool(connection.scalar(sa.text("SELECT 1")))
        except sa.exc.SQLAlchemyError:
            return False

    def register_source(self, source: SourceDescriptor, *, registered_at: datetime) -> None:
        statement = (
            pg_insert(source_definition_table)
            .values(
                id=source.id,
                descriptor=source.model_dump(mode="json"),
                registered_at=registered_at,
            )
            .on_conflict_do_nothing(index_elements=[source_definition_table.c.id])
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def save_artifact(self, artifact: RawArtifact) -> None:
        statement = (
            pg_insert(raw_artifact_table)
            .values(
                id=artifact.id,
                source_id=artifact.source_id,
                sha256=artifact.sha256,
                payload=artifact.model_dump(mode="json"),
                retrieved_at=artifact.retrieved_at,
            )
            .on_conflict_do_nothing(
                index_elements=[raw_artifact_table.c.source_id, raw_artifact_table.c.sha256]
            )
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def save_run(self, run: OpportunityZoneImportRun) -> None:
        statement = pg_insert(import_run_table).values(**run.model_dump(mode="python"))
        statement = statement.on_conflict_do_update(
            index_elements=[import_run_table.c.id],
            set_={
                column.name: getattr(statement.excluded, column.name)
                for column in import_run_table.c
                if column.name != "id"
            },
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def import_tracts(
        self,
        *,
        round_record: OpportunityZoneRound,
        tracts: Iterable[OpportunityZoneTract],
        expected_tracts: int,
        expected_geometry_repairs: int,
        loaded_at: datetime,
    ) -> ImportOutcome:
        with self.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    CREATE TEMPORARY TABLE oz_tract_stage (
                        round_id text NOT NULL,
                        tract_geoid varchar(11) NOT NULL,
                        census_vintage smallint NOT NULL,
                        certification_status text NOT NULL,
                        designation_status text NOT NULL,
                        effective_from date NOT NULL,
                        effective_from_precision text NOT NULL,
                        effective_to date NOT NULL,
                        state_name text NOT NULL,
                        county_name text NOT NULL,
                        source_artifact_id uuid NOT NULL,
                        source_artifact_sha256 varchar(64) NOT NULL,
                        source_geometry geometry(MULTIPOLYGON,3857) NOT NULL,
                        loaded_at timestamptz NOT NULL,
                        PRIMARY KEY (round_id, tract_geoid)
                    ) ON COMMIT DROP
                    """
                )
            )
            count = self._stage_tracts(
                connection,
                round_record=round_record,
                tracts=tracts,
                expected_tracts=expected_tracts,
                loaded_at=loaded_at,
            )
            invalid = int(
                connection.scalar(
                    sa.text(
                        """
                        SELECT count(*) FROM oz_tract_stage
                        WHERE ST_IsEmpty(source_geometry) OR NOT ST_IsValid(source_geometry)
                           OR ST_GeometryType(source_geometry) <> 'ST_MultiPolygon'
                        """
                    )
                )
                or 0
            )
            if invalid != expected_geometry_repairs:
                raise OpportunityZonePersistenceError(
                    "official archive geometry-repair count differs from the reviewed contract: "
                    f"expected {expected_geometry_repairs}, found {invalid}"
                )
            unrepairable = int(
                connection.scalar(
                    sa.text(
                        """
                        SELECT count(*) FROM oz_tract_stage
                        WHERE ST_IsEmpty(
                            ST_Multi(ST_CollectionExtract(ST_MakeValid(source_geometry), 3))
                        ) OR NOT ST_IsValid(
                            ST_Multi(ST_CollectionExtract(ST_MakeValid(source_geometry), 3))
                        )
                        """
                    )
                )
                or 0
            )
            if unrepairable:
                raise OpportunityZonePersistenceError(
                    f"{unrepairable} source geometries cannot be normalized to valid polygons"
                )

            existing_count = int(
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM geo.opportunity_zone_tract WHERE round_id = :round_id"
                    ),
                    {"round_id": round_record.id},
                )
                or 0
            )
            if existing_count:
                return self._verify_unchanged(
                    connection,
                    round_record=round_record,
                    expected_tracts=expected_tracts,
                )

            existing_round = connection.scalar(
                sa.text("SELECT id FROM geo.opportunity_zone_round WHERE id = :round_id"),
                {"round_id": round_record.id},
            )
            if existing_round is not None:
                raise OpportunityZonePersistenceError(
                    "frozen Opportunity Zone round exists without its complete tract set"
                )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO geo.opportunity_zone_round (
                        id, round_code, census_vintage, certification_status,
                        designation_status, effective_from, effective_to,
                        tract_intervals_vary, source_id,
                        source_artifact_id, source_artifact_sha256, authority_uri, loaded_at
                    ) VALUES (
                        :id, :round_code, :census_vintage, :certification_status,
                        :designation_status, :effective_from, :effective_to,
                        :tract_intervals_vary, :source_id,
                        :source_artifact_id, :source_artifact_sha256, :authority_uri, :loaded_at
                    )
                    """
                ),
                {
                    **round_record.model_dump(mode="python"),
                    "certification_status": round_record.certification_status.value,
                    "designation_status": round_record.designation_status.value,
                    "loaded_at": loaded_at,
                },
            )
            result = connection.execute(
                sa.text(
                    """
                    INSERT INTO geo.opportunity_zone_tract (
                        round_id, tract_geoid, census_vintage, certification_status,
                        designation_status, effective_from, effective_from_precision, effective_to,
                        state_name, county_name, source_artifact_id,
                        source_artifact_sha256, geometry, geometry_was_repaired,
                        geometry_repair_method, loaded_at
                    )
                    SELECT round_id, tract_geoid, census_vintage, certification_status,
                           designation_status, effective_from,
                           effective_from_precision, effective_to,
                           state_name, county_name, source_artifact_id,
                           source_artifact_sha256,
                           CASE WHEN ST_IsValid(source_geometry) THEN source_geometry
                                ELSE ST_Multi(
                                    ST_CollectionExtract(ST_MakeValid(source_geometry), 3)
                                ) END,
                           NOT ST_IsValid(source_geometry),
                           CASE WHEN ST_IsValid(source_geometry) THEN NULL
                                ELSE 'postgis_st_makevalid_collection_extract_v1' END,
                           loaded_at
                    FROM oz_tract_stage
                    """
                )
            )
            if result.rowcount != count:
                raise OpportunityZonePersistenceError(
                    "PostGIS did not insert the complete tract set"
                )
            return ImportOutcome(inserted_tracts=count, total_tracts=count)

    def _stage_tracts(
        self,
        connection: sa.Connection,
        *,
        round_record: OpportunityZoneRound,
        tracts: Iterable[OpportunityZoneTract],
        expected_tracts: int,
        loaded_at: datetime,
    ) -> int:
        insert = sa.text(
            """
            INSERT INTO oz_tract_stage (
                round_id, tract_geoid, census_vintage, certification_status,
                designation_status, effective_from, effective_from_precision, effective_to,
                state_name, county_name, source_artifact_id, source_artifact_sha256,
                source_geometry, loaded_at
            ) VALUES (
                :round_id, :tract_geoid, :census_vintage, :certification_status,
                :designation_status, :effective_from, :effective_from_precision, :effective_to,
                :state_name, :county_name, :source_artifact_id, :source_artifact_sha256,
                ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geometry_geojson), :geometry_srid)),
                :loaded_at
            )
            """
        )
        seen: set[str] = set()
        batch: list[dict[str, object]] = []
        count = 0
        for tract in tracts:
            _validate_tract(round_record, tract)
            if tract.tract_geoid in seen:
                raise OpportunityZonePersistenceError(
                    f"duplicate tract GEOID during database import: {tract.tract_geoid}"
                )
            seen.add(tract.tract_geoid)
            batch.append(
                {
                    **tract.model_dump(mode="python"),
                    "certification_status": tract.certification_status.value,
                    "designation_status": tract.designation_status.value,
                    "effective_from_precision": tract.effective_from_precision.value,
                    "loaded_at": loaded_at,
                }
            )
            count += 1
            if len(batch) == self.batch_size:
                connection.execute(insert, batch)
                batch.clear()
        if batch:
            connection.execute(insert, batch)
        if count != expected_tracts or len(seen) != expected_tracts:
            raise OpportunityZonePersistenceError(
                f"expected {expected_tracts} unique tracts, received {count}"
            )
        return count

    def _verify_unchanged(
        self,
        connection: sa.Connection,
        *,
        round_record: OpportunityZoneRound,
        expected_tracts: int,
    ) -> ImportOutcome:
        round_matches = int(
            connection.scalar(
                sa.text(
                    """
                    SELECT count(*) FROM geo.opportunity_zone_round
                    WHERE id = :id
                      AND round_code = :round_code
                      AND census_vintage = :census_vintage
                      AND certification_status = :certification_status
                      AND designation_status = :designation_status
                      AND effective_from = :effective_from
                      AND effective_to = :effective_to
                      AND tract_intervals_vary = :tract_intervals_vary
                      AND source_id = :source_id
                      AND source_artifact_id = :source_artifact_id
                      AND source_artifact_sha256 = :source_artifact_sha256
                      AND authority_uri = :authority_uri
                    """
                ),
                {
                    **round_record.model_dump(mode="python"),
                    "certification_status": round_record.certification_status.value,
                    "designation_status": round_record.designation_status.value,
                },
            )
            or 0
        )
        if round_matches != 1:
            raise OpportunityZonePersistenceError(
                "existing frozen Opportunity Zone round metadata conflicts with the artifact"
            )
        if (
            int(
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM geo.opportunity_zone_tract WHERE round_id = :round_id"
                    ),
                    {"round_id": round_record.id},
                )
                or 0
            )
            != expected_tracts
        ):
            raise OpportunityZonePersistenceError(
                "existing frozen Opportunity Zone layer is incomplete"
            )
        differences = int(
            connection.scalar(
                sa.text(
                    """
                    SELECT count(*)
                    FROM oz_tract_stage AS staged
                    FULL OUTER JOIN geo.opportunity_zone_tract AS stored
                      ON stored.round_id = staged.round_id
                     AND stored.tract_geoid = staged.tract_geoid
                    WHERE (stored.round_id = :round_id OR staged.round_id = :round_id)
                      AND (
                           stored.tract_geoid IS NULL OR staged.tract_geoid IS NULL
                        OR stored.census_vintage <> staged.census_vintage
                        OR stored.certification_status <> staged.certification_status
                        OR stored.designation_status <> staged.designation_status
                        OR stored.effective_from <> staged.effective_from
                        OR stored.effective_from_precision <> staged.effective_from_precision
                        OR stored.effective_to <> staged.effective_to
                        OR stored.state_name <> staged.state_name
                        OR stored.county_name <> staged.county_name
                        OR stored.source_artifact_id <> staged.source_artifact_id
                        OR stored.source_artifact_sha256 <> staged.source_artifact_sha256
                        OR NOT ST_Equals(
                            stored.geometry,
                            CASE WHEN ST_IsValid(staged.source_geometry)
                                 THEN staged.source_geometry
                                 ELSE ST_Multi(
                                     ST_CollectionExtract(
                                         ST_MakeValid(staged.source_geometry), 3
                                     )
                                 ) END
                        )
                        OR stored.geometry_was_repaired <> NOT ST_IsValid(staged.source_geometry)
                        OR stored.geometry_repair_method IS DISTINCT FROM
                           CASE WHEN ST_IsValid(staged.source_geometry) THEN NULL
                                ELSE 'postgis_st_makevalid_collection_extract_v1' END
                      )
                    """
                ),
                {"round_id": round_record.id},
            )
            or 0
        )
        if differences:
            raise OpportunityZonePersistenceError(
                "existing frozen Opportunity Zone layer differs from the reviewed artifact"
            )
        return ImportOutcome(
            inserted_tracts=0,
            total_tracts=expected_tracts,
            unchanged=True,
        )


def _validate_tract_set(
    round_record: OpportunityZoneRound,
    tracts: tuple[OpportunityZoneTract, ...],
    expected_tracts: int,
) -> None:
    if len(tracts) != expected_tracts:
        raise OpportunityZonePersistenceError(
            f"expected {expected_tracts} unique tracts, received {len(tracts)}"
        )
    seen: set[str] = set()
    for tract in tracts:
        _validate_tract(round_record, tract)
        if tract.tract_geoid in seen:
            raise OpportunityZonePersistenceError(f"duplicate tract GEOID: {tract.tract_geoid}")
        seen.add(tract.tract_geoid)


def _validate_tract(
    round_record: OpportunityZoneRound,
    tract: OpportunityZoneTract,
) -> None:
    if (
        tract.round_id != round_record.id
        or tract.census_vintage != round_record.census_vintage
        or tract.certification_status is not round_record.certification_status
        or tract.designation_status is not round_record.designation_status
        or tract.effective_from < round_record.effective_from
        or tract.effective_to > round_record.effective_to
        or tract.source_artifact_id != round_record.source_artifact_id
        or tract.source_artifact_sha256 != round_record.source_artifact_sha256
    ):
        raise OpportunityZonePersistenceError(
            f"tract {tract.tract_geoid} does not match its designation round lineage"
        )
