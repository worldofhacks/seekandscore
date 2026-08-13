"""Official TCAD ArcGIS adapter contract tests."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from seekandscore.acquisition.adapters.travis_tcad import (
    OUT_FIELDS,
    SourceSchemaError,
    TravisTcadArcGisAdapter,
    TravisTcadQuery,
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
