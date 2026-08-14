"""Internal service authentication for single-operator research writes."""

import secrets
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status

from seekandscore.api.dependencies import get_container
from seekandscore.bootstrap import AppContainer


@dataclass(frozen=True, slots=True)
class ResearchActor:
    organization_id: UUID
    actor_id: UUID


def require_research_actor(
    container: Annotated[AppContainer, Depends(get_container)],
    internal_token: Annotated[str | None, Header(alias="X-SeekAndScore-Internal-Token")] = None,
) -> ResearchActor:
    settings = container.settings
    if not settings.research_writes_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved research is disabled by the runtime gate.",
        )
    expected_token = settings.research_internal_token
    if (
        expected_token is None
        or internal_token is None
        or not secrets.compare_digest(internal_token, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal research authentication failed.",
            headers={"WWW-Authenticate": "Internal"},
        )
    if settings.research_organization_id is None or settings.research_actor_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved-research identity is not configured.",
        )
    return ResearchActor(
        organization_id=settings.research_organization_id,
        actor_id=settings.research_actor_id,
    )
