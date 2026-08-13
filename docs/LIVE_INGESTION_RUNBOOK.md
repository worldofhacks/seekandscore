# Live ingestion runbook

Research cutoff: **August 13, 2026**. Endpoints and platform behavior are operational dependencies and must be rechecked before activation. A public endpoint is not itself a grant of retention, display, export, redistribution, or automated-access rights.

## Current state

The repository has a bounded, fail-closed contract for the first source, `travis_tcad_parcels`. Committed configuration and every fresh environment keep ingestion disabled. A live process must satisfy all of these independent gates:

```text
APP_ENV=staging or production
DATASET_MODE=live
INGESTION_ENABLED=true
INGESTION_ACTIVATION_ID=<reviewed record id>
INGESTION_SOURCE_ID=travis_tcad_parcels
INGESTION_RUN_PROFILE=proof or cohort
approved source-rights record
durable raw-artifact storage
LIVE_SOURCE_DISPLAY_ENABLED=true only for an approved source descriptor
LIVE_SOURCE_DISPLAY_APPROVAL_ID=SRC-TCAD-TNR-BOUNDED-DISPLAY-20260813-V1
```

The one-shot command is:

```sh
python -m seekandscore.ingestion run --source travis_tcad_parcels
```

`INGESTION_CONFIG_PATH` records the intended profile but is not dynamically consumed in v1. The adapter's endpoint, output fields, base predicate, and ordering are compiled and reviewed; this prevents a YAML-only change from broadening acquisition.

The initial `proof` profile is deliberately only two records. It proves acquisition, artifact persistence, parsing, and database idempotency and is recorded as an intentional partial run; it is never eligible for display. After that proof and replay, the `cohort` profile acquires the official service's 953 matching `DEL VALLE` and `MANOR` records (observed August 13, 2026), bounded at 1,000 records in four 250-record pages and requiring a stable complete count. This is an airport/east-growth research cohort, not full Travis coverage.

## Authoritative source register

### Approved for bounded collection and attributed reference display

| Source | Exact official endpoint/download | Publication/access behavior | Rights and rate-limit posture |
|---|---|---|---|
| Travis TNR/TCAD parcels | [Service ItemInfo](https://gis.traviscountytx.gov/server1/rest/services/Boundaries_and_Jurisdictions/TCAD/MapServer/info/iteminfo), [layer metadata](https://gis.traviscountytx.gov/server1/rest/services/Boundaries_and_Jurisdictions/TCAD/MapServer/0), [query operation](https://gis.traviscountytx.gov/server1/rest/services/Boundaries_and_Jurisdictions/TCAD/MapServer/0/query) | Travis County says the TCAD-derived layer is assembled and updated monthly. ArcGIS reports query/data capability, pagination, and a 1,000-record response maximum. | Exact ItemInfo identifies TCAD and limits the product to informational/reference use with approximate boundaries and no accuracy/completeness warranty. The approved product scope is bounded collection, private raw retention, and attributed display of the non-owner allowlist. Export, redistribution, contact use, legal-boundary conclusions, appraisal, and offers are disabled. TCAD's separate [PDF maps page](https://traviscad.org/maps) is not accessed or mined. |

### Identified official sources; adapters remain disabled

| Capability | Exact official endpoint/download | Cadence/access notes | Activation note |
|---|---|---|---|
| Travis delinquent tax roll | [Download page](https://tax-office.traviscountytx.gov/pages/property.php), [delinquent CSV](https://tax-office.traviscountytx.gov/voterdata/TaxDelqOpenData.csv), [foreclosure process/list](https://tax-office.traviscountytx.gov/properties/foreclosed) | Tax Office says roll files refresh each business day. It publishes a bulk CSV; no public API quota is stated. Fetch at most once per business day with conditional requests and backoff. Auction listings are available roughly 15 days before sale and may be withdrawn. | Separate tax-delinquency and sale-event facts; never treat a listing as final or title-clear. Review retention/redistribution and RealAuction terms before automation. |
| Bastrop CAD parcels/appraisal | [Download/disclaimer page](https://bastropcad.org/data-downloads/), [2026 certified real-property export](https://bastropcad.org/wp-content/uploads/2026/07/2026-RE-PUBLIC-DOWNLOAD-AS-OF-CERTIFICATION.zip), [GIS ZIP](https://bastropcad.org/wp-content/uploads/GIS/Bastrop.zip) | Official bulk ZIPs; the site says users must accept its export disclaimer, provides no technical support, and reports GIS updates separately. No API quota is published. Prefer a single version check and download no more than weekly during preliminary/supplement periods. | Record acceptance text/timestamp and obtain rights approval before retention, display, export, or redistribution. A dated certified ZIP is safer than scraping property search. |
| Caldwell CAD parcels/appraisal | [Public data page](https://caldwellcad.org/publicly-available-data/), [2026 certified export](https://caldwellcad.org/wp-content/uploads/2026/07/2026-Caldwell-Certified-CAD-Export-Files-updated-July-31.zip), [2026 layout](https://caldwellcad.org/wp-content/uploads/2026/07/2026-Layout-Files.zip) | Caldwell says standard preliminary, certified, and collection exports are typically produced once a year; other exports require a request and fee. No API quota is published. | Poll the landing page sparingly, snapshot dated official exports, and do not automate third-party search/map interfaces. Complete rights review first. |
| FEMA effective flood hazard | [FEMA products page](https://www.fema.gov/flood-maps/products-tools), [Map Service Center](https://msc.fema.gov/portal/home), [NFHL REST service](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer) | FEMA describes MSC as the official source and NFHL as current effective flood-map data. Bulk NFHL geodatabases are free downloads. No general REST quota is published. Prefer state/county bulk artifacts for snapshots over parcel-by-parcel queries. | Store effective map/product dates and treat results as screening, not a survey or coverage determination. Adapter remains disabled until the effective-layer/version process is tested. |
| 2018 Opportunity Zone designations | [CDFI archive](https://www.cdfifund.gov/opportunity-zones), [designation spreadsheet](https://www.cdfifund.gov/system/files/documents/designated-qozs.12.14.18.xlsx), [2010-vintage shapefile](https://www.cdfifund.gov/system/files/documents/opportunity-zones%3D8764.-9-10-2019.zip), [IRS Notice 2018-48](https://www.irs.gov/pub/irs-drop/n-18-48.pdf), [IRS Notice 2019-42](https://www.irs.gov/pub/irs-drop/n-19-42.pdf) | Static federal downloads. CDFI is an official machine-readable archive; the IRS notices are the legal designation lists. | Do not calculate parcel membership until the frozen 2010 tract geometry and boundary-quality join are implemented. Do not infer tax qualification from location. |
| 2010 Census tract geometry | [TIGER/Line directory](https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/), [Travis](https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/tl_2010_48453_tract10.zip), [Bastrop](https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/tl_2010_48021_tract10.zip), [Caldwell](https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/tl_2010_48055_tract10.zip) | Static Census bulk files. Census geographic data is not copyrighted; source acknowledgment is requested. | Use only the matching vintage for the 2018 cohort. Never transfer legal designation through a 2010–2020 crosswalk. |
| 2027 eligible LIC tracts | [Treasury QOZ data hub](https://home.treasury.gov/policy-issues/tax-policy/data-transparency/qualified-opportunity-zones), [eligible-tract workbook](https://home.treasury.gov/system/files/131/OZ2-Eligible-LIC-Tracts-Data-Transparency-03232026.xlsx), [Revenue Procedure 2026-14](https://www.irs.gov/pub/irs-drop/rp-26-14.pdf) | The new designation cycle opened July 1, 2026. This workbook is a candidate/eligibility input, not a final designation list. | Label records `eligible`, never `designated`. Snapshot nominations/certifications as separate temporal observations when Treasury publishes them. |
| Texas 2027 nomination lifecycle | [Governor EDT process page](https://gov.texas.gov/business/page/opportunity-zones), [Texas eligible-tract workbook](https://gov.texas.gov/uploads/files/business/Texas_OZ_Eligible.xlsx) | At the cutoff, Texas targets state submission by August 17, 2026 and reports Treasury certification expected by November 28, 2026; no final state nomination list was found on the official page. | Treat the page as state process context and any future state selection as `state_nominated`, never Treasury-certified or effective. Recheck the page after the submission target. |

Federal works are generally not copyrightable under 17 U.S.C. §105, but agency terms, marks, privacy rules, and third-party material can still apply. County public-record availability likewise does not answer automated access or product redistribution. Each adapter needs the source-policy review described in [`SOURCE_INVENTORY.md`](SOURCE_INVENTORY.md).

## Bounded Travis query contract

The server advertises a maximum of 1,000 records per response. Repository defaults select the private two-record proof:

```text
INGESTION_RUN_PROFILE=proof
INGESTION_PAGE_SIZE=2
INGESTION_MAX_RECORDS=2
INGESTION_WHERE=PROP_ID IS NOT NULL AND tcad_acres >= 1
INGESTION_ORDER_BY=OBJECTID ASC
INGESTION_CITIES=DEL VALLE,MANOR
INGESTION_MIN_REQUEST_INTERVAL_SECONDS=1
INGESTION_MAX_RETRIES=3             # hard maximum 5
```

For the reviewed complete staging cohort, use this exact profile:

```text
INGESTION_RUN_PROFILE=cohort
INGESTION_PAGE_SIZE=250
INGESTION_MAX_RECORDS=1000
INGESTION_CITIES=DEL VALLE,MANOR
```

When ingestion is enabled, the runtime rejects any other profile, bounds, or city set. Keep the base predicate and order exactly as shown. The cohort profile performs an upstream count preflight before fetching any page, fails if the result exceeds 1,000, and rechecks the count after acquisition to reject a changing or incomplete snapshot.

The adapter must paginate deterministically by `OBJECTID`, request only its fixed field list, enforce a single concurrent request, and reject arbitrary `where`, `orderByFields`, or `outFields` input. The first feed explicitly excludes `py_owner_id`, `py_owner_name`, and `py_address`; it is not an owner/contact acquisition feed. On `429` or transient `5xx`, honor `Retry-After`, use capped exponential backoff, and fail the run after the bounded retry count. A partial fetch is never promoted as a complete snapshot.

## Artifact storage contract

Fetch bytes are evidence. Persist them before parsing under a content-addressed key such as:

```text
raw-artifacts/travis_tcad_parcels/<first-two-sha256-chars>/<sha256>.json
```

The database artifact row records the source, exact request parameters, first retrieval time, media type, byte count, SHA-256, object key, and response ETag. The source-run row separately records the activation ID, configuration hash, adapter/parser versions, timestamps, counts, and ordered artifact references. Never overwrite a key. Repeated identical bytes reuse the same content object and artifact row. V1 does not yet create a separate retrieval-receipt row when an identical response is fetched again; add that ledger before making compliance-grade claims about preserving every individual HTTP exchange.

Native development without S3 credentials uses `./var/raw-artifacts`; the Compose ingestion process uses its private MinIO bucket. MinIO initialization enables versioning and removes anonymous access. Source artifacts, database dumps, and owner/contact data are never committed.

For staging, use a private Railway bucket named `raw-artifacts` in `sjc`. At the cutoff, Railway lists storage at $0.015/GB-month with bucket operations and bucket egress free; service egress can still be billed. Railway buckets are S3-compatible and environment-isolated, but do **not** support server-side encryption controls, object versioning, object lock, lifecycle policies, or native backups. Therefore content-addressed, create-only application writes are mandatory and a verified external copy is required before the bucket becomes the sole evidence store. Do not claim regulatory immutability from a Railway bucket.

Map the bucket's Railway-provided variables to the application only on acquisition services:

```text
OBJECT_STORAGE_BUCKET=${{raw-artifacts.BUCKET}}
OBJECT_STORAGE_ACCESS_KEY_ID=${{raw-artifacts.ACCESS_KEY_ID}}
OBJECT_STORAGE_SECRET_ACCESS_KEY=${{raw-artifacts.SECRET_ACCESS_KEY}}
OBJECT_STORAGE_REGION=${{raw-artifacts.REGION}}
OBJECT_STORAGE_ENDPOINT=${{raw-artifacts.ENDPOINT}}
OBJECT_STORAGE_FORCE_PATH_STYLE=false
```

Do not copy these credentials to web or browser-visible variables. Railway uses virtual-hosted-style URLs for new buckets; confirm the bucket Credentials tab because older buckets may require path style.

## Local proof run

1. Install locked dependencies, copy `.env.example` to an untracked `.env`, and start infrastructure with `make infra-up`.
2. Run `make ingestion-check`; it must report acquisition disabled.
3. Review and record the source rights decision and create a unique activation ID.
4. For an approved bounded staging-style local test, retain the exact `proof` profile from `.env.example`, export the four reviewed gate values, and run `make ingestion-run-local`. The target passes `APP_ENV`, `DATASET_MODE`, `INGESTION_ENABLED`, and `INGESTION_ACTIVATION_ID` only from the caller; absent or invalid values fail closed.
5. Verify a raw object/checksum exists before normalized records, rerun the same slice, and confirm idempotency.
6. Set `INGESTION_ENABLED=false` immediately after the proof.

Do not install a local recurring job until the three-run idempotency test and kill-switch drill pass. After approval, the OS scheduler may invoke `make -C /absolute/repository/path ingestion-run-local`; load the activation ID from a protected scheduler environment/secret file, never inline it in a crontab or committed script. Use the same monthly `17 9 2 * *` UTC cadence as Railway.

## Railway staging rollout checklist

1. Create a staging-only `raw-artifacts` bucket in `sjc`; keep it private and record its immutable region choice.
2. Use the pinned `postgis/postgis:17-3.5` single-node service with one persistent volume mounted at `/var/lib/postgresql/data`. Set `PGDATA=/var/lib/postgresql/data/pgdata`; writing directly to the mounted root fails because Railway initializes it with `lost+found`. Keep it private, configure Railway volume backups, create an external logical backup, and accept the single-node limitation.
3. Deploy API from `/infra/railway/api.example.toml` and web from `/infra/railway/web.example.toml`. API is the only migration owner. Reference the private database as `DATABASE_URL=${{PostGIS.DATABASE_URL}}`; never add a public database TCP proxy for application traffic.
4. Deploy the manual acquisition proof from `/infra/railway/ingestion-travis.example.toml`. Give it PostGIS and `raw-artifacts` references, but no public domain, Redis, outreach, alert-provider, auth, or web secrets. This template intentionally has no cron.
5. First deploy it with `APP_ENV=staging`, `DATASET_MODE=live`, `INGESTION_ENABLED=false`, `INGESTION_SOURCE_ID=travis_tcad_parcels`, `INGESTION_RUN_PROFILE=proof`, exact page/max records `2`/`2`, exact cities `DEL VALLE,MANOR`, and no activation ID. Confirm the command fails closed without a network acquisition.
6. Run database migration from the API pre-deploy owner and verify API `/readyz` before any source run.
7. Reference the recorded private-acquisition decision, then set `INGESTION_ENABLED=true` and the exact reviewed activation ID only on the acquisition service. Execute the two-record `proof` profile and replay it once. Require two fetched records, no quarantine, a content-addressed private raw artifact, and no duplicate normalized rows on replay; then disable ingestion and clear the activation ID.
8. Immediately recheck the exact official `returnCountOnly` query. Proceed only when it is exactly 953. Set `INGESTION_RUN_PROFILE=cohort`, page/max records `250`/`1000`, and exact cities `DEL VALLE,MANOR`; run the complete cohort and replay it once. Both runs must be complete, stable at 953, and free of quarantined rows. Disable ingestion and clear the activation ID after validation.
9. Verify raw object durability/checksums, source-run profile and status, artifact lineage, exactly bounded request count, parser outcome, and replay idempotency. Exercise the kill switch and inspect logs for secret/query leakage.
10. Only after both proof and cohort replays pass, change the service config path to `/infra/railway/ingestion-travis.cron.example.toml`, retain `INGESTION_RUN_PROFILE=cohort`, page/max `250`/`1000`, exact cities, and the reviewed acquisition activation ID, then enable the monthly `17 9 2 * *` schedule. Railway cron is UTC, may start late, and skips a new run while the previous process remains active; the process must exit and close connections.
11. Keep live display off during ingestion validation. After the complete cohort and replay checks pass, protect the public web origin with the required single-operator access gate, keep the API private, and enable reference display with `LIVE_SOURCE_DISPLAY_APPROVAL_ID=SRC-TCAD-TNR-BOUNDED-DISPLAY-20260813-V1`. Keep export, redistribution, outreach, and provider alert delivery off. Enabling acquisition alone never grants those capabilities.

## Incident stop and replay

Set `INGESTION_ENABLED=false`, remove the cron schedule or pause the service, and preserve the failed run and artifact. Do not delete or overwrite source evidence. Record the last good artifact/cursor, classify rights/schema/quality/provider failure, patch against a saved fixture, and replay from the immutable object without contacting the source. Resumption requires a new reviewed activation ID when the prior approval scope changed.
