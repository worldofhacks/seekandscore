# Delivery roadmap

The roadmap is outcome-based. Calendar dates begin only after critical source access and the initial team capacity are known.

## Release map

| Release | Outcome | Included milestones |
|---|---|---|
| `0.1` Foundation | replayable synthetic vertical slice in Railway staging | M0–M1 |
| `0.2` Travis intelligence | approved Travis facts resolved and enriched | M2 |
| `0.3` Ranking alpha | reviewed deterministic Top 25 on internal data | M3 |
| `1.0` Central Texas operator MVP | Travis/Bastrop/Caldwell Top 25, map, evidence, watchlist, alerts | M4 |
| `1.1` Acquisition operations | distress, owner portfolios, auctions, deal workflow | M5 |
| `1.2` Specialist underwriting | parking, zoning/utilities, offers, OZ scenarios | M6 |
| `2.0` Multi-market proof | one non-Texas market runs on shared core | M7 |
| `3.x` National operating platform | certified adapters and scalable market activation | M8 |

## Milestone 0 — feasibility

### Source and rights discovery

- Inventory Travis, Bastrop, and Caldwell assessor/parcel access.
- Inventory tax office, tax-sale, court, recorder/trustee notice, zoning, GIS, and auction sources.
- Obtain representative files/responses and identifiers.
- Document terms, automated-access method, rate limits, retention, display/export/redistribution, and privacy classification.
- Select listing/sales path or approve manual-import fallback.

### Product decisions

- Review 100–300 parcel gold set.
- Finalize score-v1 definitions, risks, applicability, and minimum evidence.
- Select map/geocoder, auth, storage, alert, telemetry, and license approach.
- Approve Railway cost ceiling and recovery objectives.

## Milestone 1 — platform foundation

### Repository and runtime

- Scaffold web, API, worker, shared contracts/UI, backend modules, migrations, and region packs.
- Add pinned dependencies, lint/type/test/build/migration/security CI.
- Add local PostGIS, Redis, and object-store development services.

### Data kernel

- Geography/jurisdiction/source/rights registries.
- Source-run/job state machine and transactional outbox.
- Immutable artifacts, checksums, observations/evidence, bitemporal intervals, and replay.
- Synthetic adapter and end-to-end fixture pipeline.

### Railway staging

- Private pinned PostGIS and Redis.
- Web/API/worker/scheduler services, health checks, config paths, reference variables.
- Structured telemetry, backup, verified restore, and ingestion kill switch.

## Milestone 2 — Travis vertical slice

- Travis parcel/assessor adapter.
- Parcel geometry and canonical identity with review queue.
- FEMA flood and core geography enrichment.
- Legacy/2027 OZ cohort and parcel-membership ingestion.
- Tax foreclosure and manual court/listing inputs.
- Provenance/conflicts/freshness and source operations view.
- Initial comparable/value range service.

## Milestone 3 — ranking alpha

- Versioned feature and score registries.
- Strategy underwriting, risk deductions, and confidence.
- Material change events and score/rank history.
- Stable overall/strategy rankings and composition preferences.
- Ranking explanations and next-action rules.
- Gold-set regression/backtest review.

## Milestone 4 — Central Texas MVP

- Bastrop/Caldwell source configurations and adapters.
- Top 25, filters, map, candidate detail, evidence, conflicts, and timeline.
- Daily brief, new-opportunity feed, watch/pass, notes/tasks, and alerts.
- Production Railway shadow mode, data-quality signoff, security/recovery launch gate.

## Milestone 5 — acquisition operations

- Automated/manual-assisted court and trustee notice pipelines.
- Owner/entity resolution and related-parcel portfolios.
- Auction inventory, due diligence, clearing-cost and max-bid scenarios.
- Deal stages, contacts, attempts, offers, follow-ups, and outcomes.
- Improved automated comparable workflows.

## Milestone 6 — specialist underwriting

- Parking/site capacity and revenue scenarios.
- Zoning, permit, access, utility, and septic evidence.
- Off-market offer ranges.
- Opportunity Zone development/tax scenarios with cohort policy.
- Evidence-cited optional AI analyst summaries.

## Milestone 7 — second-market proof

- Select one dissimilar non-Texas Opportunity Zone market.
- Create its region pack, source policies, adapters, and gold set.
- Run shadow rankings and document required core changes.
- Pass modularity and data-quality activation gates.

## Milestone 8 — national platform

- Adapter SDK/conformance suite and certification workflow.
- Market/source control plane and activation lifecycle.
- Vendor data strategy and cost/coverage measurement.
- Partitioning/archive, managed HA data services, and analytics/search scaling as measured.
- Collaboration/multi-tenant controls only if product direction requires them.

## Issue labels

Use a small consistent taxonomy:

### Type

- `type: discovery`
- `type: feature`
- `type: infrastructure`
- `type: data-source`
- `type: data-quality`
- `type: documentation`
- `type: security`

### Area

- `area: platform`
- `area: ingestion`
- `area: identity`
- `area: geo`
- `area: market`
- `area: scoring`
- `area: web`
- `area: deals`
- `area: operations`

### Priority/state

- `priority: critical`
- `priority: high`
- `priority: normal`
- `blocked: decision`
- `blocked: source-access`

Each issue should have one milestone, an owner, dependencies, data/security notes, and objective acceptance criteria.

## Roadmap change rule

New features enter the active milestone only if they are required for its outcome or remove a demonstrated blocker. Everything else stays in a later milestone. Source terms, severe data-quality issues, security, and recovery can stop a release regardless of feature completion.
