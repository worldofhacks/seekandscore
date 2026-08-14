# ADR 0007: Isolate database owner and derive research history in PostgreSQL

- Status: accepted
- Date: 2026-08-13

## Decision

Railway uses one private, one-shot `db-migrate` service as the only holder of
the PostGIS owner URL. API and acquisition processes authenticate with distinct
LOGIN roles that inherit fixed NOLOGIN capability roles:

- `seekandscore_api_runtime`: read the approved live-candidate source tables;
  select/insert research cases; update only case status, version, payload, and
  updated time.
- `seekandscore_ingestion_runtime`: read/write only source-run, raw-artifact,
  parcel-observation, and quarantine tables; update only source-run payload.

Both logins are non-owner, non-superuser, cannot create databases/roles, cannot
bypass RLS, receive no database/schema CREATE or TEMPORARY, and have no
unexpected membership. Every deployed process audits its exact `DATABASE_URL`
before application code starts. Enrichment, engagement, Opportunity Zone
importing, and scheduling remain undeployed until dedicated roles are defined.

Research-case relational identity/version/status must match its JSON envelope.
A validation trigger enforces version increments, immutable source/creation
fields, bounded text, and allowed status transitions. A second, narrowly scoped
`SECURITY DEFINER` trigger with `search_path=pg_catalog` derives exactly one
revision and audit event per accepted insert/update. Runtime roles receive no
ledger INSERT/UPDATE/DELETE/TRUNCATE. Ledger `recorded_at` comes from PostgreSQL
`statement_timestamp()`, not caller input.

## Consequences and limits

- Compromise of API credentials can create or alter valid research cases within
  the API contract, including caller-attributed `updated_by` and case
  `updated_at`, but cannot make a case mutation disappear from history or forge,
  rewrite, delete, or backdate the database-recorded ledger event.
- Compromise of ingestion credentials can alter an existing source-run payload,
  which is required by the run lifecycle, but cannot access research/audit data,
  mutate immutable artifact/observation rows, or perform DDL.
- The migration owner and PostgreSQL superuser remain trusted and can change
  grants/triggers. Their credentials therefore never enter a long-running
  application environment.
- Revoking PUBLIC database CREATE/TEMPORARY and public-schema CREATE is retained
  across Alembic downgrade. Restoring those broad defaults would be a separate,
  explicit security decision, not an automatic rollback side effect.
- Every future migration must explicitly grant any new runtime table/column
  capability and update the role audit contract in the same release.

## Release order

1. Back up PostGIS and pin the exact application SHA.
2. Pause the old API, manual/monthly ingestion, discovery workers, and scheduler.
   Remove every PostGIS owner reference from their Railway variables before any
   application process can restart.
3. Create/seal distinct API and ingestion passwords and private runtime URLs.
4. Deploy `db-migrate` at that SHA with the owner URL and both runtime contracts.
5. Require Alembic head, provisioning, and both live role audits to pass.
6. Deploy API with only the API URL; verify startup audit and readiness.
7. Deploy manual/monthly ingestion with only the ingestion URL; verify startup
   audit before enabling acquisition.
8. Confirm no public database proxy exists. Schedule owner-credential rotation
   as defense-in-depth and update only `db-migrate`; rotation is not a substitute
   for stopping old services and removing every owner reference before cutover.
9. Leave unprovisioned services stopped. A failed role audit stops rollout; it
   never authorizes falling back to the owner URL.
