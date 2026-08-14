# Live 2018 Opportunity Zone rollout

Status: implementation-ready, default off. This runbook covers the frozen 2018
federal layer and its deterministic join to the approved 953-record Travis
County parcel cohort. It does not authorize owner/contact collection, outreach,
export, redistribution, public display, or a tax-qualification claim.

## 1. Reviewed official-source snapshot

Verified against the live official endpoints on August 14, 2026:

| Evidence | Reviewed value |
|---|---|
| CDFI resource page | <https://www.cdfifund.gov/opportunity-zones> |
| Frozen CDFI archive | <https://www.cdfifund.gov/system/files/documents/opportunity-zones%3D8764.-9-10-2019.zip> |
| Archive bytes | `46,685,678` |
| Archive SHA-256 | `686256f36e2f2f5da6dcea9d6a3f6424eeb994fb97f4f725da14c31576ef7af9` |
| Unique tract GEOIDs | `8,764` |
| Geometry contract | 2010 Census tract boundaries; EPSG:3857; `MULTIPOLYGON` |
| Reviewed topology repairs | exactly `1`, with per-tract repair lineage |
| Texas / Travis subset | 628 Texas tracts; 21 Travis County tracts |
| Supporting workbook | <https://www.cdfifund.gov/system/files/documents/designated-qozs.12.14.18.xlsx> |
| Current workbook snapshot | `276,974` bytes; SHA-256 `96b791f36d1065ab975196a4a545b6bb4ea4afaa6fdae865baf50c0e7b170891`; 8,764 unique GEOIDs |

The ZIP, not the separately served workbook bytes, is the import contract. The
ZIP contains its own workbook and Readme, and all six required shapefile members
are validated before extraction. The supporting workbook may be snapshotted as
additional evidence but cannot replace the pinned archive.

[IRS Notice 2018-48](https://www.irs.gov/pub/irs-drop/n-18-48.pdf) and
[IRS Notice 2019-42](https://www.irs.gov/pub/irs-drop/n-19-42.pdf) are the
official designation lists. [IRS Notice 2026-40](https://www.irs.gov/pub/irs-drop/n-26-40.pdf)
confirms that the prior designation period ends December 31, 2027 for Puerto
Rico and December 31, 2028 for the other 2018 designations. CDFI states that the
2018 boundaries remain the boundaries at designation even when later Census
releases redefine tracts.

CDFI describes its site as public information that may be copied and
distributed with credit. Census federal materials are reproducible with source
citation. Preserve both agencies' attribution and the Census disclaimer that
statistical boundaries are not legal land descriptions. The platform's product
policy remains intentionally stricter: authenticated reference display only;
no export or redistribution.

The current official [Travis TCAD feature layer](https://gis.traviscountytx.gov/server1/rest/services/Boundaries_and_Jurisdictions/TCAD/MapServer/0)
still reports polygon geometry, source WKID 2277, query support, a 1,000-record
page limit, and monthly TNR assembly. The approved live count query still
returns exactly 953 `DEL VALLE`/`MANOR` records. A reviewed query with
`returnGeometry=true&outSR=4326` returns polygon rings without requesting owner
fields.

## 2. Railway baseline before activation

Read-only audit on August 14, 2026:

- staging web, API, PostGIS, and monthly Travis ingestion are healthy;
- API, PostGIS, ingestion, and migration services have no public domain;
- `ingestion-travis` is scheduled for `17 9 2 * *` UTC and next runs on
  September 2, 2026;
- `db-migrate` is stopped and its owner URL is blank at rest;
- production has no service instances;
- private bucket `seekandscore-raw-staging` exists and the Travis service has a
  complete S3 reference set;
- create a separate private `seekandscore-qoz-raw-staging` bucket before the
  federal import so that its one-shot credentials cannot read Travis artifacts;
- the owner URL is absent from web, API, and ingestion; bucket credentials are
  absent from web and API; and no OZ activation variables exist yet.

Do not attach QOZ variables to the existing API, web, or Travis ingestion
service. Create a private import service and a separate private membership
service, and keep GitHub autodeploy off for both.

## 3. Database and service boundary

Migration service only:

```text
OZ_IMPORTER_DATABASE_LOGIN_ROLE=seekandscore_oz_importer
OZ_IMPORTER_DATABASE_PASSWORD=<distinct sealed 32+ character URL-safe value>
OZ_IMPORTER_RUNTIME_DATABASE_URL=<sealed restricted URL for that login>
OZ_MEMBERSHIP_DATABASE_LOGIN_ROLE=seekandscore_oz_membership
OZ_MEMBERSHIP_DATABASE_PASSWORD=<different sealed 32+ character URL-safe value>
OZ_MEMBERSHIP_RUNTIME_DATABASE_URL=<sealed restricted membership URL>
```

`db-migrate` is the only service that temporarily receives
`MIGRATION_DATABASE_URL`. It applies the migration, provisions the LOGIN as the
sole member of `seekandscore_oz_importer_runtime`, provisions the membership
LOGIN as the sole member of `seekandscore_oz_membership_runtime`, and audits all
four application contracts. Neither QOZ runtime has an owner URL or can own
schema objects, change roles, run migrations, or access deal, engagement,
delivery, or research data. The recurring membership role also cannot mutate
registry/raw artifacts or import the federal source.

The private `oz-import-2018` service receives only:

```text
APP_ENV=staging
DATASET_MODE=live
DATABASE_URL=<OZ_IMPORTER_RUNTIME_DATABASE_URL value>
OZ_IMPORTER_DATABASE_LOGIN_ROLE=seekandscore_oz_importer
OBJECT_STORAGE_BUCKET=${{seekandscore-qoz-raw-staging.BUCKET}}
OBJECT_STORAGE_ACCESS_KEY_ID=${{seekandscore-qoz-raw-staging.ACCESS_KEY_ID}}
OBJECT_STORAGE_SECRET_ACCESS_KEY=${{seekandscore-qoz-raw-staging.SECRET_ACCESS_KEY}}
OBJECT_STORAGE_REGION=${{seekandscore-qoz-raw-staging.REGION}}
OBJECT_STORAGE_ENDPOINT=${{seekandscore-qoz-raw-staging.ENDPOINT}}
OBJECT_STORAGE_FORCE_PATH_STYLE=false
OBJECT_STORAGE_PREFIX=raw-artifacts
OZ_2018_IMPORT_ENABLED=false
OZ_2018_IMPORT_ACTIVATION_ID=
OUTREACH_MODE=disabled
OUTREACH_SEND_ENABLED=false
```

It has no domain, cron, Redis, API/research token, web credential, alert-provider
credential, outreach credential, or other database login. Railway bucket
credentials are bucket-wide, not prefix-scoped, so this rollout requires the
dedicated QOZ bucket. Keep the importer stopped and its credentials sealed
between reviewed runs.

The private `oz-membership-refresh` service receives only
`DATABASE_URL=<OZ_MEMBERSHIP_RUNTIME_DATABASE_URL value>`,
`OZ_MEMBERSHIP_DATABASE_LOGIN_ROLE=seekandscore_oz_membership`,
`APP_ENV=staging`, `DATASET_MODE=live`, and these gates:

```text
OZ_2018_MEMBERSHIP_BUILD_ENABLED=false
OZ_2018_MEMBERSHIP_BUILD_ACTIVATION_ID=
OUTREACH_MODE=disabled
OUTREACH_SEND_ENABLED=false
```

It receives no bucket, HTTP-source, import, API/research, web, outreach, alert,
or other service credentials and has no domain. Use the manual config for the
first build and replay; attach the cron config only after both pass.

Railway buckets are private and S3-compatible, but currently lack server-side
encryption controls, object versioning, object lock, lifecycle configuration,
and native snapshots/backups. The application key is content-addressed and
create-only. Make a checksum-verified off-project copy before treating Railway
as the sole evidence store.

## 4. Ordered release and activation

### A. Release the additive schema and restricted role

1. Require green lint, type, backend, web, configuration, secret, and real
   PostGIS tests at one exact commit SHA.
2. Confirm the migration creates `identity.parcel`, `geo.parcel_geometry`, the
   frozen QOZ tables, membership snapshot/build/evidence tables, and the four
   audited runtime capability roles.
3. Temporarily restore the owner reference only on stopped `db-migrate`; add the
   six OZ role variables above; deploy `db-migrate` at the exact SHA.
4. Require release `apply` and `verify` at the same Alembic head, with all four
   login audits passing. Any failure blocks the rollout.
5. Stop `db-migrate`, blank its owner reference without deploying, and verify
   that owner credentials remain absent from every application service.
6. Deploy API with its existing restricted URL. It may read membership evidence
   and non-coordinate provenance only; it cannot import or build it.

### B. Acquire a geometry-complete parcel cohort

1. Deploy the updated Travis parser under version
   `travis-tcad-parcel-geometry-v2` using the existing approved cohort bounds:
   cities `DEL VALLE,MANOR`, page size 250, maximum 1,000, and the existing TCAD
   acquisition activation ID.
2. Require a complete 953-record run with zero quarantine, 953 observations,
   953 stable parcel identities, and 953 valid PostGIS parcel geometries.
3. Require source SRID 4326 on every stored evidence record, database geometry
   SRID 3857 on every normalized geometry, non-empty multipolygons, and exact
   repair counts recorded by the run. Missing geometry blocks membership.
4. Replay the same bounded cohort once. It must be unchanged/idempotent and must
   not create duplicate parcel identities or geometry rows.
5. Restore the existing monthly cron only after both runs pass. This refreshes
   parcel geometry; it does not alter the frozen 2018 tract layer automatically.

### C. Import and replay the frozen federal layer

1. Create the private unscheduled service at the exact release SHA with
   `/infra/railway/oz-import-2018.example.toml`; keep its import gate false first
   and confirm the process refuses the import before an HTTP request.
2. Set only:

   ```text
   OZ_2018_IMPORT_ENABLED=true
   OZ_2018_IMPORT_ACTIVATION_ID=SRC-CDFI-QOZ-2018-IMPORT-20260813-V1
   ```

3. Run one deployment. Require `succeeded`, SHA and byte equality, one immutable
   object, one round, 8,764 unique tracts, one reviewed geometry repair, and no
   partial layer.
4. Redeploy the exact same SHA and settings once. Require
   `succeeded_unchanged`, the same artifact ID/SHA, no new round or tract rows,
   and a second immutable import-run receipt.
5. Stop the service; set the import flag false and blank its activation ID
   without starting another process.

### D. Build and replay parcel membership

1. Confirm the latest complete 953-record geometry cohort and complete 8,764
   tract round are the selected inputs.
2. Create/use the separate private `oz-membership-refresh` service with
   `/infra/railway/oz-membership-build.example.toml` and set only:

   ```text
   OZ_2018_MEMBERSHIP_BUILD_ENABLED=true
   OZ_2018_MEMBERSHIP_BUILD_ACTIVATION_ID=GEO-TCAD-QOZ-2018-MEMBERSHIP-20260814-V1
   ```

3. Run once. The transaction must evaluate exactly 953 parcels. Every parcel is
   classified `inside`, `outside`, or `boundary_review`; missing geometry must
   equal zero and the three classifications must sum to 953.
4. An `inside` result requires exactly one intersecting designated tract. Any
   parcel touching or intersecting more than one designation boundary is
   `boundary_review`, never silently promoted. `outside` requires zero
   intersections.
5. Run the same build a second time. Require `succeeded_unchanged`, one immutable
   snapshot for the cohort/round/algorithm tuple, no duplicate memberships, and
   a second build receipt.
6. Stop the service; set the membership flag false and blank its activation ID.
7. Switch to `/infra/railway/oz-membership-verify.example.toml` and run the
   read-only verifier. It must pass without either data-changing gate.
8. Restore the exact membership gate, switch to
   `/infra/railway/oz-membership-build.cron.example.toml`, and attach
   `47 9 2 * *` UTC only after verification. If activated on August 14, 2026,
   the expected first membership run is September 2, 2026 at 09:47 UTC, 30
   minutes after the TCAD run scheduled for 09:17 UTC.
9. Read the Railway service instance back after activation. Acceptance requires
   `cronSchedule="47 9 2 * *"` and a non-null `nextCronRunAt` equal to the next
   intended UTC window. A config manifest alone did not persist the cron during
   the prior TCAD rollout. If the read-back is blank, use the same narrow
   Railway `serviceInstanceUpdate(cronSchedule)` correction and read it back
   again; do not change any other service field.
10. Scheduling must not execute the builder immediately. Record the
    build-receipt count immediately before and after activation and require no
    new membership build receipt until the first scheduled window (or a
    separately approved manual replay).

The scheduled builder must inspect the newest TCAD attempt before choosing a
cohort. A running, failed, partial, quarantined, or geometry-incomplete newest
attempt makes the job fail closed; it must not silently rebuild an older cohort.
For a successful newest cohort, derive `expected_parcels` from that complete
cohort and its artifacts rather than hardcoding 953. If TCAD succeeds but the
membership run is late, skipped, or fails, authenticated OZ display for the new
cohort remains unavailable until a manual build and unchanged replay pass. If
TCAD itself fails, retain the prior immutable snapshot but surface the source
refresh error and rerun TCAD before a membership build.

### E. Enable authenticated reference display

Only after all prior stages pass, set the API/web private-display gate:

```text
OZ_2018_PRIVATE_DISPLAY_ENABLED=true
OZ_2018_PRIVATE_DISPLAY_APPROVAL_ID=SRC-CDFI-QOZ-2018-PRIVATE-REFERENCE-DISPLAY-20260814-V1
```

Deploy API and web at the same exact SHA. The browser must remain behind Basic
authentication. Display classification, tract GEOID when unambiguous, 2010
vintage, source/freshness, effective interval, and screening/disclaimer text.
Do not return polygon coordinates, bulk export, owner/contact fields, outreach
actions, or a statement that the property or investment qualifies for a tax
benefit.

## 5. Database verification

Run aggregate checks through an approved operator/read-only path. Do not export
the parcel or geometry tables.

```sql
SELECT status, imported_tracts, source_artifact_sha256
FROM geo.opportunity_zone_import_run
ORDER BY started_at DESC
LIMIT 2;

SELECT count(*) AS rounds
FROM geo.opportunity_zone_round
WHERE id = 'us-federal-qoz-2018';

SELECT count(*) AS tracts,
       count(DISTINCT tract_geoid) AS unique_geoids,
       count(*) FILTER (WHERE geometry_was_repaired) AS repaired,
       bool_and(ST_IsValid(geometry)) AS all_valid,
       bool_and(ST_SRID(geometry) = 3857) AS all_3857
FROM geo.opportunity_zone_tract
WHERE round_id = 'us-federal-qoz-2018';

SELECT count(*) AS parcels,
       count(DISTINCT parcel_id) AS unique_parcels,
       bool_and(ST_IsValid(geometry)) AS all_valid,
       bool_and(ST_SRID(geometry) = 3857) AS all_3857
FROM geo.parcel_geometry
WHERE parser_version = 'travis-tcad-parcel-geometry-v2';

SELECT status, expected_parcels, evaluated_parcels, inside_count, outside_count,
       boundary_review_count, missing_geometry_count
FROM geo.opportunity_zone_membership_build_run
ORDER BY started_at DESC
LIMIT 2;

WITH latest AS (
    SELECT id
    FROM geo.opportunity_zone_membership_snapshot
    ORDER BY created_at DESC
    LIMIT 1
)
SELECT classification, count(*)
FROM geo.opportunity_zone_membership
WHERE membership_snapshot_id = (SELECT id FROM latest)
GROUP BY classification
ORDER BY classification;
```

Expected frozen-layer invariants are one round, 8,764 unique tracts, exactly one
tract repair, valid SRID-3857 geometry, and two successful import receipts ending
in `succeeded_unchanged`. Expected current-cohort invariants are 953 evaluated,
zero missing geometry, a classification total of 953, one immutable membership
snapshot, and a final `succeeded_unchanged` build receipt.

## 6. Kill switch and recovery

At any failure, stop the QOZ service, disable the relevant flag, blank the
activation ID, and keep private display false. Preserve every failed run,
artifact, quarantine record, and immutable snapshot. Do not delete or overwrite
evidence to make a retry pass.

- Archive hash/size/schema/count mismatch: do not import; investigate the
  official publication and require a new source review before changing pins.
- Tract repair-count change: fail closed; do not normalize an unreviewed layer.
- Incomplete parcel geometry: rerun or repair the approved ingestion parser;
  never fill gaps with centroids, geocoding, or synthetic polygons.
- Monthly sequencing failure: keep the new cohort's OZ display unavailable;
  after TCAD completes successfully, run membership manually, replay it
  unchanged, then leave the monthly cron attached.
- Boundary ambiguity: retain `boundary_review`; do not coerce it to `inside`.
- Import/build conflict on replay: keep display off and compare immutable inputs,
  algorithm version, and stored evidence before issuing a new activation ID.
- Display regression: disable only the private-display gate; the imported source
  and membership evidence remain preserved and private.

The static 2018 source import is never scheduled. Only the derived membership
refresh runs monthly after TCAD because a new cohort has a new immutable ID. A
future official correction or the 2027 designation round is a new versioned
source, review, schema status, and activation—not an overwrite of this layer.

## 7. Expansion contract

The one national 8,764-tract import already supplies the frozen 2018 reference
layer for every U.S. jurisdiction. Do not download or duplicate it for each new
market. Expansion consists of onboarding a new official parcel cohort and
building a new immutable membership snapshot against the shared round.

For each jurisdiction, require a separately reviewed source descriptor,
allowlisted query bounds, proof and complete-cohort activation IDs, parser and
geometry versions, source-specific freshness policy, and a restricted ingestion
service. Exclude owner/contact fields from the adapter and artifact request.
Schedule a membership-only job after that source's successful cohort window;
derive its expected count from the newest complete run and refuse any newer
failed, running, partial, quarantined, or geometry-incomplete attempt.

Before the current Travis-specific builder serves another jurisdiction,
parameterize its parcel source and jurisdiction through a checked-in allowlist,
not a free-form runtime value. Preserve `source_id`, `cohort_run_id`, federal
round, algorithm version, parser version, and artifact hashes in every snapshot
key and receipt. Give each acquisition worker only its source/bucket grants and
each membership worker the common membership capability with no download or
raw-artifact mutation. Use dedicated buckets when credential isolation matters;
otherwise use immutable, source-scoped content-addressed prefixes and keep an
external checksum-verified evidence copy.

Add capacity only from observed load: PostGIS GiST indexes and bounded cohort
transactions first, then jurisdiction-partitioned workers and queues. Never
trade complete-cohort checks, boundary review, immutable replay, or authenticated
reference-only display for throughput. The future 2027 federal designation
round remains a separate source/round/algorithm review and cannot overwrite or
silently reclassify the 2018 evidence.
