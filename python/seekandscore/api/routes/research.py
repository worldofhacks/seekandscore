"""Authenticated saved-research and evidence-dossier endpoints."""

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from seekandscore.api.dependencies import get_container
from seekandscore.api.research_auth import ResearchActor, require_research_actor
from seekandscore.bootstrap import AppContainer
from seekandscore.deal import (
    CandidateDossier,
    ResearchCase,
    ResearchCaseConflictError,
    ResearchCaseNotFoundError,
    ResearchCasePage,
    ResearchCaseTransitionError,
    ResearchStatus,
)
from seekandscore.deal.service import ResearchCaseService
from seekandscore.readmodels import CandidateReadUnavailableError
from seekandscore.readmodels.candidates import CandidateReadModel

router = APIRouter(tags=["research"])
Container = Annotated[AppContainer, Depends(get_container)]
Actor = Annotated[ResearchActor, Depends(require_research_actor)]


class ResearchCaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResearchStatus = ResearchStatus.WATCHING
    operator_note: str | None = Field(default=None, max_length=4000)
    next_action: str | None = Field(default=None, max_length=500)


class ResearchCasePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResearchStatus | None = None
    operator_note: str | None = Field(default=None, max_length=4000)
    next_action: str | None = Field(default=None, max_length=500)


@router.get("/research-cases", response_model=ResearchCasePage)
def list_research_cases(
    container: Container,
    actor: Actor,
    response: Response,
    status_filter: Annotated[ResearchStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> ResearchCasePage:
    _set_private_headers(response)
    service = _service(container)
    try:
        return service.list(
            actor.organization_id,
            status=status_filter,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/candidates/{candidate_id}/dossier", response_model=CandidateDossier)
def get_candidate_dossier(
    candidate_id: UUID,
    container: Container,
    actor: Actor,
    response: Response,
) -> CandidateDossier:
    _set_private_headers(response)
    candidate = _candidate(container, candidate_id)
    return _service(container).dossier(
        organization_id=actor.organization_id,
        candidate=candidate,
    )


@router.put("/candidates/{candidate_id}/research-case", response_model=ResearchCase)
def create_research_case(
    candidate_id: UUID,
    payload: ResearchCaseCreateRequest,
    container: Container,
    actor: Actor,
    response: Response,
) -> ResearchCase:
    candidate = _candidate(container, candidate_id)
    research_case, created = _service(container).create(
        organization_id=actor.organization_id,
        actor_id=actor.actor_id,
        candidate=candidate,
        status=payload.status,
        operator_note=payload.operator_note,
        next_action=payload.next_action,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["ETag"] = f'"{research_case.version}"'
    _set_private_headers(response)
    return research_case


@router.patch("/research-cases/{case_id}", response_model=ResearchCase)
def update_research_case(
    case_id: UUID,
    payload: ResearchCasePatchRequest,
    container: Container,
    actor: Actor,
    response: Response,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ResearchCase:
    expected_version = _expected_version(if_match)
    service = _service(container)
    try:
        research_case = service.update(
            organization_id=actor.organization_id,
            actor_id=actor.actor_id,
            case_id=case_id,
            expected_version=expected_version,
            status=payload.status,
            operator_note=payload.operator_note,
            next_action=payload.next_action,
            update_note="operator_note" in payload.model_fields_set,
            update_next_action="next_action" in payload.model_fields_set,
        )
    except ResearchCaseNotFoundError as error:
        raise HTTPException(status_code=404, detail="Research case not found") from error
    except ResearchCaseConflictError as error:
        raise HTTPException(status_code=412, detail=str(error)) from error
    except ResearchCaseTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    response.headers["ETag"] = f'"{research_case.version}"'
    _set_private_headers(response)
    return research_case


def _candidate(container: AppContainer, candidate_id: UUID) -> CandidateReadModel:
    try:
        candidate = container.candidates.get(candidate_id)
    except CandidateReadUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


def _service(container: AppContainer) -> ResearchCaseService:
    if container.research is None or not container.research.is_ready():
        raise HTTPException(status_code=503, detail="Saved research store is unavailable.")
    return container.research


def _expected_version(if_match: str | None) -> int:
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match is required")
    match = re.fullmatch(r'"([1-9][0-9]{0,9})"', if_match.strip())
    if match is None:
        raise HTTPException(
            status_code=400,
            detail="If-Match must be a strong quoted positive case version",
        )
    version = int(match.group(1))
    if version > 2_147_483_647:
        raise HTTPException(
            status_code=400,
            detail="If-Match case version exceeds the supported range",
        )
    return version


def _set_private_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
