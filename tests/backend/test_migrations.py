"""Migration configuration smoke tests that require no database."""

from seekandscore.db.migrate import build_config


def test_migration_config_points_to_repository_migrations() -> None:
    config = build_config("postgresql+psycopg://example/seekandscore")

    assert config.get_main_option("script_location").endswith("/migrations")
    assert config.get_main_option("sqlalchemy.url") == ("postgresql+psycopg://example/seekandscore")
