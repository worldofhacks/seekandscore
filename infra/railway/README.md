# Railway configuration

The files in this directory are planning examples until the referenced applications and Dockerfiles exist. They must be validated against Railway's live schema before a service uses them.

Planned service mapping:

| Service | Config path | Start behavior |
|---|---|---|
| `web` | `/infra/railway/web.example.toml` | Next.js server |
| `api` | `/infra/railway/api.example.toml` | FastAPI, sole migration owner |
| `worker-discovery` | `/infra/railway/worker-discovery.example.toml` | Celery acquisition queues |
| `worker-enrichment` | `/infra/railway/worker-enrichment.example.toml` | Celery geo/market/score queues |
| `worker-engagement` | `/infra/railway/worker-engagement.example.toml` | private policy-gated engagement queue; disabled/log-only until activation |
| `scheduler` | `/infra/railway/scheduler.example.toml` | enqueue due jobs and exit |

Do not point Railway at these examples until paths/commands exist. When activated, remove `.example` and record the validation/deployment in the associated issue.

See [the full deployment plan](../../docs/RAILWAY_DEPLOYMENT.md).

The engagement worker has no public domain, no migration ownership, and no discovery/alert credentials. Preview environments set `OUTREACH_MODE=disabled`; staging stays `log_only` until a production activation record exists. Provider webhooks enter through the authenticated API and enqueue only validated, idempotent events.
