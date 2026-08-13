"""Typed API dependency accessors."""

from fastapi import Request

from seekandscore.bootstrap import AppContainer


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[no-any-return]
