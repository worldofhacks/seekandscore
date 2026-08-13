# ADR 0001: Modular monolith with separate deployable processes

- Status: accepted
- Date: 2026-08-12

## Context

Seek and Score spans source acquisition, identity, GIS, market valuation, scoring, ranking, deal workflow, and delivery. These have distinct responsibilities and workload profiles, but the launch team and transaction volume do not justify independently deployed domain microservices.

The API, long-running data work, scheduler, and web frontend do require different runtime and scaling behavior.

## Decision

Implement the backend as a modular monolith with explicit bounded contexts and one PostGIS source of truth. Deploy separate entrypoints for:

- web;
- API;
- discovery workers;
- enrichment/scoring workers;
- short-lived scheduler.

Modules own their tables, commands, and events. Cross-module writes use application services. A transactional outbox connects asynchronous workflows. Read models may denormalize across modules.

## Consequences

### Positive

- Simple transactions and consistent provenance/identity changes.
- Fewer operational systems during source and model discovery.
- Independent worker/API scaling without network service boundaries everywhere.
- Modules can be extracted later behind existing command/event contracts.

### Negative

- Requires enforcement to prevent arbitrary cross-module imports/SQL.
- One database is a shared failure/scaling boundary.
- Polyglot web/backend contracts need generated/validated schemas.

## Extraction rule

Extract a module only after measured need for independent scaling, availability, security/data access, persistence, release cadence, or team ownership. Extraction retains event/version/idempotency contracts and includes a data migration plan.
