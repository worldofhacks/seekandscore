"""Source descriptor, run, freshness, and provenance endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from seekandscore.acquisition.models import SourceDescriptor, SourceRun, SourceRunStatus
from seekandscore.api.dependencies import get_container
from seekandscore.bootstrap import AppContainer
from seekandscore.registry import SourceFreshness

router = APIRouter(prefix="/sources", tags=["sources"])
Container = Annotated[AppContainer, Depends(get_container)]


class SourceStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: SourceDescriptor
    freshness: SourceFreshness
    latest_run: "SourceRunSummary | None"


class SourceRunSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: SourceRunStatus
    started_at: datetime
    completed_at: datetime | None
    records_fetched: int
    observations_created: int
    records_quarantined: int
    partial: bool


@router.get("", response_model=tuple[SourceDescriptor, ...])
def list_sources(container: Container) -> tuple[SourceDescriptor, ...]:
    return container.sources.list()


@router.get("/{source_id}", response_model=SourceStatusResponse)
def get_source(source_id: str, container: Container) -> SourceStatusResponse:
    source = container.sources.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    latest_run = _latest_run(container, source_id)
    return SourceStatusResponse(
        source=source,
        freshness=container.sources.freshness(source_id, latest_run),
        latest_run=(
            SourceRunSummary(
                status=latest_run.status,
                started_at=latest_run.started_at,
                completed_at=latest_run.completed_at,
                records_fetched=latest_run.records_fetched,
                observations_created=latest_run.observations_created,
                records_quarantined=latest_run.records_quarantined,
                partial=latest_run.partial,
            )
            if latest_run
            else None
        ),
    )


def _latest_run(container: AppContainer, source_id: str) -> SourceRun | None:
    if container.source_runs is None:
        return None
    return container.source_runs.latest_run(source_id)
