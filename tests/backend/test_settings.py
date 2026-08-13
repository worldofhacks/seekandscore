"""External-effect activation tests."""

import pytest
from pydantic import ValidationError

from seekandscore.platform.settings import Settings


def test_safe_defaults() -> None:
    settings = Settings()

    assert settings.dataset_mode == "synthetic"
    assert settings.ingestion_enabled is False
    assert settings.alert_delivery_mode == "log"
    assert settings.outreach_mode == "disabled"
    assert settings.outreach_send_enabled is False


@pytest.mark.parametrize("app_env", ["development", "test", "preview"])
def test_ingestion_cannot_run_in_non_deployment_environments(app_env: str) -> None:
    with pytest.raises(ValidationError, match="ingestion cannot be enabled"):
        Settings(
            app_env=app_env,
            dataset_mode="live",
            ingestion_enabled=True,
            ingestion_activation_id="approval-1",
        )


def test_ingestion_activation_requires_live_dataset_and_approval() -> None:
    with pytest.raises(ValidationError, match="DATASET_MODE=live"):
        Settings(app_env="staging", ingestion_enabled=True, ingestion_activation_id="approval-1")

    with pytest.raises(ValidationError, match="INGESTION_ACTIVATION_ID"):
        Settings(app_env="staging", dataset_mode="live", ingestion_enabled=True)


def test_provider_alert_delivery_fails_closed() -> None:
    with pytest.raises(ValidationError, match="production-only"):
        Settings(app_env="staging", alert_delivery_mode="provider")

    with pytest.raises(ValidationError, match="provider and activation record"):
        Settings(app_env="production", alert_delivery_mode="provider")


def test_outreach_send_requires_complete_production_activation() -> None:
    with pytest.raises(ValidationError, match="production-only"):
        Settings(app_env="staging", outreach_mode="provider", outreach_send_enabled=True)

    with pytest.raises(ValidationError, match="OUTREACH_MODE=provider"):
        Settings(app_env="production", outreach_send_enabled=True)

    with pytest.raises(ValidationError, match="human approval"):
        Settings(
            app_env="production",
            outreach_mode="provider",
            outreach_send_enabled=True,
            outreach_human_approval_required=False,
        )

    with pytest.raises(ValidationError, match="provider, policy, legal-review"):
        Settings(
            app_env="production",
            outreach_mode="provider",
            outreach_send_enabled=True,
        )


def test_complete_outreach_activation_is_representable() -> None:
    settings = Settings(
        app_env="production",
        outreach_mode="provider",
        outreach_send_enabled=True,
        outreach_provider="approved-email-provider",
        outreach_activation_id="activation-42",
        outreach_legal_review_id="legal-review-7",
    )

    assert settings.outreach_send_enabled is True
