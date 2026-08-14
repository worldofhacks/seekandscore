"""Research-case state transitions and server-derived verification gates."""

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid5

from seekandscore.deal.models import (
    CandidateDossier,
    DossierControls,
    ResearchCase,
    ResearchCasePage,
    ResearchStatus,
    VerificationGate,
    VerificationGateKey,
    VerificationGateStatus,
)
from seekandscore.deal.repository import ResearchCaseRepository
from seekandscore.readmodels.candidates import CandidateReadModel

RESEARCH_CASE_NAMESPACE = UUID("66c84799-6802-4e47-a44a-772c760b3e66")
CENTRAL_TEXAS_REGION_ID = "us-tx-central-texas"


class ResearchCaseNotFoundError(LookupError):
    pass


class ResearchCaseConflictError(RuntimeError):
    pass


class ResearchCaseTransitionError(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[ResearchStatus, frozenset[ResearchStatus]] = {
    ResearchStatus.WATCHING: frozenset(
        {ResearchStatus.RESEARCHING, ResearchStatus.PASSED, ResearchStatus.ARCHIVED}
    ),
    ResearchStatus.RESEARCHING: frozenset(
        {ResearchStatus.WATCHING, ResearchStatus.PASSED, ResearchStatus.ARCHIVED}
    ),
    ResearchStatus.PASSED: frozenset({ResearchStatus.WATCHING, ResearchStatus.ARCHIVED}),
    ResearchStatus.ARCHIVED: frozenset({ResearchStatus.WATCHING}),
}


class ResearchCaseService:
    def __init__(
        self,
        repository: ResearchCaseRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(UTC))

    def is_ready(self) -> bool:
        return self.repository.is_ready()

    def get(self, organization_id: UUID, case_id: UUID) -> ResearchCase:
        item = self.repository.get(organization_id, case_id)
        if item is None:
            raise ResearchCaseNotFoundError(str(case_id))
        return item

    def get_by_candidate(self, organization_id: UUID, candidate_id: UUID) -> ResearchCase | None:
        return self.repository.get_by_candidate(organization_id, candidate_id)

    def list(
        self,
        organization_id: UUID,
        *,
        status: ResearchStatus | None,
        limit: int,
        cursor: str | None,
    ) -> ResearchCasePage:
        offset = _decode_cursor(cursor, status) if cursor else 0
        items, total = self.repository.list(
            organization_id, status=status, limit=limit + 1, offset=offset
        )
        has_more = len(items) > limit
        visible = items[:limit]
        return ResearchCasePage(
            items=visible,
            next_cursor=_encode_cursor(offset + limit, status) if has_more else None,
            total=total,
        )

    def create(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        candidate: CandidateReadModel,
        status: ResearchStatus,
        operator_note: str | None,
        next_action: str | None,
    ) -> tuple[ResearchCase, bool]:
        now = self.clock()
        case_id = uuid5(RESEARCH_CASE_NAMESPACE, f"{organization_id}:{candidate.id}")
        research_case = ResearchCase(
            id=case_id,
            organization_id=organization_id,
            candidate_id=candidate.id,
            region_id=CENTRAL_TEXAS_REGION_ID,
            jurisdiction_id=candidate.jurisdiction_id,
            parcel_id=candidate.parcel_id,
            status=status,
            operator_note=_clean_optional(operator_note),
            next_action=_clean_optional(next_action),
            candidate_read_model_version=candidate.read_model_version,
            candidate_as_of=candidate.as_of,
            version=1,
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        return self.repository.create(research_case)

    def update(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        case_id: UUID,
        expected_version: int,
        status: ResearchStatus | None,
        operator_note: str | None,
        next_action: str | None,
        update_note: bool,
        update_next_action: bool,
    ) -> ResearchCase:
        current = self.get(organization_id, case_id)
        if current.version != expected_version:
            raise ResearchCaseConflictError("research case version changed")
        target_status = status or current.status
        if (
            target_status is not current.status
            and target_status not in ALLOWED_TRANSITIONS[current.status]
        ):
            raise ResearchCaseTransitionError(
                f"cannot transition {current.status.value} to {target_status.value}"
            )
        updated = ResearchCase.model_validate(
            {
                **current.model_dump(),
                "status": target_status,
                "operator_note": (
                    _clean_optional(operator_note) if update_note else current.operator_note
                ),
                "next_action": (
                    _clean_optional(next_action) if update_next_action else current.next_action
                ),
                "version": current.version + 1,
                "updated_by": actor_id,
                "updated_at": self.clock(),
            }
        )
        result = self.repository.update(updated, expected_version=expected_version)
        if result is None:
            raise ResearchCaseConflictError("research case version changed")
        return result

    def dossier(
        self,
        *,
        organization_id: UUID,
        candidate: CandidateReadModel,
    ) -> CandidateDossier:
        source_evidence_id = (
            str(candidate.source_observation.source_record_id)
            if candidate.source_observation is not None
            else ""
        )
        freshness_current = candidate.evidence.freshness == "current"
        return CandidateDossier(
            candidate=candidate,
            region_id=CENTRAL_TEXAS_REGION_ID,
            gates=(
                VerificationGate(
                    key=VerificationGateKey.PARCEL_IDENTITY,
                    status=VerificationGateStatus.OPEN,
                    reason_code="SOURCE_IDENTITY_ONLY",
                    detail=(
                        "The approved assessor identifier is present; canonical parcel and "
                        "geometry resolution are not complete."
                    ),
                    evidence_ids=(source_evidence_id,) if source_evidence_id else (),
                ),
                VerificationGate(
                    key=VerificationGateKey.SOURCE_FRESHNESS,
                    status=(
                        VerificationGateStatus.SATISFIED
                        if freshness_current
                        else VerificationGateStatus.OPEN
                    ),
                    reason_code=("SOURCE_CURRENT" if freshness_current else "SOURCE_NOT_CURRENT"),
                    detail=(
                        "The source observation is inside its configured freshness window."
                        if freshness_current
                        else "The source observation requires a freshness review."
                    ),
                    evidence_ids=(source_evidence_id,) if source_evidence_id else (),
                ),
                VerificationGate(
                    key=VerificationGateKey.OPPORTUNITY_ZONE,
                    status=VerificationGateStatus.BLOCKED,
                    reason_code="VERSIONED_SPATIAL_JOIN_REQUIRED",
                    detail=(
                        "Opportunity Zone status remains blocked until parcel geometry is joined "
                        "to the correct frozen designation-round geometry."
                    ),
                ),
                VerificationGate(
                    key=VerificationGateKey.UNDERWRITING,
                    status=VerificationGateStatus.BLOCKED,
                    reason_code="INDEPENDENT_VALUE_AND_COSTS_REQUIRED",
                    detail=(
                        "Assessor observations alone are insufficient for underwriting, an offer, "
                        "or an acquisition basis."
                    ),
                ),
                VerificationGate(
                    key=VerificationGateKey.CONTACT_PREP,
                    status=VerificationGateStatus.BLOCKED,
                    reason_code="RESPONSIBLE_PARTY_EVIDENCE_REQUIRED",
                    detail=(
                        "No approved responsible-party or permitted contact-point evidence is "
                        "available. Outbound channels remain disabled."
                    ),
                ),
            ),
            research_case=self.repository.get_by_candidate(organization_id, candidate.id),
            controls=DossierControls(contact_prep_enabled=False, outbound_enabled=False),
        )


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _encode_cursor(offset: int, status: ResearchStatus | None) -> str:
    payload = {"offset": offset, "status": status.value if status else None}
    return base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()


def _decode_cursor(cursor: str, status: ResearchStatus | None) -> int:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        expected_status = status.value if status else None
        if payload.get("status") != expected_status:
            raise ValueError
        offset = int(payload["offset"])
        if offset < 0:
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid research-case cursor") from error
    return offset
