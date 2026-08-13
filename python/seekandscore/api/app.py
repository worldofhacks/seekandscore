"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from seekandscore.api.routes.candidates import router as candidates_router
from seekandscore.api.routes.system import router as system_router
from seekandscore.bootstrap import AppContainer
from seekandscore.platform.settings import Settings, get_settings
from seekandscore.version import API_VERSION, __version__


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an isolated application with explicit validated settings."""

    runtime_settings = settings or get_settings()
    container = AppContainer.build(runtime_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.container = container
        yield

    application = FastAPI(
        title="Seek and Score API",
        summary="Evidence-backed property intelligence API",
        version=__version__,
        openapi_url=f"/{API_VERSION}/openapi.json",
        docs_url=f"/{API_VERSION}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.container = container
    application.include_router(system_router)
    application.include_router(candidates_router, prefix=f"/{API_VERSION}")

    @application.exception_handler(HTTPException)
    async def http_problem(request: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail if isinstance(error.detail, str) else "Request could not be completed"
        return JSONResponse(
            status_code=error.status_code,
            media_type="application/problem+json",
            headers=error.headers,
            content={
                "type": "about:blank",
                "title": _problem_title(error.status_code),
                "status": error.status_code,
                "detail": detail,
                "instance": request.url.path,
            },
        )

    return application


def _problem_title(status_code: int) -> str:
    return {
        400: "Bad Request",
        404: "Not Found",
        409: "Conflict",
        503: "Service Unavailable",
    }.get(status_code, "Request Error")


app = create_app()
