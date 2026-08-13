"""Small registry contract and synthetic foundation data."""

from pydantic import BaseModel, ConfigDict


class Jurisdiction(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    country_code: str
    state_fips: str
    county_fips: str
    state_name: str
    county_name: str
    timezone: str
    region_pack_id: str


class InMemoryGeographyRegistry:
    """Read-only registry used until the database-backed registry lands."""

    def __init__(self, jurisdictions: tuple[Jurisdiction, ...] | None = None) -> None:
        entries = jurisdictions or _SYNTHETIC_JURISDICTIONS
        self._by_id = {entry.id: entry for entry in entries}
        if len(self._by_id) != len(entries):
            raise ValueError("jurisdiction identifiers must be unique")

    def get(self, jurisdiction_id: str) -> Jurisdiction | None:
        return self._by_id.get(jurisdiction_id)

    def is_ready(self) -> bool:
        return bool(self._by_id) and all(item.timezone for item in self._by_id.values())


_SYNTHETIC_JURISDICTIONS = (
    Jurisdiction(
        id="us-tx-453",
        country_code="US",
        state_fips="48",
        county_fips="453",
        state_name="Texas",
        county_name="Travis County",
        timezone="America/Chicago",
        region_pack_id="us-tx-central-texas",
    ),
    Jurisdiction(
        id="us-tx-021",
        country_code="US",
        state_fips="48",
        county_fips="021",
        state_name="Texas",
        county_name="Bastrop County",
        timezone="America/Chicago",
        region_pack_id="us-tx-central-texas",
    ),
    Jurisdiction(
        id="us-tx-055",
        country_code="US",
        state_fips="48",
        county_fips="055",
        state_name="Texas",
        county_name="Caldwell County",
        timezone="America/Chicago",
        region_pack_id="us-tx-central-texas",
    ),
)
