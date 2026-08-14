"""Research-case persistence with organization isolation and append-only revisions."""

from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from seekandscore.deal.models import ResearchCase, ResearchStatus


class ResearchCaseRepository(Protocol):
    def is_ready(self) -> bool: ...

    def get(self, organization_id: UUID, case_id: UUID) -> ResearchCase | None: ...

    def get_by_candidate(
        self, organization_id: UUID, candidate_id: UUID
    ) -> ResearchCase | None: ...

    def list(
        self,
        organization_id: UUID,
        *,
        status: ResearchStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[tuple[ResearchCase, ...], int]: ...

    def create(self, research_case: ResearchCase) -> tuple[ResearchCase, bool]: ...

    def update(
        self,
        research_case: ResearchCase,
        *,
        expected_version: int,
    ) -> ResearchCase | None: ...


class MemoryResearchCaseRepository:
    """Deterministic repository used only by unit tests."""

    def __init__(self) -> None:
        self.cases: dict[tuple[UUID, UUID], ResearchCase] = {}
        self.revisions: list[ResearchCase] = []

    def is_ready(self) -> bool:
        return True

    def get(self, organization_id: UUID, case_id: UUID) -> ResearchCase | None:
        return self.cases.get((organization_id, case_id))

    def get_by_candidate(self, organization_id: UUID, candidate_id: UUID) -> ResearchCase | None:
        return next(
            (
                item
                for (org_id, _), item in self.cases.items()
                if org_id == organization_id and item.candidate_id == candidate_id
            ),
            None,
        )

    def list(
        self,
        organization_id: UUID,
        *,
        status: ResearchStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[tuple[ResearchCase, ...], int]:
        matches = [
            item
            for (org_id, _), item in self.cases.items()
            if org_id == organization_id and (status is None or item.status is status)
        ]
        matches.sort(key=lambda item: (item.updated_at, str(item.id)), reverse=True)
        return tuple(matches[offset : offset + limit]), len(matches)

    def create(self, research_case: ResearchCase) -> tuple[ResearchCase, bool]:
        existing = self.get_by_candidate(research_case.organization_id, research_case.candidate_id)
        if existing is not None:
            return existing, False
        self.cases[(research_case.organization_id, research_case.id)] = research_case
        self.revisions.append(research_case)
        return research_case, True

    def update(
        self,
        research_case: ResearchCase,
        *,
        expected_version: int,
    ) -> ResearchCase | None:
        key = (research_case.organization_id, research_case.id)
        current = self.cases.get(key)
        if current is None or current.version != expected_version:
            return None
        self.cases[key] = research_case
        self.revisions.append(research_case)
        return research_case


metadata = sa.MetaData()

research_case_table = sa.Table(
    "research_case",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("organization_id", sa.Uuid(), nullable=False),
    sa.Column("candidate_id", sa.Uuid(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    schema="deal",
)

research_case_revision_table = sa.Table(
    "research_case_revision",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("organization_id", sa.Uuid(), nullable=False),
    sa.Column("research_case_id", sa.Uuid(), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    schema="deal",
)

audit_event_table = sa.Table(
    "audit_event",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("organization_id", sa.Uuid(), nullable=False),
    sa.Column("actor_id", sa.Uuid(), nullable=True),
    sa.Column("event_type", sa.Text(), nullable=False),
    sa.Column("subject_type", sa.Text(), nullable=False),
    sa.Column("subject_id", sa.Text(), nullable=False),
    sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("details", sa.JSON(), nullable=False),
    schema="platform",
)


class PostgresResearchCaseRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def is_ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(sa.select(research_case_table.c.id).limit(0))
        except sa.exc.SQLAlchemyError:
            return False
        return True

    def get(self, organization_id: UUID, case_id: UUID) -> ResearchCase | None:
        statement = sa.select(research_case_table.c.payload).where(
            research_case_table.c.organization_id == organization_id,
            research_case_table.c.id == case_id,
        )
        with self.engine.connect() as connection:
            payload = connection.scalar(statement)
        return ResearchCase.model_validate(payload) if payload else None

    def get_by_candidate(self, organization_id: UUID, candidate_id: UUID) -> ResearchCase | None:
        statement = sa.select(research_case_table.c.payload).where(
            research_case_table.c.organization_id == organization_id,
            research_case_table.c.candidate_id == candidate_id,
        )
        with self.engine.connect() as connection:
            payload = connection.scalar(statement)
        return ResearchCase.model_validate(payload) if payload else None

    def list(
        self,
        organization_id: UUID,
        *,
        status: ResearchStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[tuple[ResearchCase, ...], int]:
        filters = [research_case_table.c.organization_id == organization_id]
        if status is not None:
            filters.append(research_case_table.c.status == status.value)
        statement = (
            sa.select(research_case_table.c.payload)
            .where(*filters)
            .order_by(research_case_table.c.updated_at.desc(), research_case_table.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = (
            sa.select(sa.func.count()).select_from(research_case_table).where(*filters)
        )
        with self.engine.connect() as connection:
            payloads = connection.scalars(statement).all()
            total = int(connection.scalar(count_statement) or 0)
        return tuple(ResearchCase.model_validate(item) for item in payloads), total

    def create(self, research_case: ResearchCase) -> tuple[ResearchCase, bool]:
        statement = (
            pg_insert(research_case_table)
            .values(
                id=research_case.id,
                organization_id=research_case.organization_id,
                candidate_id=research_case.candidate_id,
                status=research_case.status.value,
                version=research_case.version,
                payload=research_case.model_dump(mode="json"),
                updated_at=research_case.updated_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    research_case_table.c.organization_id,
                    research_case_table.c.candidate_id,
                ]
            )
            .returning(research_case_table.c.id)
        )
        with self.engine.begin() as connection:
            inserted_id = connection.scalar(statement)
            if inserted_id is not None:
                return research_case, True
        existing = self.get_by_candidate(research_case.organization_id, research_case.candidate_id)
        if existing is None:  # pragma: no cover - defensive database race guard
            raise RuntimeError("research case conflict did not resolve to a durable row")
        return existing, False

    def update(
        self,
        research_case: ResearchCase,
        *,
        expected_version: int,
    ) -> ResearchCase | None:
        statement = (
            sa.update(research_case_table)
            .where(
                research_case_table.c.id == research_case.id,
                research_case_table.c.organization_id == research_case.organization_id,
                research_case_table.c.version == expected_version,
            )
            .values(
                status=research_case.status.value,
                version=research_case.version,
                payload=research_case.model_dump(mode="json"),
                updated_at=research_case.updated_at,
            )
            .returning(research_case_table.c.payload)
        )
        with self.engine.begin() as connection:
            payload = connection.scalar(statement)
            if payload is None:
                return None
        return ResearchCase.model_validate(payload)
