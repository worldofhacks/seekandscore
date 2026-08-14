# Railway configuration

The files in this directory are per-service configurations aligned with the runnable monorepo scaffold and root build context. Every application runtime is live-only and database-backed; there are no synthetic preview configurations. These files do not provision a Railway project or external resource by themselves.

Planned service mapping:

| Service | Config path | Start behavior |
|---|---|---|
| `web` | `/infra/railway/web.example.toml` | database-backed Next.js server template |
| `db-migrate` | `/infra/railway/db-migrate.example.toml` | one-shot owner-only migration, role provisioning, and verification |
| `api` | `/infra/railway/api.example.toml` | FastAPI with audited restricted API login; never migrates |
| `worker-discovery` | `/infra/railway/worker-discovery.example.toml` | acquisition queues using the restricted ingestion login |
| `worker-enrichment` | `/infra/railway/worker-enrichment.example.toml` | blocked until a dedicated role is approved |
| `worker-engagement` | `/infra/railway/worker-engagement.example.toml` | blocked until a dedicated role and activation are approved |
| `scheduler` | `/infra/railway/scheduler.example.toml` | blocked until a dedicated role is approved |
| `ingestion-travis` | `/infra/railway/ingestion-travis.example.toml` | manual bounded TCAD proof; fail-closed until source activation |
| `ingestion-travis` (scheduled) | `/infra/railway/ingestion-travis.cron.example.toml` | same process with monthly UTC cron, attached only after proof |
| `oz-import-2018` | `/infra/railway/oz-import-2018.example.toml` | manual frozen CDFI layer import and unchanged replay |
| `oz-membership-refresh` (manual) | `/infra/railway/oz-membership-build.example.toml` | manual complete-cohort parcel spatial join |
| `oz-membership-refresh` (verify) | `/infra/railway/oz-membership-verify.example.toml` | read-only frozen-layer and membership invariant check |
| `oz-membership-refresh` | `/infra/railway/oz-membership-build.cron.example.toml` | monthly join refresh after a new complete TCAD cohort |

Every Python image enters through `scripts/runtime/python-entrypoint.sh`. Unless an environment explicitly provides values, it forces these inert defaults:

```text
DATASET_MODE=live
INGESTION_ENABLED=false
ALERT_DELIVERY_MODE=log
OUTREACH_MODE=disabled
OUTREACH_SEND_ENABLED=false
```

Set the same values explicitly in every Railway environment so deployment state is visible in the dashboard. Missing variables remain safe; changing a variable alone does not bypass application policy gates. When activating a template, record live-schema validation in the associated issue and retain the repository root as the build context.

Every deployed Python runtime also passes through a database-role audit before
the application command starts. The API must authenticate as `seekandscore_api`
and acquisition processes as `seekandscore_ingestion`; the audit rejects table
ownership, role administration, DDL, extra memberships, or privileges outside
the exact table/column contract. `worker-enrichment`, `worker-engagement`, and
`scheduler` intentionally refuse to start until separate roles exist.

The web service additionally refuses to start in staging or production unless
the single-operator access gate is complete:

```text
WEB_PRIVATE_ACCESS_ENABLED=true
WEB_PRIVATE_ACCESS_USERNAME=<sealed server-only value>
WEB_PRIVATE_ACCESS_PASSWORD=<sealed generated high-entropy value, 24+ characters>
```

Never prefix either credential with `NEXT_PUBLIC_`. The gate protects every web
path except the data-free `/api/health` Railway check. Keep the API on Railway
private networking when live display is enabled; a public API domain is not
protected by the web credential.

If saved-research writes are enabled, also set `WEB_PUBLIC_ORIGIN` to the exact
public HTTPS web origin without a trailing slash (for example,
`https://web-staging-7db2.up.railway.app`). The web refuses to start if this
value is missing, non-HTTPS, contains credentials/path/query/fragment, or is not
already in canonical origin form. Mutation requests must carry that exact
browser `Origin`; Railway's internal request URL is deliberately not trusted.

See [the full deployment plan](../../docs/RAILWAY_DEPLOYMENT.md).

## First live-ingestion service

`ingestion-travis` is separate from the general scheduler while the first adapter is proved. It has no public domain and runs one bounded command, then exits. Repository and initial Railway defaults stay inert:

```text
APP_ENV=staging
DATASET_MODE=live
INGESTION_ENABLED=false
INGESTION_SOURCE_ID=travis_tcad_parcels
INGESTION_RUN_PROFILE=proof
INGESTION_PAGE_SIZE=2
INGESTION_MAX_RECORDS=2
INGESTION_CITIES=DEL VALLE,MANOR
LIVE_SOURCE_DISPLAY_ENABLED=false
OUTREACH_MODE=disabled
OUTREACH_SEND_ENABLED=false
```

The runtime accepts only two reviewed enabled profiles. Use `proof` with the
exact `2`/`2` bounds for the two-record private acquisition and replay. After
both proof runs pass, use `cohort` with `INGESTION_PAGE_SIZE=250` and
`INGESTION_MAX_RECORDS=1000` for the complete `DEL VALLE,MANOR` cohort and its
replay. The monthly service must retain the `cohort` profile and those exact
bounds; it must never schedule the partial proof profile.

Create a private Railway bucket displayed as `raw-artifacts` in the same staging environment and initial region (`sjc`). Map references exactly:

```text
OBJECT_STORAGE_BUCKET=${{raw-artifacts.BUCKET}}
OBJECT_STORAGE_ACCESS_KEY_ID=${{raw-artifacts.ACCESS_KEY_ID}}
OBJECT_STORAGE_SECRET_ACCESS_KEY=${{raw-artifacts.SECRET_ACCESS_KEY}}
OBJECT_STORAGE_REGION=${{raw-artifacts.REGION}}
OBJECT_STORAGE_ENDPOINT=${{raw-artifacts.ENDPOINT}}
OBJECT_STORAGE_FORCE_PATH_STYLE=false
DATABASE_URL=<sealed seekandscore_ingestion URL; never PostGIS.DATABASE_URL>
```

Only acquisition services receive bucket credentials. Railway buckets currently lack object lock, versioning, lifecycle rules, server-side encryption controls, and native backups, so application writes must be content-addressed/create-only and copied to independent storage. See [the live-ingestion runbook](../../docs/LIVE_INGESTION_RUNBOOK.md) before enabling the cron.

## Database credential boundary

Only the private, one-shot `db-migrate` service receives
`MIGRATION_DATABASE_URL=${{PostGIS.DATABASE_URL}}`. It also receives two distinct
32+ character URL-safe generated passwords plus sealed restricted URLs so its
pre-deploy can migrate, reconcile both LOGIN roles, and audit the credentials:

```text
MIGRATION_DATABASE_URL=${{PostGIS.DATABASE_URL}}
API_DATABASE_LOGIN_ROLE=seekandscore_api
API_DATABASE_PASSWORD=<sealed URL-safe generated value>
API_RUNTIME_DATABASE_URL=<sealed restricted API URL>
INGESTION_DATABASE_LOGIN_ROLE=seekandscore_ingestion
INGESTION_DATABASE_PASSWORD=<different sealed URL-safe generated value>
INGESTION_RUNTIME_DATABASE_URL=<sealed restricted ingestion URL>
```

The API receives only its restricted URL as `DATABASE_URL`; manual ingestion,
monthly ingestion, and discovery receive only the ingestion URL. Never attach
`MIGRATION_DATABASE_URL`, the PostGIS owner URL, or the other service's runtime
URL to an application service. The Python entrypoint refuses owner credentials,
and the runtime audit checks the exact `DATABASE_URL` the process will use.

Migration `20260813_0006` also makes research history database-derived: every
accepted case insert/update emits exactly one revision and audit event through a
locked-down trigger. Neither runtime role can insert, update, delete, truncate,
or fabricate those ledgers. Their event time comes from PostgreSQL, not the
caller. Existing append-only triggers continue to protect owner-side mistakes.

Workers and scheduler never migrate. The engagement worker has no public domain,
no discovery/alert credentials, and remains blocked. Every environment keeps
`OUTREACH_MODE=disabled` and `OUTREACH_SEND_ENABLED=false`; provider mode and
provider webhooks require a separate approved production activation record.

## Federal 2018 Opportunity Zone service

Use one private, unscheduled, restart-`NEVER` service for the static import
config. It receives only the dedicated `seekandscore_oz_importer` database URL
and the private artifact-bucket references. Use a different private service for
the manual membership build, verification, and eventual cron config. Neither
service receives the PostGIS owner URL, API/research credentials, outreach
credentials, a domain, or the Travis ingestion login.

`db-migrate` provisions and audits this third restricted login with:

```text
OZ_IMPORTER_DATABASE_LOGIN_ROLE=seekandscore_oz_importer
OZ_IMPORTER_DATABASE_PASSWORD=<third distinct sealed URL-safe value>
OZ_IMPORTER_RUNTIME_DATABASE_URL=<sealed restricted QOZ importer URL>
```

It separately provisions the recurring membership builder, which has no raw
artifact or source-import capability:

```text
OZ_MEMBERSHIP_DATABASE_LOGIN_ROLE=seekandscore_oz_membership
OZ_MEMBERSHIP_DATABASE_PASSWORD=<fourth distinct sealed URL-safe value>
OZ_MEMBERSHIP_RUNTIME_DATABASE_URL=<sealed restricted membership URL>
```

The import stage receives references to a separate private
`seekandscore-qoz-raw-staging` bucket. Railway bucket credentials are
bucket-wide, so do not reuse the Travis raw-artifact bucket for this service.
Keep both data-changing gates false and their IDs unset at rest:

```text
OZ_2018_IMPORT_ENABLED=false
OZ_2018_IMPORT_ACTIVATION_ID=
OZ_2018_MEMBERSHIP_BUILD_ENABLED=false
OZ_2018_MEMBERSHIP_BUILD_ACTIVATION_ID=
```

The first gate loads the complete frozen federal layer; its exact reviewed ID is
`SRC-CDFI-QOZ-2018-IMPORT-20260813-V1`. After a successful unchanged replay, the
independent membership gate may use
`GEO-TCAD-QOZ-2018-MEMBERSHIP-20260814-V1`. Neither gate enables display.
Authenticated reference display is separately controlled by
`OZ_2018_PRIVATE_DISPLAY_ENABLED` and approval ID
`SRC-CDFI-QOZ-2018-PRIVATE-REFERENCE-DISPLAY-20260814-V1` on the private API/web
path. The static 2018 archive import has no cron. After the first manual build
and replay pass, a separate private membership-only service may run at
`47 9 2 * *` UTC, 30 minutes after the approved Travis cohort refresh. Give that
cron only the `seekandscore_oz_membership` URL and membership gate—no
bucket/source/import credentials. It must refuse a running, failed, or partial
latest TCAD attempt, derive its expected parcel count from the new complete
cohort, and exit after an unchanged or newly materialized snapshot.
After attaching the cron, read the service instance back and require both the
exact `cronSchedule` and a non-null `nextCronRunAt`; the manifest alone did not
persist this setting in the prior TCAD rollout. If absent, apply only the narrow
service-instance cron-schedule update. Cron activation must not execute a
membership build or create a build receipt immediately.

Follow [the live QOZ rollout runbook](../../docs/OZ_LIVE_ROLLOUT.md) for the
ordered import, replay, membership build, verification, and rollback gates.
