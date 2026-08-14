"""Domain records for source-pinned Opportunity Zone geography."""

import json
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DesignationStatus(StrEnum):
    """Publication stage; eligibility and nomination are not designations."""

    ELIGIBLE = "eligible"
    STATE_NOMINATED = "state_nominated"
    TREASURY_CERTIFIED = "treasury_certified"
    EFFECTIVE = "effective"
    EXPIRED = "expired"


class TemporalPrecision(StrEnum):
    EXACT = "exact"
    YEAR = "year"


class OpportunityZoneRound(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    round_code: str
    census_vintage: int
    certification_status: DesignationStatus
    designation_status: DesignationStatus
    effective_from: date
    effective_to: date
    tract_intervals_vary: bool = False
    source_id: str
    source_artifact_id: UUID
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_uri: str

    @model_validator(mode="after")
    def reject_unreviewed_2027_effective_status(self) -> "OpportunityZoneRound":
        if self.round_code == "2027" and self.designation_status is DesignationStatus.EFFECTIVE:
            raise ValueError(
                "2027 eligibility or nomination data cannot be represented as effective"
            )
        if self.effective_from > self.effective_to:
            raise ValueError("effective interval ends before it begins")
        return self


class OpportunityZoneTract(BaseModel):
    """One tract geometry asserted by one immutable official artifact."""

    model_config = ConfigDict(frozen=True)

    round_id: str
    tract_geoid: str = Field(pattern=r"^[0-9]{11}$")
    census_vintage: int
    certification_status: DesignationStatus
    designation_status: DesignationStatus
    effective_from: date
    effective_from_precision: TemporalPrecision
    effective_to: date
    state_name: str = Field(min_length=1, max_length=80)
    county_name: str = Field(min_length=1, max_length=120)
    source_artifact_id: UUID
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    geometry_srid: int
    geometry_geojson: str

    @model_validator(mode="after")
    def require_valid_effective_interval(self) -> "OpportunityZoneTract":
        if self.effective_from > self.effective_to:
            raise ValueError("effective interval ends before it begins")
        return self

    @field_validator("geometry_geojson")
    @classmethod
    def require_multipolygon_geojson(cls, value: str) -> str:
        try:
            geometry: Any = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("geometry must be valid GeoJSON") from error
        if not isinstance(geometry, dict) or geometry.get("type") != "MultiPolygon":
            raise ValueError("geometry must be a GeoJSON MultiPolygon")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise ValueError("geometry must contain polygon coordinates")
        return value


class OpportunityZoneImportStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SUCCEEDED_UNCHANGED = "succeeded_unchanged"
    FAILED = "failed"


class OpportunityZoneImportRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: str
    status: OpportunityZoneImportStatus
    activation_id: str
    started_at: datetime
    completed_at: datetime | None = None
    source_artifact_id: UUID | None = None
    source_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_tracts: int = Field(gt=0)
    imported_tracts: int = Field(default=0, ge=0)
    error_code: str | None = None
    error_detail: str | None = None


class ImportOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    inserted_tracts: int = Field(ge=0)
    total_tracts: int = Field(ge=0)
    unchanged: bool = False


class OpportunityZoneClassification(StrEnum):
    INSIDE = "inside"
    OUTSIDE = "outside"
    BOUNDARY_REVIEW = "boundary_review"
    UNAVAILABLE = "unavailable"


class OpportunityZoneEvidenceReason(StrEnum):
    MATCHED_DESIGNATED_TRACT = "matched_designated_tract"
    NO_DESIGNATED_TRACT_INTERSECTION = "no_designated_tract_intersection"
    PARCEL_INTERSECTS_DESIGNATION_BOUNDARY = "parcel_intersects_designation_boundary"
    PARCEL_GEOMETRY_REPAIRED = "parcel_geometry_repaired"
    DESIGNATION_GEOMETRY_REPAIRED = "designation_geometry_repaired"
    PARCEL_GEOMETRY_UNAVAILABLE = "parcel_geometry_unavailable"
    DESIGNATION_LAYER_UNAVAILABLE = "designation_layer_unavailable"
    MEMBERSHIP_SNAPSHOT_UNAVAILABLE = "membership_snapshot_unavailable"
    DISPLAY_NOT_APPROVED = "display_not_approved"


class ParcelGeometryEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    source_record_id: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    geometry_repaired: bool
    repair_method: str | None = None

    @model_validator(mode="after")
    def require_repair_lineage_pair(self) -> "ParcelGeometryEvidence":
        if self.geometry_repaired != (self.repair_method is not None):
            raise ValueError("parcel geometry repair flag and method must be present together")
        return self


class OpportunityZoneDesignationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    round_id: str
    tract_geoid: str | None = Field(default=None, pattern=r"^[0-9]{11}$")
    intersecting_tract_geoids: tuple[str, ...] = ()
    census_vintage: int
    designation_status: Literal["effective"]
    effective_from: date
    effective_to: date
    source_id: str
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_uri: str
    geometry_repaired: bool = False
    repair_method: str | None = None

    @field_validator("intersecting_tract_geoids")
    @classmethod
    def require_sorted_unique_geoids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))) or any(
            len(value) != 11 or not value.isdigit() for value in values
        ):
            raise ValueError("intersecting tract GEOIDs must be sorted unique 11-digit values")
        return values

    @model_validator(mode="after")
    def require_repair_lineage_pair(self) -> "OpportunityZoneDesignationEvidence":
        if self.geometry_repaired != (self.repair_method is not None):
            raise ValueError("designation geometry repair flag and method must be present together")
        if self.effective_from > self.effective_to:
            raise ValueError("designation evidence effective interval is reversed")
        return self


class OpportunityZoneEvidence(BaseModel):
    """Derived membership evidence; geometry coordinates are deliberately excluded."""

    model_config = ConfigDict(frozen=True)

    classification: OpportunityZoneClassification
    reason_code: OpportunityZoneEvidenceReason
    method: Literal["postgis_strict_interior_v1"] | None = None
    classified_at: datetime | None = None
    parcel_geometry: ParcelGeometryEvidence | None = None
    designation: OpportunityZoneDesignationEvidence | None = None

    @model_validator(mode="after")
    def require_classification_evidence_shape(self) -> "OpportunityZoneEvidence":
        unavailable_reasons = {
            OpportunityZoneEvidenceReason.PARCEL_GEOMETRY_UNAVAILABLE,
            OpportunityZoneEvidenceReason.DESIGNATION_LAYER_UNAVAILABLE,
            OpportunityZoneEvidenceReason.MEMBERSHIP_SNAPSHOT_UNAVAILABLE,
            OpportunityZoneEvidenceReason.DISPLAY_NOT_APPROVED,
        }
        if self.classification is OpportunityZoneClassification.UNAVAILABLE:
            if (
                self.reason_code not in unavailable_reasons
                or self.method is not None
                or self.classified_at is not None
                or self.parcel_geometry is not None
                or self.designation is not None
            ):
                raise ValueError("unavailable classification cannot contain displayed evidence")
            return self

        if (
            self.reason_code in unavailable_reasons
            or self.method is None
            or self.classified_at is None
            or self.parcel_geometry is None
            or self.designation is None
        ):
            raise ValueError("spatial classification requires complete coordinate-free evidence")
        designation = self.designation
        parcel = self.parcel_geometry
        if self.classification is OpportunityZoneClassification.INSIDE:
            valid = (
                self.reason_code is OpportunityZoneEvidenceReason.MATCHED_DESIGNATED_TRACT
                and not parcel.geometry_repaired
                and not designation.geometry_repaired
                and designation.tract_geoid is not None
                and designation.intersecting_tract_geoids == (designation.tract_geoid,)
            )
        elif self.classification is OpportunityZoneClassification.OUTSIDE:
            valid = (
                self.reason_code is OpportunityZoneEvidenceReason.NO_DESIGNATED_TRACT_INTERSECTION
                and not parcel.geometry_repaired
                and not designation.geometry_repaired
                and designation.tract_geoid is None
                and not designation.intersecting_tract_geoids
            )
        else:
            expected_reason = (
                OpportunityZoneEvidenceReason.DESIGNATION_GEOMETRY_REPAIRED
                if designation.geometry_repaired
                else OpportunityZoneEvidenceReason.PARCEL_GEOMETRY_REPAIRED
                if parcel.geometry_repaired
                else OpportunityZoneEvidenceReason.PARCEL_INTERSECTS_DESIGNATION_BOUNDARY
            )
            valid = (
                self.reason_code is expected_reason
                and designation.tract_geoid is None
                and (
                    bool(designation.intersecting_tract_geoids)
                    or (parcel.geometry_repaired and not designation.geometry_repaired)
                )
            )
        if not valid:
            raise ValueError("classification, reason, and spatial evidence lineage conflict")
        return self


class OpportunityZoneMembershipRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    parcel_id: UUID
    evidence: OpportunityZoneEvidence


class OpportunityZoneSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    cohort_run_id: UUID
    complete: bool
    unavailable_reason: OpportunityZoneEvidenceReason | None = None
    memberships: tuple[OpportunityZoneMembershipRecord, ...] = ()

    @model_validator(mode="after")
    def require_snapshot_state_shape(self) -> "OpportunityZoneSnapshot":
        if self.complete == (self.unavailable_reason is not None):
            raise ValueError("snapshot completeness and unavailable reason conflict")
        if not self.complete and self.memberships:
            raise ValueError("unavailable snapshot cannot expose partial membership evidence")
        return self


class OpportunityZoneMembershipBuildStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SUCCEEDED_UNCHANGED = "succeeded_unchanged"
    FAILED = "failed"


class OpportunityZoneMembershipBuildOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    cohort_run_id: UUID
    round_id: str
    algorithm_version: str
    activation_id: str = Field(min_length=1)
    status: OpportunityZoneMembershipBuildStatus
    snapshot_id: UUID | None = None
    expected_parcels: int = Field(gt=0)
    evaluated_parcels: int = Field(ge=0)
    inside_count: int = Field(ge=0)
    outside_count: int = Field(ge=0)
    boundary_review_count: int = Field(ge=0)
    missing_geometry_count: int = Field(ge=0)
    started_at: datetime
    completed_at: datetime | None = None
