"""Backend test configuration."""

import pytest
from fastapi.testclient import TestClient

from seekandscore.api import create_app
from seekandscore.platform.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env="test")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
