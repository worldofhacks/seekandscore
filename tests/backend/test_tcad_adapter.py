"""Official TCAD ArcGIS adapter contract tests."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from seekandscore.acquisition.adapters.travis_tcad import (
    OUT_FIELDS,
    SourceSchemaError,
    TravisTcadArcGisAdapter,
    TravisTcadQuery,
    _polygon_geojson,
)
from seekandscore.acquisition.models import RawArtifact

FIXTURE = Path(__file__).parent / "fixtures" / "tcad_page.json"
FIXTURE_SHA = "e" * 64


def artifact() -> RawArtifact:
    return RawArtifact(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        source_id="travis_tcad_parcels",
        sha256=FIXTURE_SHA,
        byte_count=FIXTURE.stat().st_size,
        media_type="application/json",
        storage_uri="memory://fixture",
        original_uri="https://example.test/query",
        request_params={},
        retrieved_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
    )


def test_query_is_bounded_ordered_geometry_enabled_and_excludes_owner_fields() -> None:
    query = TravisTcadQuery(
        page_size=250,
        max_records=1000,
        cities=("DEL VALLE", "MANOR"),
    )

    params = query.params(0)

    assert params["where"].endswith("situs_city IN ('DEL VALLE','MANOR')")
    assert params["resultRecordCount"] == 250
    assert params["orderByFields"] == "OBJECTID ASC"
    assert params["returnGeometry"] is True
    assert params["outSR"] == 4326
    assert "py_owner_name" not in OUT_FIELDS
    assert "py_owner_id" not in OUT_FIELDS


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"page_size": 1001}, "provider maximum"),
        ({"max_records": 10001}, "10000"),
        ({"where": "1=1"}, "not approved"),
        ({"order_by": "market_value DESC"}, "OBJECTID ASC"),
        ({"cities": ("Manor",)}, "uppercase"),
    ],
)
def test_query_rejects_unbounded_or_unapproved_inputs(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        TravisTcadQuery(**kwargs)  # type: ignore[arg-type]


def test_parser_normalizes_money_provenance_and_replays_deterministically() -> None:
    adapter = TravisTcadArcGisAdapter(TravisTcadQuery())
    content = FIXTURE.read_bytes()

    first, quarantined, exceeded = adapter.parse_page(content=content, artifact=artifact())
    second, _, _ = adapter.parse_page(content=content, artifact=artifact())

    assert first == second
    assert not quarantined
    assert exceeded is False
    assert len(first) == 2
    observation = first[0]
    assert observation.local_parcel_id == "700001"
    assert observation.market_value_cents == 50_000_000
    assert observation.appraised_value_cents == 48_000_000
    assert observation.assessed_value_cents == 45_000_000
    assert observation.improvement_value_cents == 15_000_000
    assert observation.land_value_cents == 35_000_000
    assert observation.artifact_sha256 == FIXTURE_SHA
    assert observation.geometry_srid == 4326
    assert json.loads(observation.geometry_geojson or "")["type"] == "MultiPolygon"
    assert observation.screening_only is True


def test_parser_quarantines_invalid_feature_without_losing_valid_records() -> None:
    content = FIXTURE.read_text().replace('"PROP_ID": 700002', '"PROP_ID": null').encode()
    adapter = TravisTcadArcGisAdapter(TravisTcadQuery())

    observations, quarantined, _ = adapter.parse_page(content=content, artifact=artifact())

    assert len(observations) == 1
    assert len(quarantined) == 1
    assert quarantined[0].source_record_id == "102"
    assert quarantined[0].reason_code == "invalid_feature"


def test_parser_fails_closed_on_schema_drift() -> None:
    content = (
        FIXTURE.read_text()
        .replace(
            '"name": "PROP_ID", "type": "esriFieldTypeInteger"',
            '"name": "PROP_ID", "type": "esriFieldTypeString"',
        )
        .encode()
    )

    with pytest.raises(SourceSchemaError, match="required ArcGIS fields changed"):
        TravisTcadArcGisAdapter(TravisTcadQuery()).parse_page(
            content=content,
            artifact=artifact(),
        )


@pytest.mark.parametrize("include_field_metadata", [False, True])
def test_preflight_rejects_unapproved_field_and_attribute_names(
    include_field_metadata: bool,
) -> None:
    payload = json.loads(FIXTURE.read_text())
    if include_field_metadata:
        payload["fields"].append({"name": "py_owner_name", "type": "esriFieldTypeString"})
    payload["features"][0]["attributes"]["py_owner_name"] = "PROHIBITED"

    with pytest.raises(SourceSchemaError, match="reviewed allowlist"):
        TravisTcadArcGisAdapter(TravisTcadQuery()).validate_page_before_persistence(
            content=json.dumps(payload).encode()
        )


@pytest.mark.parametrize(
    ("spatial_reference", "message"),
    [
        (None, "feature-page schema"),
        ({"wkid": 3857}, "WKID 4326"),
    ],
)
def test_parser_fails_closed_without_exact_response_wkid(
    spatial_reference: dict[str, int] | None,
    message: str,
) -> None:
    payload = json.loads(FIXTURE.read_text())
    if spatial_reference is None:
        payload.pop("spatialReference")
    else:
        payload["spatialReference"] = spatial_reference

    with pytest.raises(SourceSchemaError, match=message):
        TravisTcadArcGisAdapter(TravisTcadQuery()).parse_page(
            content=json.dumps(payload).encode(),
            artifact=artifact(),
        )


def test_geometry_normalizer_groups_holes_and_multiple_outer_rings() -> None:
    geometry = {
        "rings": [
            [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]],
            [[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]],
            [[20, 20], [20, 25], [25, 25], [25, 20], [20, 20]],
        ]
    }

    normalized = json.loads(_polygon_geojson(geometry))

    assert normalized["type"] == "MultiPolygon"
    assert len(normalized["coordinates"]) == 2
    assert sorted(len(polygon) for polygon in normalized["coordinates"]) == [1, 2]


def test_parser_quarantines_missing_or_zero_area_geometry() -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["features"][0]["geometry"] = {
        "rings": [[[-97.61, 30.1], [-97.60, 30.1], [-97.59, 30.1]]]
    }

    observations, quarantined, _ = TravisTcadArcGisAdapter(TravisTcadQuery()).parse_page(
        content=json.dumps(payload).encode(),
        artifact=artifact(),
    )

    assert len(observations) == 1
    assert len(quarantined) == 1
    assert "zero area" in quarantined[0].reason_detail
