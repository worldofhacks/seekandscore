"""Synthetic candidate read endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from seekandscore.api.dependencies import get_container
from seekandscore.bootstrap import AppContainer
from seekandscore.readmodels import CandidatePage, CandidateReadModel
from seekandscore.readmodels.candidates import InvalidCursorError
from seekandscore.version import READ_MODEL_VERSION

router = APIRouter(prefix="/candidates", tags=["candidates"])
Container = Annotated[AppContainer, Depends(get_container)]


@router.get("", response_model=CandidatePage)
def list_candidates(
    container: Container,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
    if_none_match: Annotated[str | None, Header()] = None,
) -> CandidatePage | Response:
    etag = f'"{READ_MODEL_VERSION}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    try:
        page = container.candidates.list(
            limit=limit,
            cursor=cursor,
            dataset_mode=container.settings.dataset_mode,
        )
    except InvalidCursorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=60"
    return page


@router.get("/{candidate_id}", response_model=CandidateReadModel)
def get_candidate(candidate_id: UUID, container: Container) -> CandidateReadModel:
    candidate = container.candidates.get(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate
