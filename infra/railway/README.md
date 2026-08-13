# Railway configuration

The files in this directory are per-service configurations aligned with the runnable monorepo scaffold and root build context. Every application runtime is live-only and database-backed; there are no synthetic preview configurations. These files do not provision a Railway project or external resource by themselves.

Planned service mapping:

| Service | Config path | Start behavior |
|---|---|---|
| `web` | `/infra/railway/web.example.toml` | database-backed Next.js server template |
| `api` | `/infra/railway/api.example.toml` | database-backed FastAPI template; sole migration owner |
| `worker-discovery` | `/infra/railway/worker-discovery.example.toml` | Celery acquisition queues |
| `worker-enrichment` | `/infra/railway/worker-enrichment.example.toml` | Celery geo/market/score queues |
| `worker-engagement` | `/infra/railway/worker-engagement.example.toml` | private policy-gated engagement queue; disabled until activation |
| `scheduler` | `/infra/railway/scheduler.example.toml` | enqueue due jobs and exit |
| `ingestion-travis` | `/infra/railway/ingestion-travis.example.toml` | manual bounded TCAD proof; fail-closed until source activation |
| `ingestion-travis` (scheduled) | `/infra/railway/ingestion-travis.cron.example.toml` | same process with monthly UTC cron, attached only after proof |

Every Python image enters through `scripts/runtime/python-entrypoint.sh`. Unless an environment explicitly provides values, it forces these inert defaults:

```text
DATASET_MODE=live
INGESTION_ENABLED=false
ALERT_DELIVERY_MODE=log
OUTREACH_MODE=disabled
OUTREACH_SEND_ENABLED=false
```

Set the same values explicitly in every Railway environment so deployment state is visible in the dashboard. Missing variables remain safe; changing a variable alone does not bypass application policy gates. When activating a template, record live-schema validation in the associated issue and retain the repository root as the build context.

See [the full deployment plan](../../docs/RAILWAY_DEPLOYMENT.md).

## First live-ingestion service

`ingestion-travis` is separate from the general scheduler while the first adapter is proved. It has no public domain and runs one bounded command, then exits. Repository and initial Railway defaults stay inert:

```text
APP_ENV=staging
DATASET_MODE=live
INGESTION_ENABLED=false
INGESTION_SOURCE_ID=travis_tcad_parcels
INGESTION_PAGE_SIZE=250
INGESTION_MAX_RECORDS=250
LIVE_SOURCE_DISPLAY_ENABLED=false
OUTREACH_MODE=disabled
OUTREACH_SEND_ENABLED=false
```

Create a private Railway bucket displayed as `raw-artifacts` in the same staging environment and initial region (`sjc`). Map references exactly:

```text
OBJECT_STORAGE_BUCKET=${{raw-artifacts.BUCKET}}
OBJECT_STORAGE_ACCESS_KEY_ID=${{raw-artifacts.ACCESS_KEY_ID}}
OBJECT_STORAGE_SECRET_ACCESS_KEY=${{raw-artifacts.SECRET_ACCESS_KEY}}
OBJECT_STORAGE_REGION=${{raw-artifacts.REGION}}
OBJECT_STORAGE_ENDPOINT=${{raw-artifacts.ENDPOINT}}
OBJECT_STORAGE_FORCE_PATH_STYLE=false
DATABASE_URL=${{PostGIS.DATABASE_URL}}
```

Only acquisition services receive bucket credentials. Railway buckets currently lack object lock, versioning, lifecycle rules, server-side encryption controls, and native backups, so application writes must be content-addressed/create-only and copied to independent storage. See [the live-ingestion runbook](../../docs/LIVE_INGESTION_RUNBOOK.md) before enabling the cron.

The API is the sole migration owner. Workers and scheduler use the same tested Python image contract but never migrate. The engagement worker has no public domain, no migration ownership, and no discovery/alert credentials. Every environment keeps `OUTREACH_MODE=disabled` and `OUTREACH_SEND_ENABLED=false`; provider mode and provider webhooks require a separate approved production activation record.
