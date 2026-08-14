"""Database credential separation and secret-safe provisioning tests."""

from types import SimpleNamespace

import pytest

from seekandscore.db import roles
from seekandscore.db.migrate import MigrationConfigurationError, resolve_database_url


def test_migrations_require_owner_url_in_deployed_environments() -> None:
    runtime_url = "postgresql+psycopg://runtime:restricted@db/app"

    with pytest.raises(MigrationConfigurationError, match="MIGRATION_DATABASE_URL"):
        resolve_database_url(environment={"APP_ENV": "production", "DATABASE_URL": runtime_url})

    owner_url = "postgresql+psycopg://owner:sealed@db/app"
    assert (
        resolve_database_url(
            environment={
                "APP_ENV": "staging",
                "DATABASE_URL": runtime_url,
                "MIGRATION_DATABASE_URL": owner_url,
            }
        )
        == owner_url
    )
    assert (
        resolve_database_url(environment={"APP_ENV": "test", "DATABASE_URL": runtime_url})
        == runtime_url
    )


def test_password_failure_never_propagates_the_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "NeverExposeThisDatabasePassword_123456789"

    class ExplodingCursor:
        def __init__(self, _connection: object) -> None:
            pass

        def __enter__(self) -> "ExplodingCursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _statement: str, parameters: tuple[str]) -> None:
            raise RuntimeError(f"driver leaked {parameters[0]}")

    monkeypatch.setattr(roles, "ClientCursor", ExplodingCursor)
    connection = SimpleNamespace(connection=SimpleNamespace(driver_connection=object()))

    with pytest.raises(roles.DatabaseRoleConfigurationError) as captured:
        roles._set_role_password(connection, "seekandscore_api", secret)  # type: ignore[arg-type]

    assert secret not in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.parametrize(
    "value",
    ("short", "contains:delimiter" * 3, "contains space" * 3, "x" * 129),
)
def test_runtime_password_contract_is_url_safe(value: str) -> None:
    with pytest.raises(roles.DatabaseRoleConfigurationError):
        roles._validated_password(value)
