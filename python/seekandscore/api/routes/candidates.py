"""Live candidate read endpoints."""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from seekandscore.api.dependencies import get_container
from seekandscore.bootstrap import AppContainer
from seekandscore.readmodels import (
    CandidatePage,
    CandidateReadModel,
    CandidateReadUnavailableError,
)
from seekandscore.readmodels.candidates import CandidateCity, InvalidCursorError
from seekandscore.version import READ_MODEL_VERSION

router = APIRouter(prefix="/candidates", tags=["candidates"])
Container = Annotated[AppContainer, Depends(get_container)]


@router.get("", response_model=CandidatePage)
def list_candidates(
    container: Container,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    city: Annotated[CandidateCity | None, Query()] = None,
    min_acres: Annotated[float | None, Query(ge=0, allow_inf_nan=False)] = None,
    max_acres: Annotated[float | None, Query(ge=0, allow_inf_nan=False)] = None,
    if_none_match: Annotated[str | None, Header()] = None,
) -> CandidatePage | Response:
    if min_acres is not None and max_acres is not None and min_acres > max_acres:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="min_acres must be less than or equal to max_acres",
        )
    try:
        page = container.candidates.list(
            limit=limit,
            cursor=cursor,
            dataset_mode=container.settings.dataset_mode,
            q=q,
            city=city.value if city is not None else None,
            min_acres=min_acres,
            max_acres=max_acres,
        )
    except InvalidCursorError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if page.dataset_status == "error":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["Cache-Control"] = "no-store"
        return page
    page_digest = hashlib.sha256(page.model_dump_json().encode()).hexdigest()[:24]
    etag = f'"{READ_MODEL_VERSION}:{page_digest}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=60"
    return page


@router.get("/{candidate_id}", response_model=CandidateReadModel)
def get_candidate(candidate_id: UUID, container: Container) -> CandidateReadModel:
    try:
        candidate = container.candidates.get(candidate_id)
    except CandidateReadUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate
