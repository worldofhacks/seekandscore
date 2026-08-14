"""Reviewed official-source contract for the frozen 2018 QOZ geography."""

from seekandscore.acquisition.models import AuthorityLevel, SourceDescriptor

CDFI_QOZ_2018_SOURCE_ID = "federal_qoz_2018_designations"
CDFI_QOZ_2018_ROUND_ID = "us-federal-qoz-2018"
CDFI_QOZ_2018_ACTIVATION_ID = "SRC-CDFI-QOZ-2018-IMPORT-20260813-V1"
CDFI_QOZ_2018_PRIVATE_DISPLAY_APPROVAL_ID = (
    "SRC-CDFI-QOZ-2018-PRIVATE-REFERENCE-DISPLAY-20260814-V1"
)
CDFI_QOZ_2018_ARCHIVE_URL = (
    "https://www.cdfifund.gov/system/files/documents/opportunity-zones%3D8764.-9-10-2019.zip"
)
CDFI_QOZ_2018_LANDING_URL = "https://www.cdfifund.gov/opportunity-zones"
CDFI_QOZ_2018_SPREADSHEET_URL = (
    "https://www.cdfifund.gov/system/files/documents/designated-qozs.12.14.18.xlsx"
)
CDFI_QOZ_2018_EXPECTED_SHA256 = "686256f36e2f2f5da6dcea9d6a3f6424eeb994fb97f4f725da14c31576ef7af9"
CDFI_QOZ_2018_EXPECTED_BYTES = 46_685_678
CDFI_QOZ_2018_EXPECTED_TRACTS = 8_764
CDFI_QOZ_2018_EXPECTED_GEOMETRY_REPAIRS = 1
CDFI_QOZ_2018_CENSUS_VINTAGE = 2010
CDFI_QOZ_2018_SRID = 3857
CDFI_QOZ_2018_ADAPTER_VERSION = "cdfi-qoz-2018-shapefile-v1"
CDFI_QOZ_2018_PARSER_VERSION = "cdfi-qoz-2018-tract-v1"

CDFI_QOZ_2018_SOURCE = SourceDescriptor(
    id=CDFI_QOZ_2018_SOURCE_ID,
    name="CDFI Fund 2018 Qualified Opportunity Zone national archive",
    authority="U.S. Department of the Treasury, CDFI Fund; IRS official designation notices",
    authority_level=AuthorityLevel.OFFICIAL_DERIVATIVE,
    jurisdiction_id="us-federal",
    capability="opportunity_zone_geography",
    original_uri=CDFI_QOZ_2018_ARCHIVE_URL,
    query_uri=CDFI_QOZ_2018_ARCHIVE_URL,
    terms_uri=CDFI_QOZ_2018_LANDING_URL,
    attribution_text="U.S. Department of the Treasury, CDFI Fund; 2018 QOZ designations",
    use_limitation=(
        "Frozen 2010-vintage tract geography for screening and reference only. Location does "
        "not establish tax, fund, business, or investment eligibility."
    ),
    cadence="static final 2018 archive",
    freshness_days=3650,
    geographic_vintage="2010 Census tract boundaries used for the 2018 designations",
    adapter_version=CDFI_QOZ_2018_ADAPTER_VERSION,
    parser_version=CDFI_QOZ_2018_PARSER_VERSION,
    contains_personal_data=False,
    # Only coordinate-free derived membership evidence is displayable, behind an independent
    # authenticated-private runtime gate. Geometry export remains prohibited.
    display_allowed=True,
    export_allowed=False,
    redistribution_allowed=False,
)
