# ADR 0004: Railway application plane and single-node PostGIS for MVP

- Status: accepted with production gate
- Date: 2026-08-12

## Context

Railway is the requested deployment target and supports stateless services, workers, cron, private networking, Redis, and a PostGIS template. Its native PostgreSQL HA conversion does not cover the community PostGIS image, and volume-backed services cannot use ordinary replicas.

## Decision

Deploy web, API, workers, scheduler, Redis, and the initial PostGIS node on Railway. Keep PostGIS/Redis private. Use a pinned PostGIS image, Railway volume snapshots, off-project encrypted logical backups, monitoring, and verified restores.

Treat the single-node database as an MVP constraint. Before strict availability requirements, migrate PostGIS to a managed HA provider that supports the required extensions while retaining Railway for the application plane.

## Consequences

### Positive

- Fast staging/production setup and simple private service connectivity.
- Independent stateless/worker scale.
- Clean later database-provider swap through connection/config boundaries.

### Negative

- Database remains a single node and operator-managed.
- Volume-backed deploys have availability constraints.
- Backup/restore and upgrade responsibility stays with the team.
- There is no assumed PITR for the community PostGIS image.

## Production gate

Launch requires explicit RPO/RTO and single-node-risk acceptance. Acquisition-critical operation or stricter SLOs trigger the managed-HA evaluation/migration.
