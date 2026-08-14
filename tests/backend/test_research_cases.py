"""Saved-research state, audit semantics, and authenticated API tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from seekandscore.api import create_app
from seekandscore.api.dependencies import get_container
from seekandscore.bootstrap import AppContainer
from seekandscore.deal import (
    MemoryResearchCaseRepository,
    ResearchCaseConflictError,
    ResearchCaseService,
    ResearchStatus,
)
from seekandscore.platform.settings import Settings
from seekandscore.readmodels.candidates import (
    CandidateQueueState,
    CandidateReadModel,
    EvidenceSummary,
    MoneyRange,
    OpportunityZoneStatus,
)

NOW = datetime(2026, 8, 13, 17, tzinfo=UTC)
CANDIDATE_ID = UUID("11111111-1111-4111-8111-111111111111")
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
ACTOR_ID = UUID("33333333-3333-4333-8333-333333333333")
TOKEN = "r" * 40
DISPLAY_APPROVAL_ID = "SRC-TCAD-TNR-BOUNDED-DISPLAY-20260813-V1"


def candidate() -> CandidateReadModel:
    return CandidateReadModel(
        id=CANDIDATE_ID,
        display_name="100 LIVE PARCEL RD",
        locality="Del Valle, TX",
        parcel_id="TCAD-700001",
        candidate_kind="parcel",
        parcel_count=1,
        jurisdiction_id="us-tx-travis",
        county_name="Travis County",
        state_name="Texas",
        timezone="America/Chicago",
        strategy="assessor",
        rank=1,
        previous_rank=None,
        queue_state=CandidateQueueState.RESEARCH,
        opportunity_score=60,
        confidence=0.5,
        acreage=2.5,
        value_range=MoneyRange(low=500_000, high=500_000),
        likely_basis=0,
        thesis="Assessor screening only.",
        opportunity_zone_status=OpportunityZoneStatus.REVIEW,
        next_action="Verify geometry",
        evidence=EvidenceSummary(
            source_count=1,
            unresolved_conflict_count=0,
            freshness="current",
        ),
        as_of=NOW,
        screening_only=True,
    )


def service() -> tuple[ResearchCaseService, MemoryResearchCaseRepository]:
    repository = MemoryResearchCaseRepository()
    return ResearchCaseService(repository, clock=lambda: NOW), repository


def test_create_is_idempotent_and_case_ids_are_organization_scoped() -> None:
    research, repository = service()

    first, created = research.create(
        organization_id=ORG_ID,
        actor_id=ACTOR_ID,
        candidate=candidate(),
        status=ResearchStatus.WATCHING,
        operator_note="Check access",
        next_action="Review survey",
    )
    replay, replay_created = research.create(
        organization_id=ORG_ID,
        actor_id=ACTOR_ID,
        candidate=candidate(),
        status=ResearchStatus.RESEARCHING,
        operator_note="This replay must not overwrite",
        next_action=None,
    )
    other_org, other_created = research.create(
        organization_id=UUID("44444444-4444-4444-8444-444444444444"),
        actor_id=ACTOR_ID,
        candidate=candidate(),
        status=ResearchStatus.WATCHING,
        operator_note=None,
        next_action=None,
    )

    assert created is True
    assert replay_created is False
    assert replay == first
    assert other_created is True
    assert other_org.id != first.id
    assert len(repository.revisions) == 2


def test_update_uses_optimistic_lock_and_append_only_revisions() -> None:
    research, repository = service()
    original, _ = research.create(
        organization_id=ORG_ID,
        actor_id=ACTOR_ID,
        candidate=candidate(),
        status=ResearchStatus.WATCHING,
        operator_note=None,
        next_action=None,
    )

    updated = research.update(
        organization_id=ORG_ID,
        actor_id=ACTOR_ID,
        case_id=original.id,
        expected_version=1,
        status=ResearchStatus.RESEARCHING,
        operator_note="Verify legal access",
        next_action="Order survey",
        update_note=True,
        update_next_action=True,
    )

    assert updated.version == 2
    assert updated.status is ResearchStatus.RESEARCHING
    assert [item.version for item in repository.revisions] == [1, 2]
    with pytest.raises(ResearchCaseConflictError):
        research.update(
            organization_id=ORG_ID,
            actor_id=ACTOR_ID,
            case_id=original.id,
            expected_version=1,
            status=ResearchStatus.PASSED,
            operator_note=None,
            next_action=None,
            update_note=False,
            update_next_action=False,
        )


def test_dossier_gates_do_not_promote_unverified_oz_or_outreach() -> None:
    research, _ = service()

    dossier = research.dossier(organization_id=ORG_ID, candidate=candidate())

    gates = {gate.key: gate for gate in dossier.gates}
    assert gates["source_freshness"].status == "satisfied"
    assert gates["opportunity_zone"].status == "blocked"
    assert gates["underwriting"].status == "blocked"
    assert gates["contact_prep"].status == "blocked"
    assert dossier.controls.contact_prep_enabled is False
    assert dossier.controls.outbound_enabled is False


def test_dossier_never_satisfies_freshness_for_a_stale_candidate() -> None:
    research, _ = service()
    stale = candidate().model_copy(
        update={"evidence": candidate().evidence.model_copy(update={"freshness": "stale"})}
    )

    dossier = research.dossier(organization_id=ORG_ID, candidate=stale)

    gates = {gate.key: gate for gate in dossier.gates}
    assert gates["source_freshness"].status == "open"
    assert gates["source_freshness"].reason_code == "SOURCE_NOT_CURRENT"


class CandidateStub:
    serving_mode = "live"
    display_enabled = True

    def list(self, **_: object):  # type: ignore[no-untyped-def]
        raise AssertionError("list is not used by research API tests")

    def get(self, candidate_id: UUID) -> CandidateReadModel | None:
        return candidate() if candidate_id == CANDIDATE_ID else None

    def is_ready(self) -> bool:
        return True


def test_research_api_requires_internal_auth_and_if_match() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        live_source_display_enabled=True,
        live_source_display_approval_id=DISPLAY_APPROVAL_ID,
        research_writes_enabled=True,
        research_internal_token=TOKEN,
        research_organization_id=ORG_ID,
        research_actor_id=ACTOR_ID,
    )
    container = AppContainer.build(settings)
    research, _ = service()
    object.__setattr__(container, "candidates", CandidateStub())
    object.__setattr__(container, "research", research)
    app = create_app(settings)
    app.dependency_overrides[get_container] = lambda: container
    headers = {
        "X-SeekAndScore-Internal-Token": TOKEN,
        "X-SeekAndScore-Operator": "spoofed-operator",
    }

    with TestClient(app) as client:
        denied = client.put(f"/v1/candidates/{CANDIDATE_ID}/research-case", json={})
        created = client.put(
            f"/v1/candidates/{CANDIDATE_ID}/research-case",
            headers=headers,
            json={"status": "watching", "operator_note": "Review access"},
        )
        replay = client.put(
            f"/v1/candidates/{CANDIDATE_ID}/research-case",
            headers=headers,
            json={"status": "researching"},
        )
        missing_match = client.patch(
            f"/v1/research-cases/{created.json()['id']}",
            headers=headers,
            json={"status": "researching"},
        )
        weak_match = client.patch(
            f"/v1/research-cases/{created.json()['id']}",
            headers={**headers, "If-Match": 'W/"1"'},
            json={"status": "researching"},
        )
        bare_match = client.patch(
            f"/v1/research-cases/{created.json()['id']}",
            headers={**headers, "If-Match": "1"},
            json={"status": "researching"},
        )
        oversized_match = client.patch(
            f"/v1/research-cases/{created.json()['id']}",
            headers={**headers, "If-Match": f'"{"9" * 5000}"'},
            json={"status": "researching"},
        )
        updated = client.patch(
            f"/v1/research-cases/{created.json()['id']}",
            headers={**headers, "If-Match": '"1"'},
            json={"status": "researching", "next_action": "Verify access"},
        )
        stale = client.patch(
            f"/v1/research-cases/{created.json()['id']}",
            headers={**headers, "If-Match": '"1"'},
            json={"status": "passed"},
        )
        dossier = client.get(
            f"/v1/candidates/{CANDIDATE_ID}/dossier",
            headers=headers,
        )

    assert denied.status_code == 401
    assert denied.headers["cache-control"] == "private, no-store, max-age=0"
    assert denied.headers["pragma"] == "no-cache"
    assert created.status_code == 201
    assert created.headers["etag"] == '"1"'
    assert created.headers["cache-control"] == "private, no-store, max-age=0"
    assert created.json()["created_by"] == str(settings.research_actor_id)
    assert replay.status_code == 200
    assert replay.json()["operator_note"] == "Review access"
    assert missing_match.status_code == 428
    assert weak_match.status_code == 400
    assert bare_match.status_code == 400
    assert oversized_match.status_code == 400
    assert oversized_match.headers["cache-control"] == "private, no-store, max-age=0"
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert stale.status_code == 412
    assert dossier.status_code == 200
    assert dossier.headers["cache-control"] == "private, no-store, max-age=0"
    assert dossier.json()["controls"] == {
        "contact_prep_enabled": False,
        "outbound_enabled": False,
    }


def test_research_list_response_is_private_and_not_cached() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        live_source_display_enabled=True,
        live_source_display_approval_id=DISPLAY_APPROVAL_ID,
        research_writes_enabled=True,
        research_internal_token=TOKEN,
        research_organization_id=ORG_ID,
        research_actor_id=ACTOR_ID,
    )
    container = AppContainer.build(settings)
    research, _ = service()
    object.__setattr__(container, "research", research)
    app = create_app(settings)
    app.dependency_overrides[get_container] = lambda: container

    with TestClient(app) as client:
        response = client.get(
            "/v1/research-cases",
            headers={"X-SeekAndScore-Internal-Token": TOKEN},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_research_setting_fails_closed_without_strong_internal_token() -> None:
    with pytest.raises(ValueError, match=r"32\+ character"):
        Settings(
            app_env="test",
            database_url="sqlite://",
            live_source_display_enabled=True,
            live_source_display_approval_id=DISPLAY_APPROVAL_ID,
            research_writes_enabled=True,
            research_internal_token="short",
            research_organization_id=ORG_ID,
            research_actor_id=ACTOR_ID,
        )


def test_research_setting_requires_explicit_tenant_and_actor() -> None:
    with pytest.raises(ValueError, match="explicit nonzero organization and actor IDs"):
        Settings(
            app_env="test",
            database_url="sqlite://",
            live_source_display_enabled=True,
            live_source_display_approval_id=DISPLAY_APPROVAL_ID,
            research_writes_enabled=True,
            research_internal_token=TOKEN,
        )


def test_research_case_updated_at_changes_with_clock() -> None:
    repository = MemoryResearchCaseRepository()
    times = iter((NOW, NOW + timedelta(minutes=5)))
    research = ResearchCaseService(repository, clock=lambda: next(times))
    original, _ = research.create(
        organization_id=ORG_ID,
        actor_id=ACTOR_ID,
        candidate=candidate(),
        status=ResearchStatus.WATCHING,
        operator_note=None,
        next_action=None,
    )
    updated = research.update(
        organization_id=ORG_ID,
        actor_id=ACTOR_ID,
        case_id=original.id,
        expected_version=1,
        status=ResearchStatus.RESEARCHING,
        operator_note=None,
        next_action=None,
        update_note=False,
        update_next_action=False,
    )
    assert updated.updated_at == NOW + timedelta(minutes=5)
