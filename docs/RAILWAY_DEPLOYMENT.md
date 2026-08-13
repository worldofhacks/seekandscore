# Railway deployment plan

Research cutoff: **August 12, 2026**. Validate configuration fields against Railway's live schema and documentation during implementation because platform capabilities can change.

## 1. Deployment decision

Use Railway for the stateless application plane and MVP infrastructure:

- Next.js web service
- FastAPI service
- independently scalable worker services
- short-lived cron scheduler
- Redis queue/cache
- initial single-node PostGIS

Use S3-compatible object storage for immutable source artifacts. The provider is an open Phase 0 decision; production disaster recovery should not rely solely on a database volume in the same Railway project.

Railway is a good fit for service deployment and private networking, but its database templates remain operator-managed. Backups, tuning, security, monitoring, upgrades, and recovery are our responsibility. See Railway's [database](https://docs.railway.com/databases) and [PostgreSQL](https://docs.railway.com/databases/postgresql) documentation.

## 2. Critical PostGIS constraint

Railway offers a [PostGIS template](https://railway.com/deploy/postgis), but Railway's native [PostgreSQL high-availability conversion](https://docs.railway.com/databases/postgresql-ha) supports its official PostgreSQL images and excludes custom images such as PostGIS/TimescaleDB. Railway's [volume reference](https://docs.railway.com/volumes/reference) also prevents ordinary replicated services from sharing an attached volume.

This creates an explicit decision gate:

### MVP

Use one Railway PostGIS node with:

- a pinned, tested image tag or digest (never the template's floating tag in production);
- private networking only;
- scheduled Railway volume backups;
- encrypted logical backups stored outside the Railway project/provider;
- database and storage monitoring;
- monthly automated restore verification;
- a documented recovery runbook and accepted RPO/RTO.

### Availability-critical production

Before strict uptime requirements or intolerable single-node risk, move PostGIS to a managed HA provider with full PostGIS support. Keep web/API/workers on Railway and update a reference/secret connection variable.

Do not self-manage Patroni/etcd/PostGIS on Railway for the first release; the operational burden is disproportionate to a single-operator MVP.

## 3. Service topology

```mermaid
flowchart TB
  Internet --> Web["web<br/>Next.js"]
  Internet --> API["api<br/>FastAPI"]
  Web --> API

  API --> Redis["Redis<br/>queue/cache"]
  API --> PostGIS["PostGIS<br/>source of truth"]

  Scheduler["scheduler<br/>Railway cron"] --> Redis
  Discovery["worker-discovery"] --> Redis
  Discovery --> PostGIS
  Discovery --> Objects["S3-compatible<br/>raw artifacts"]
  Enrichment["worker-enrichment"] --> Redis
  Enrichment --> PostGIS
  Enrichment --> Objects

  API -. private network .-> PostGIS
  Discovery -. private network .-> PostGIS
  Enrichment -. private network .-> PostGIS
```

| Service | Railway primitive | Public domain | Persistent volume | MVP replicas | Scale trigger |
|---|---|---:|---:|---:|---|
| `web` | persistent service | yes | no | 1 | 2+ at production launch or measured saturation |
| `api` | persistent service | yes | no | 1 | 2+ for availability/load; remain stateless |
| `worker-discovery` | persistent worker | no | no | 1 | source backlog/latency or rate-isolation needs |
| `worker-enrichment` | persistent worker | no | no | 1 | CPU/GIS/document backlog |
| `scheduler` | cron service | no | no | scheduled singleton | never performs long work |
| `postgis` | database/image service | no | yes | 1 | migrate externally for HA, not replicas |
| `redis` | database/image service | no | yes | 1 | external managed/Sentinel when queue HA matters |
| `pgbouncer` | optional persistent service | no | no | 0 initially | connection count approaches safe DB limit |

Split additional workers by resource/risk class only when needed: OCR/document parsing, geocoding, valuation, ranking, and alert delivery can each get distinct queues and concurrency.

## 4. Monorepo deployment model

Railway maps each deployable process to a service. Its [monorepo documentation](https://docs.railway.com/deployments/monorepo) supports root directories, per-service commands/config, and watch paths.

Use the repository root as build context for services that consume shared Python packages, contracts, migrations, or lockfiles. Give each service:

- a dedicated Dockerfile or simple Railpack build;
- an absolute Railway config-file path such as `/infra/railway/api.toml`;
- root-relative watch patterns including every shared dependency;
- its own start command;
- a clear migration owner.

Railway config files do not automatically follow a configured service root directory. A config path must be set explicitly. Watch paths must include shared contracts, migrations, and lockfiles or a dependency change may fail to redeploy the consumer.

### Build choice

- Use a multi-stage Dockerfile for Python API/workers because GIS, GDAL/GEOS/PROJ, OCR, or browser dependencies require deterministic OS packages.
- Railpack is acceptable for the Next.js web service if no special native dependency is needed.
- Do not start a new Nixpacks setup; Railway identifies Railpack as its successor.
- Pin language/toolchain versions and use deterministic lockfiles.
- Run application processes as a non-root user.

## 5. Config as code

Stable `railway.toml`/`railway.json` configuration is per service, not an entire-project blueprint. Railway's TypeScript project-level infrastructure-as-code is beta and mutually exclusive with service config for a controlled service; evaluate it in staging later, not as the MVP control plane.

Representative API configuration (final paths/commands land with the scaffold):

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "infra/docker/api.Dockerfile"
watchPatterns = [
  "services/api/**",
  "python/seekandscore/**",
  "packages/contracts/**",
  "migrations/**",
  "pyproject.toml",
  "uv.lock",
  "infra/docker/api.Dockerfile"
]

[deploy]
preDeployCommand = "python -m seekandscore.db.migrate"
startCommand = "python -m seekandscore.api"
healthcheckPath = "/readyz"
healthcheckTimeout = 300
restartPolicyType = "ALWAYS"
restartPolicyMaxRetries = 10
overlapSeconds = 15
drainingSeconds = 30
```

This is a design example, not runnable until the referenced application exists. Validate it with Railway's [Config as Code reference](https://docs.railway.com/config-as-code/reference) and live schema.

Worker configurations omit the API migration command and use queue-specific start commands. The scheduler adds a UTC cron expression and must exit after enqueueing work.

## 6. Environments

| Environment | Data | Sources | Secrets | Deployment behavior |
|---|---|---|---|---|
| `development` | local/synthetic | fixtures/manual | local `.env` | Docker Compose or native tools |
| `staging` | isolated synthetic/sampled open data | sandbox/low-rate | distinct low-privilege | auto-deploy from integration branch |
| `production` | real records | approved production access | sealed production | protected main release |
| PR environment | synthetic fixtures only | production ingestion disabled | no production secrets | focused previews; auto-remove on PR close |

Railway [environments](https://docs.railway.com/environments) isolate private networks. Sealed variables are not automatically copied to duplicated/PR environments; explicitly provision safe preview credentials.

Preview deployments must set:

```text
INGESTION_ENABLED=false
ALERT_DELIVERY_MODE=log
DATASET_MODE=synthetic
AI_ANALYST_ENABLED=false
```

This prevents a UI pull request from scraping sources, contacting owners, or sending real alerts.

## 7. Networking

Only `web` and `api` receive public domains. PostGIS, Redis, workers, scheduler, and PgBouncer remain private.

Railway [private networking](https://docs.railway.com/networking/private-networking) supplies per-environment internal DNS over encrypted WireGuard. Services use names such as `postgis.railway.internal` and `redis.railway.internal`, ideally through reference variables rather than hardcoded hostnames.

Requirements:

- Bind application servers to Railway's injected `PORT` and an IPv6-compatible address (`::`) when using its dual-stack private network.
- Keep client-side browser code on the public API URL; browsers cannot reach `*.railway.internal`.
- Use application connection retries/backoff. GitHub-triggered monorepo service deploys are independent and there is no Docker Compose `depends_on` guarantee.
- Do not expose the database TCP proxy in production unless an approved operational need exists.
- If a source requires IP allowlisting, evaluate Railway Pro static outbound IPv4 and document that capability in the adapter descriptor.

## 8. Variables and secrets

Use Railway reference variables for internal services, for example:

```text
DATABASE_URL=${{PostGIS.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
```

Use shared non-secret variables for version/config identifiers and sealed service variables for secrets.

### Common application variables

```text
APP_ENV
LOG_LEVEL
PUBLIC_APP_URL
API_BASE_URL
ALLOWED_ORIGINS
DATABASE_URL
REDIS_URL
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_REGION
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY_ID
OBJECT_STORAGE_SECRET_ACCESS_KEY
AUTH_SECRET / OIDC settings
OTEL_EXPORTER_OTLP_ENDPOINT
SENTRY_DSN
```

### Source variables

Namespace credentials per adapter, such as `SOURCE_TCAD_*`. Never place source tokens in a shared browser-visible `NEXT_PUBLIC_*` variable. Rotate provider credentials independently and record owner/expiry in an external secret inventory.

## 9. Database provisioning

1. Deploy the Railway PostGIS template into `staging`.
2. Replace any floating image reference with a tested stable tag/digest.
3. Attach the required persistent volume at the documented Postgres data path.
4. Keep it private.
5. Create a least-privilege application role and a separate migration role.
6. Run an idempotent baseline migration that verifies required extensions (`postgis` and only explicitly approved additions).
7. Set bounded application pools per API/worker replica.
8. Add GiST/SP-GiST and conventional indexes from measured query plans.
9. Configure Railway snapshots and the external logical-backup job.
10. Complete a restore test before loading non-reproducible production data.

Do not assume point-in-time recovery works for the community PostGIS image; Railway's documented PITR depends on its own pgBackRest-enabled PostgreSQL image. Verify the actual deployed service before declaring PITR in the recovery objective.

## 10. Redis behavior

Redis supports Celery queues, short-lived locks, rate limits, and disposable caches. It is not the authoritative record of job status, source cursors, deduplication, events, or rankings.

- Store pending job intent and outcomes in Postgres.
- Publish jobs through a transactional outbox.
- Confirm persistence mode and volume behavior for the deployed Redis service.
- Define memory limits and an eviction policy that cannot silently delete live queues.
- Monitor queue depth, oldest job, memory, restarts, and failed deliveries.
- Rebuild queues/caches from Postgres after Redis loss.
- Move to managed HA Redis or an appropriate queue when availability/throughput requires it.

## 11. Scheduler and workers

Railway [cron jobs](https://docs.railway.com/cron-jobs):

- use UTC;
- have a five-minute minimum frequency;
- may run a few minutes late;
- skip the next run when the prior execution remains active;
- require the process to close connections and exit.

Therefore the scheduler performs one short transaction:

1. Acquire a Postgres advisory lock/idempotency key.
2. Determine due source jobs from the registry.
3. Insert durable job intents/outbox rows.
4. Publish/enqueue.
5. Release resources and exit successfully.

Long acquisition, parsing, spatial, scoring, or delivery work runs in always-on workers with Celery retry/dead-letter policies. Use separate queues and concurrency limits per source to honor rate limits.

## 12. Migrations and deploy ordering

One designated deployment unit owns schema migration. Do **not** configure the same migration command on API and every worker.

Railway's [pre-deploy command](https://docs.railway.com/deployments/pre-deploy-command) runs after build and before application start, can access environment variables/private networking, uses a separate container without the service volume, is not retried, and blocks deployment on failure.

Migration requirements:

- Postgres advisory lock prevents concurrent execution.
- Expand/contract changes remain compatible with the prior application and workers.
- Backfills are resumable background jobs, not long blocking schema migrations.
- Destructive column/table removal occurs in a later release after old code is drained.
- Migration, API, and worker images share one tested commit/schema contract.
- Production deployment has a database backup and rollback decision point.

## 13. Health, shutdown, and continuous monitoring

Expose:

- `/livez`: process is alive; no remote dependency required.
- `/readyz`: initialization succeeded and critical dependencies respond within tight timeouts.
- `/version`: commit SHA, build time, schema compatibility, and config versions without secrets.

Railway [health checks](https://docs.railway.com/deployments/healthchecks) gate a new deployment; they are not continuous monitoring. They require HTTP 200 and use the injected `PORT`. Allow the `healthcheck.railway.app` host where framework host validation applies.

Set a nonzero drain period. On SIGTERM:

- web/API stop accepting new requests and finish bounded in-flight work;
- workers stop reserving new jobs, safely return/retry unfinished jobs, and flush telemetry;
- scheduler exits without leaving locks/connections.

Use an external uptime monitor plus OpenTelemetry/error tracking for continuous application health.

## 14. Scaling and region choice

Railway horizontal scaling is manually configured; public traffic is distributed without sticky sessions. Keep session and job state outside API/web memory.

Start all latency-sensitive services in one region. Railway does not currently list a Texas/US Central region. Benchmark Virginia and California against:

- Central Texas operator latency;
- county/source endpoints;
- object-storage region;
- external PostGIS if selected.

Virginia is the initial hypothesis, not an unmeasured commitment.

Scaling order:

1. Fix slow queries, indexes, payloads, and worker concurrency.
2. Add PgBouncer/adjust bounded pools before API replicas exhaust connections.
3. Add API/web replicas for availability and measured load.
4. Split/scale workers by queue and bottleneck.
5. Add read projections/caches.
6. Move to managed HA data services before multi-region app replicas create cross-region database risk.

Nationwide coverage alone is not a reason for multi-region compute. A single-region source-of-truth database can make distant API replicas slower.

## 15. Backups and disaster recovery

Railway [volume backups](https://docs.railway.com/volumes/backups) can be scheduled but restore within the same project/environment and do not replace provider/regional disaster recovery.

### Proposed MVP policy

- Daily, weekly, and monthly Railway volume backups according to available retention.
- Daily encrypted logical PostGIS backup to an off-project storage location.
- SHA/checksum and restore logs for every backup.
- Automated monthly restore into an isolated database and validation of row counts, extensions, spatial indexes, migrations, and sample queries.
- Quarterly recovery exercise using the written runbook.
- Alert when the last good backup or restore verification exceeds its SLA.

### Proposed objectives requiring owner acceptance

| Stage | RPO | RTO | Notes |
|---|---:|---:|---|
| Development | best effort | best effort | reproducible fixtures only |
| MVP production | 24 hours | 4 hours | daily logical backup; source data may be replayable |
| Acquisition-critical | 1 hour | 2 hours | requires verified WAL/PITR or managed HA provider |

Deal notes, manual resolution decisions, contacts, offers, and outcomes are less reproducible than source data; prioritize them in recovery verification.

## 16. Observability on Railway

Railway provides container logs and infrastructure metrics, but application/source/business telemetry remains our responsibility. Emit single-line structured JSON and OpenTelemetry data.

Minimum production alerts:

- public API unavailable or error/latency threshold exceeded;
- source freshness SLA missed;
- repeated source authentication/rate-limit/schema failure;
- queue oldest-job age/depth exceeds threshold;
- dead-letter count increases;
- database connection/storage/slow-query threshold exceeded;
- PostGIS/Redis restart;
- backup age or restore verification stale;
- ranking/read-model snapshot too old;
- alert delivery failure rate elevated.

Railway log throughput/retention is not an audit archive. Store durable audit events and important source/job outcomes in Postgres/object storage, then export telemetry to an approved external system.

## 17. Deployment sequence

### Gate 0 — before creating Railway resources

- Runnable web/API/worker scaffold exists.
- Synthetic fixture pipeline and migrations pass locally.
- `/livez` and `/readyz` exist.
- Source ingestion can be globally disabled.
- Secret inventory and owner are defined.
- Initial monthly spend ceiling and alerts are approved.

### Gate 1 — staging

1. Create Railway project and staging environment.
2. Provision pinned PostGIS and Redis privately.
3. Configure object storage and low-privilege staging credentials.
4. Create `web`, `api`, workers, and scheduler from the GitHub repository.
5. Assign per-service config paths, watch patterns, commands, and variables.
6. Run migration owner; load synthetic fixtures.
7. Generate public staging domains only for web/API.
8. Verify network isolation, health, graceful shutdown, replay, and dead-letter flow.
9. Configure backups; perform and document a restore.
10. Run load and failure tests; record baseline cost/resource use.

### Gate 2 — production shadow mode

1. Create isolated production environment and production credentials.
2. Re-run backup/restore and security checklist.
3. Enable approved sources one at a time with alerts/log delivery disabled.
4. Compare results to manually verified records.
5. Keep rankings internal and mark them shadow until data-quality thresholds pass.

### Gate 3 — operator launch

1. Approve source freshness and parcel-resolution benchmarks.
2. Enable Top 25, watchlist, and internal alerts.
3. Review one full auction/source-refresh cycle.
4. Hold a recovery exercise and incident simulation.
5. Sign off on accepted single-node PostGIS risk or migrate to managed HA.

## 18. Release checklist

- [ ] CI passed for the exact commit
- [ ] schema migration is backward compatible and backup exists
- [ ] Railway config paths/watch patterns include shared dependencies
- [ ] production ingestion/alert flags are intentional
- [ ] no production secret entered in Git or public build variables
- [ ] source terms/access version remains approved
- [ ] new deployment passes readiness and prior deploy drains safely
- [ ] worker queue/retries are healthy
- [ ] data freshness and Top-25 snapshot advance
- [ ] smoke tests pass on web, API, map, source evidence, watchlist, and ranking explanation
- [ ] rollback and data-forward-fix owner identified

## 19. Cost controls

- Tag/measure CPU, memory, network, storage, and task duration by service/source.
- Bound worker concurrency and source polling to actual freshness requirements.
- Use cron only for short dispatch work; scale idle worker pools deliberately.
- Add object lifecycle policies without deleting the only permitted raw record.
- Prevent production dependencies in PR environments.
- Set workspace/project spend alerts and review cost per source, parcel, and daily active operator.
- Revisit architectural extraction only when its operational savings exceed its added complexity.
