"""Durable Postgres repository and deterministic in-memory test repository."""

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from seekandscore.acquisition.models import (
    NormalizedParcelObservation,
    QuarantinedRecord,
    RawArtifact,
    SourceRun,
    SourceRunProfile,
)


class AcquisitionRepository(Protocol):
    def is_ready(self) -> bool: ...

    def latest_run(self, source_id: str) -> SourceRun | None: ...

    def latest_complete_run(
        self, source_id: str, *, run_profile: SourceRunProfile
    ) -> SourceRun | None: ...

    def latest_artifact(
        self, source_id: str, *, artifact_ids: tuple[UUID, ...] | None = None
    ) -> RawArtifact | None: ...

    def save_run(self, run: SourceRun) -> None: ...

    def save_artifact(self, artifact: RawArtifact) -> None: ...

    def save_observations(self, observations: Iterable[NormalizedParcelObservation]) -> int: ...

    def save_quarantine(self, records: Iterable[QuarantinedRecord]) -> int: ...

    def list_latest_observations(
        self,
        *,
        limit: int,
        offset: int = 0,
        artifact_ids: tuple[UUID, ...] | None = None,
        cities: tuple[str, ...] | None = None,
    ) -> tuple[NormalizedParcelObservation, ...]: ...

    def count_latest_observations(
        self,
        *,
        artifact_ids: tuple[UUID, ...] | None = None,
        cities: tuple[str, ...] | None = None,
    ) -> int: ...


class MemoryAcquisitionRepository:
    def __init__(self) -> None:
        self.runs: dict[object, SourceRun] = {}
        self.artifacts: dict[object, RawArtifact] = {}
        self.observations: dict[object, NormalizedParcelObservation] = {}
        self.quarantine: dict[object, QuarantinedRecord] = {}

    def is_ready(self) -> bool:
        return True

    def latest_run(self, source_id: str) -> SourceRun | None:
        matches = [run for run in self.runs.values() if run.source_id == source_id]
        return max(matches, key=lambda run: (run.started_at, str(run.id))) if matches else None

    def latest_complete_run(
        self, source_id: str, *, run_profile: SourceRunProfile
    ) -> SourceRun | None:
        matches = [
            run
            for run in self.runs.values()
            if run.source_id == source_id
            and run.run_profile is run_profile
            and run.is_complete_cohort
        ]
        return max(matches, key=lambda run: (run.started_at, str(run.id))) if matches else None

    def latest_artifact(
        self, source_id: str, *, artifact_ids: tuple[UUID, ...] | None = None
    ) -> RawArtifact | None:
        selected = frozenset(artifact_ids) if artifact_ids is not None else None
        matches = [item for item in self.artifacts.values() if item.source_id == source_id]
        if selected is not None:
            matches = [item for item in matches if item.id in selected]
        return max(matches, key=lambda item: (item.retrieved_at, str(item.id))) if matches else None

    def save_run(self, run: SourceRun) -> None:
        self.runs[run.id] = run

    def save_artifact(self, artifact: RawArtifact) -> None:
        existing = next(
            (
                item
                for item in self.artifacts.values()
                if item.source_id == artifact.source_id and item.sha256 == artifact.sha256
            ),
            None,
        )
        if existing is not None and existing.model_dump() != artifact.model_dump():
            # Content identity wins; its first retrieval metadata is immutable.
            return
        self.artifacts.setdefault(artifact.id, artifact)

    def save_observations(self, observations: Iterable[NormalizedParcelObservation]) -> int:
        inserted = 0
        for observation in observations:
            if observation.id not in self.observations:
                self.observations[observation.id] = observation
                inserted += 1
        return inserted

    def save_quarantine(self, records: Iterable[QuarantinedRecord]) -> int:
        inserted = 0
        for record in records:
            if record.id not in self.quarantine:
                self.quarantine[record.id] = record
                inserted += 1
        return inserted

    def list_latest_observations(
        self,
        *,
        limit: int,
        offset: int = 0,
        artifact_ids: tuple[UUID, ...] | None = None,
        cities: tuple[str, ...] | None = None,
    ) -> tuple[NormalizedParcelObservation, ...]:
        selected_artifacts = frozenset(artifact_ids) if artifact_ids is not None else None
        selected_cities = frozenset(cities) if cities is not None else None
        latest_by_parcel: dict[str, NormalizedParcelObservation] = {}
        for item in self.observations.values():
            if selected_artifacts is not None and item.artifact_id not in selected_artifacts:
                continue
            if selected_cities is not None and item.situs_city not in selected_cities:
                continue
            current = latest_by_parcel.get(item.local_parcel_id)
            if current is None or item.observed_at > current.observed_at:
                latest_by_parcel[item.local_parcel_id] = item
        ordered = sorted(
            latest_by_parcel.values(),
            key=lambda item: (
                -(item.tcad_acres or item.gis_acres or 0),
                item.local_parcel_id,
            ),
        )
        return tuple(ordered[offset : offset + limit])

    def count_latest_observations(
        self,
        *,
        artifact_ids: tuple[UUID, ...] | None = None,
        cities: tuple[str, ...] | None = None,
    ) -> int:
        selected_artifacts = frozenset(artifact_ids) if artifact_ids is not None else None
        selected_cities = frozenset(cities) if cities is not None else None
        return len(
            {
                item.local_parcel_id
                for item in self.observations.values()
                if (selected_artifacts is None or item.artifact_id in selected_artifacts)
                and (selected_cities is None or item.situs_city in selected_cities)
            }
        )


metadata = sa.MetaData()

source_run_table = sa.Table(
    "source_run",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("source_id", sa.Text(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    schema="registry",
)

raw_artifact_table = sa.Table(
    "artifact",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("source_id", sa.Text(), nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    schema="raw",
)

observation_table = sa.Table(
    "parcel_observation",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("source_id", sa.Text(), nullable=False),
    sa.Column("source_record_id", sa.Text(), nullable=False),
    sa.Column("artifact_id", sa.Uuid(), nullable=False),
    sa.Column("artifact_sha256", sa.String(64), nullable=False),
    sa.Column("parser_version", sa.Text(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    schema="observation",
)

quarantine_table = sa.Table(
    "quarantined_record",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("source_id", sa.Text(), nullable=False),
    sa.Column("artifact_id", sa.Uuid(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    schema="observation",
)


class PostgresAcquisitionRepository:
    """Postgres JSON-envelope repository preserving versioned contracts exactly."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def is_ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                for table in (source_run_table, raw_artifact_table, observation_table):
                    connection.execute(sa.select(table.c.id).limit(0))
        except sa.exc.SQLAlchemyError:
            return False
        return True

    def latest_run(self, source_id: str) -> SourceRun | None:
        statement = (
            sa.select(source_run_table.c.payload)
            .where(source_run_table.c.source_id == source_id)
            .order_by(source_run_table.c.started_at.desc(), source_run_table.c.id.desc())
            .limit(1)
        )
        with self.engine.connect() as connection:
            payload = connection.scalar(statement)
        return SourceRun.model_validate(payload) if payload else None

    def latest_complete_run(
        self, source_id: str, *, run_profile: SourceRunProfile
    ) -> SourceRun | None:
        statement = (
            sa.select(source_run_table.c.payload)
            .where(
                source_run_table.c.source_id == source_id,
                source_run_table.c.payload["run_profile"].astext == run_profile.value,
                source_run_table.c.payload["status"].astext.in_(
                    ("succeeded", "succeeded_unchanged")
                ),
                source_run_table.c.payload["partial"].astext == "false",
            )
            .order_by(source_run_table.c.started_at.desc(), source_run_table.c.id.desc())
        )
        with self.engine.connect() as connection:
            payloads = connection.scalars(statement).all()
        for payload in payloads:
            run = SourceRun.model_validate(payload)
            if run.is_complete_cohort:
                return run
        return None

    def latest_artifact(
        self, source_id: str, *, artifact_ids: tuple[UUID, ...] | None = None
    ) -> RawArtifact | None:
        if artifact_ids == ():
            return None
        statement = sa.select(raw_artifact_table.c.payload).where(
            raw_artifact_table.c.source_id == source_id
        )
        if artifact_ids is not None:
            statement = statement.where(raw_artifact_table.c.id.in_(artifact_ids))
        statement = statement.order_by(
            raw_artifact_table.c.retrieved_at.desc(), raw_artifact_table.c.id.desc()
        ).limit(1)
        with self.engine.connect() as connection:
            payload = connection.scalar(statement)
        return RawArtifact.model_validate(payload) if payload else None

    def save_run(self, run: SourceRun) -> None:
        statement = pg_insert(source_run_table).values(
            id=run.id,
            source_id=run.source_id,
            payload=run.model_dump(mode="json"),
            started_at=run.started_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[source_run_table.c.id],
            set_={"payload": statement.excluded.payload},
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def save_artifact(self, artifact: RawArtifact) -> None:
        statement = pg_insert(raw_artifact_table).values(
            id=artifact.id,
            source_id=artifact.source_id,
            sha256=artifact.sha256,
            payload=artifact.model_dump(mode="json"),
            retrieved_at=artifact.retrieved_at,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=[raw_artifact_table.c.source_id, raw_artifact_table.c.sha256]
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def save_observations(self, observations: Iterable[NormalizedParcelObservation]) -> int:
        values = [
            {
                "id": item.id,
                "source_id": item.source_id,
                "source_record_id": item.source_record_id,
                "artifact_id": item.artifact_id,
                "artifact_sha256": item.artifact_sha256,
                "parser_version": item.parser_version,
                "payload": item.model_dump(mode="json"),
            }
            for item in observations
        ]
        if not values:
            return 0
        statement = (
            pg_insert(observation_table)
            .values(values)
            .on_conflict_do_nothing()
            .returning(observation_table.c.id)
        )
        with self.engine.begin() as connection:
            result = connection.execute(statement)
            inserted_ids = tuple(result.scalars())
        return len(inserted_ids)

    def save_quarantine(self, records: Iterable[QuarantinedRecord]) -> int:
        values = [
            {
                "id": item.id,
                "source_id": item.source_id,
                "artifact_id": item.artifact_id,
                "payload": item.model_dump(mode="json"),
            }
            for item in records
        ]
        if not values:
            return 0
        statement = (
            pg_insert(quarantine_table)
            .values(values)
            .on_conflict_do_nothing()
            .returning(quarantine_table.c.id)
        )
        with self.engine.begin() as connection:
            result = connection.execute(statement)
            inserted_ids = tuple(result.scalars())
        return len(inserted_ids)

    def list_latest_observations(
        self,
        *,
        limit: int,
        offset: int = 0,
        artifact_ids: tuple[UUID, ...] | None = None,
        cities: tuple[str, ...] | None = None,
    ) -> tuple[NormalizedParcelObservation, ...]:
        if artifact_ids == ():
            return ()
        filters = [observation_table.c.source_id == "travis_tcad_parcels"]
        if artifact_ids is not None:
            filters.append(observation_table.c.artifact_id.in_(artifact_ids))
        if cities is not None:
            filters.append(observation_table.c.payload["situs_city"].astext.in_(cities))
        ranked = (
            sa.select(
                observation_table.c.payload,
                sa.func.row_number()
                .over(
                    partition_by=observation_table.c.source_record_id,
                    order_by=sa.cast(
                        observation_table.c.payload["observed_at"].astext,
                        sa.DateTime(timezone=True),
                    ).desc(),
                )
                .label("version_rank"),
            )
            .where(*filters)
            .cte("ranked_observations")
        )
        statement = (
            sa.select(ranked.c.payload)
            .where(ranked.c.version_rank == 1)
            .order_by(
                sa.cast(
                    ranked.c.payload["tcad_acres"].astext,
                    sa.Float(),
                )
                .desc()
                .nullslast(),
                ranked.c.payload["local_parcel_id"].astext,
            )
            .limit(limit)
            .offset(offset)
        )
        with self.engine.connect() as connection:
            rows = connection.scalars(statement).all()
        return tuple(NormalizedParcelObservation.model_validate(row) for row in rows)

    def count_latest_observations(
        self,
        *,
        artifact_ids: tuple[UUID, ...] | None = None,
        cities: tuple[str, ...] | None = None,
    ) -> int:
        if artifact_ids == ():
            return 0
        statement = sa.select(
            sa.func.count(sa.distinct(observation_table.c.source_record_id))
        ).where(observation_table.c.source_id == "travis_tcad_parcels")
        if artifact_ids is not None:
            statement = statement.where(observation_table.c.artifact_id.in_(artifact_ids))
        if cities is not None:
            statement = statement.where(
                observation_table.c.payload["situs_city"].astext.in_(cities)
            )
        with self.engine.connect() as connection:
            return int(connection.scalar(statement) or 0)
