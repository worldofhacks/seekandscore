"""Official Travis County TNR / TCAD ArcGIS parcel adapter."""

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, ValidationError

from seekandscore.acquisition.models import (
    AcquisitionCompletenessPolicy,
    NormalizedParcelObservation,
    QuarantinedRecord,
    RawArtifact,
    SourceRunProfile,
)
from seekandscore.registry.sources import TRAVIS_TCAD_SOURCE

OBSERVATION_NAMESPACE = UUID("65843247-04b9-4f1d-96ab-974b3aa6b810")
QUARANTINE_NAMESPACE = UUID("9c3ec910-35ed-4230-9ba8-302788460f3a")

OUT_FIELDS = (
    "OBJECTID",
    "PROP_ID",
    "geo_id",
    "situs_address",
    "situs_city",
    "situs_zip",
    "tcad_acres",
    "GIS_acres",
    "market_value",
    "appraised_val",
    "assessed_val",
    "imprv_homesite_val",
    "imprv_non_homesite_val",
    "land_homesite_val",
    "land_non_homesite_val",
    "F1year_imprv",
    "CENTROID_X",
    "CENTROID_Y",
)

REQUIRED_FIELD_TYPES = {
    "OBJECTID": "esriFieldTypeOID",
    "PROP_ID": "esriFieldTypeInteger",
    "geo_id": "esriFieldTypeString",
    "situs_address": "esriFieldTypeString",
    "tcad_acres": "esriFieldTypeDouble",
    "market_value": "esriFieldTypeInteger",
    "appraised_val": "esriFieldTypeInteger",
    "assessed_val": "esriFieldTypeInteger",
}


class SourceSchemaError(ValueError):
    """Artifact metadata or feature schema does not match the certified adapter."""


class ArcGisErrorResponse(ValueError):
    """ArcGIS returned an application-level error envelope."""


class ArcGisField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    type: str


class ArcGisFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")

    attributes: dict[str, Any]


class ArcGisPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fields: tuple[ArcGisField, ...]
    features: tuple[ArcGisFeature, ...]
    exceededTransferLimit: bool = False


@dataclass(frozen=True, slots=True)
class TravisTcadQuery:
    page_size: int = 250
    max_records: int = 250
    where: str = "PROP_ID IS NOT NULL AND tcad_acres >= 1"
    order_by: str = "OBJECTID ASC"
    cities: tuple[str, ...] = ()
    run_profile: SourceRunProfile = SourceRunProfile.PROOF
    completeness_policy: AcquisitionCompletenessPolicy = (
        AcquisitionCompletenessPolicy.ALLOW_BOUNDED_PARTIAL
    )

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 1000:
            raise ValueError("page_size must be between 1 and provider maximum 1000")
        if not 1 <= self.max_records <= 10_000:
            raise ValueError("max_records must be between 1 and 10000")
        if self.where != "PROP_ID IS NOT NULL AND tcad_acres >= 1":
            raise ValueError("query predicate is not approved")
        if self.order_by != "OBJECTID ASC":
            raise ValueError("order_by must be OBJECTID ASC")
        if len(self.cities) > 20 or any(
            not city.replace(" ", "").isalpha() or city != city.upper() for city in self.cities
        ):
            raise ValueError("cities must contain at most 20 uppercase city names")

    def effective_where(self) -> str:
        if not self.cities:
            return self.where
        quoted = ",".join(f"'{city}'" for city in self.cities)
        return f"{self.where} AND situs_city IN ({quoted})"

    def params(self, offset: int) -> dict[str, str | int | bool]:
        remaining = self.max_records - offset
        return {
            "f": "json",
            "where": self.effective_where(),
            "outFields": ",".join(OUT_FIELDS),
            "returnGeometry": True,
            "outSR": 4326,
            "geometryPrecision": 6,
            "orderByFields": self.order_by,
            "resultOffset": offset,
            "resultRecordCount": min(self.page_size, remaining),
        }

    def count_params(self) -> dict[str, str | int | bool]:
        return {
            "f": "json",
            "where": self.effective_where(),
            "returnCountOnly": True,
        }


class TravisTcadArcGisAdapter:
    descriptor = TRAVIS_TCAD_SOURCE

    def __init__(self, query: TravisTcadQuery) -> None:
        self.query = query

    def request_pages(self) -> Iterator[dict[str, str | int | bool]]:
        offset = 0
        while offset < self.query.max_records:
            yield self.query.params(offset)
            offset += min(self.query.page_size, self.query.max_records - offset)

    def parse_page(
        self,
        *,
        content: bytes,
        artifact: RawArtifact,
    ) -> tuple[tuple[NormalizedParcelObservation, ...], tuple[QuarantinedRecord, ...], bool]:
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceSchemaError("artifact is not valid UTF-8 JSON") from error
        if isinstance(payload, dict) and "error" in payload:
            raise ArcGisErrorResponse("ArcGIS returned an error envelope")
        try:
            page = ArcGisPage.model_validate(payload)
        except ValidationError as error:
            raise SourceSchemaError("artifact does not match ArcGIS feature-page schema") from error
        self._validate_fields(page.fields)

        observations: list[NormalizedParcelObservation] = []
        quarantined: list[QuarantinedRecord] = []
        for feature in page.features:
            try:
                observations.append(self._normalize(feature.attributes, artifact))
            except (TypeError, ValueError) as error:
                source_record_id = _string_or_none(feature.attributes.get("OBJECTID"))
                quarantine_id = uuid5(
                    QUARANTINE_NAMESPACE,
                    f"{artifact.sha256}:{source_record_id}:{type(error).__name__}",
                )
                quarantined.append(
                    QuarantinedRecord(
                        id=quarantine_id,
                        source_id=self.descriptor.id,
                        artifact_id=artifact.id,
                        source_record_id=source_record_id,
                        reason_code="invalid_feature",
                        reason_detail=str(error)[:500],
                        recorded_at=artifact.retrieved_at,
                    )
                )
        return tuple(observations), tuple(quarantined), page.exceededTransferLimit

    def _validate_fields(self, fields: Iterable[ArcGisField]) -> None:
        actual = {field.name: field.type for field in fields}
        mismatches = {
            name: (expected, actual.get(name))
            for name, expected in REQUIRED_FIELD_TYPES.items()
            if actual.get(name) != expected
        }
        if mismatches:
            raise SourceSchemaError(f"required ArcGIS fields changed: {sorted(mismatches)}")

    def _normalize(
        self,
        attributes: dict[str, Any],
        artifact: RawArtifact,
    ) -> NormalizedParcelObservation:
        object_id = _required_id(attributes.get("OBJECTID"), "OBJECTID")
        property_id = _required_id(attributes.get("PROP_ID"), "PROP_ID")
        source_record_id = str(object_id)
        observation_id = uuid5(
            OBSERVATION_NAMESPACE,
            ":".join(
                (
                    self.descriptor.id,
                    source_record_id,
                    artifact.sha256,
                    self.descriptor.parser_version,
                )
            ),
        )
        return NormalizedParcelObservation(
            id=observation_id,
            source_id=self.descriptor.id,
            source_record_id=source_record_id,
            artifact_id=artifact.id,
            artifact_sha256=artifact.sha256,
            parser_version=self.descriptor.parser_version,
            jurisdiction_id=self.descriptor.jurisdiction_id,
            local_parcel_id=str(property_id),
            geographic_id=_string_or_none(attributes.get("geo_id")),
            situs_address=_string_or_none(attributes.get("situs_address")),
            situs_city=_string_or_none(attributes.get("situs_city")),
            situs_zip=_string_or_none(attributes.get("situs_zip")),
            tcad_acres=_positive_float_or_none(attributes.get("tcad_acres")),
            gis_acres=_positive_float_or_none(attributes.get("GIS_acres")),
            market_value_cents=_dollars_to_cents(attributes.get("market_value")),
            appraised_value_cents=_dollars_to_cents(attributes.get("appraised_val")),
            assessed_value_cents=_dollars_to_cents(attributes.get("assessed_val")),
            improvement_value_cents=_sum_dollars_to_cents(
                attributes.get("imprv_homesite_val"),
                attributes.get("imprv_non_homesite_val"),
            ),
            land_value_cents=_sum_dollars_to_cents(
                attributes.get("land_homesite_val"),
                attributes.get("land_non_homesite_val"),
            ),
            first_improvement_year=_year_or_none(attributes.get("F1year_imprv")),
            observed_at=artifact.retrieved_at,
        )


def _required_id(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} is not an integer identifier")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} is missing or invalid") from error
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _positive_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("acreage is invalid") from error
    return result if result > 0 else None


def _dollars_to_cents(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        dollars = Decimal(str(value).replace(",", ""))
    except InvalidOperation as error:
        raise ValueError("money observation is invalid") from error
    if dollars < 0:
        raise ValueError("money observation cannot be negative")
    return int(dollars * 100)


def _sum_dollars_to_cents(*values: Any) -> int | None:
    parsed = tuple(_dollars_to_cents(value) for value in values)
    present = tuple(value for value in parsed if value is not None)
    return sum(present) if present else None


def _year_or_none(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    year = int(value)
    if not 1700 <= year <= 2100:
        raise ValueError("improvement year is outside accepted range")
    return year
