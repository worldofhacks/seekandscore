"""Liveness, readiness, version, and capability routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict

from seekandscore.api.dependencies import get_container
from seekandscore.bootstrap import MODULES, AppContainer
from seekandscore.platform import PlatformCapabilities
from seekandscore.version import API_VERSION, READ_MODEL_VERSION, __version__

router = APIRouter(tags=["system"])
Container = Annotated[AppContainer, Depends(get_container)]


class LiveResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ready", "not_ready"]
    checks: dict[str, Literal["ok", "failed"]]


class VersionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    service: str
    version: str
    api_version: str
    read_model_version: str
    dataset_mode: str
    candidate_serving_mode: str
    release_sha: str
    modules: tuple[str, ...]


@router.get("/livez", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse()


@router.get(
    "/readyz",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
def ready(container: Container, response: Response) -> ReadyResponse:
    raw_checks = container.readiness_checks()
    is_ready = all(raw_checks.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ready" if is_ready else "not_ready",
        checks={name: "ok" if result else "failed" for name, result in raw_checks.items()},
    )


@router.get("/version", response_model=VersionResponse)
def version(container: Container) -> VersionResponse:
    return VersionResponse(
        service=container.settings.app_name,
        version=__version__,
        api_version=API_VERSION,
        read_model_version=READ_MODEL_VERSION,
        dataset_mode=container.settings.dataset_mode,
        candidate_serving_mode=container.candidates.serving_mode,
        release_sha=container.settings.release_sha,
        modules=tuple(module.name for module in MODULES),
    )


@router.get(f"/{API_VERSION}/capabilities", response_model=PlatformCapabilities)
def capabilities(container: Container) -> PlatformCapabilities:
    return PlatformCapabilities.from_runtime(
        container.settings,
        candidate_serving_mode=container.candidates.serving_mode,
        candidate_read_model_ready=container.candidates.is_ready(),
        live_candidate_display_enabled=container.candidates.display_enabled,
        research_store_ready=(container.research is not None and container.research.is_ready()),
    )
