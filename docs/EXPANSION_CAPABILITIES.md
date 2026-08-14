# Expansion capabilities

Cutoff: **August 13, 2026**. This is the capability and activation sequence for expanding Seek and Score without weakening provenance, source rights, or live-only behavior.

## What this release adds

### Full live-cohort explorer

The operator can search and filter the complete approved Travis cohort instead of seeing only the first page. The API applies search, city, and acreage predicates in PostgreSQL, returns both filtered and full-cohort totals, and issues opaque cursors bound to the exact source run, filter set, and read-model version. A changed snapshot or changed filter invalidates the cursor instead of silently mixing results.

### Durable saved research

An authenticated operator can save a live candidate once, record a status, note, and next action, and update it with `If-Match` concurrency. Cases are organization-scoped. Every version creates a revision and audit event in the same transaction; database triggers reject revision/audit updates or deletes.

The dossier exposes five independent gates:

1. parcel identity;
2. source freshness;
3. Opportunity Zone location;
4. underwriting sufficiency;
5. contact preparation.

Only source freshness can currently be satisfied. Opportunity Zone, underwriting, and contact preparation remain blocked until their evidence requirements are implemented. There is no send, compose, export, or bulk-download action.

### Nationwide 2018 Opportunity Zone geography foundation

The federal importer uses the official [CDFI Opportunity Zone archive](https://www.cdfifund.gov/opportunity-zones), [IRS Notice 2018-48](https://www.irs.gov/pub/irs-drop/n-18-48.pdf), [IRS Notice 2019-42](https://www.irs.gov/pub/irs-drop/n-19-42.pdf), and [IRS Notice 2026-40](https://www.irs.gov/pub/irs-drop/n-26-40.pdf). It:

- pins the exact 46,685,678-byte archive and SHA-256;
- rejects unsafe ZIP members and schema drift;
- requires exactly 8,764 unique 11-digit 2010-vintage tract GEOIDs;
- stores immutable raw-source lineage;
- transactionally loads valid `MULTIPOLYGON(3857)` geometry with a GiST index;
- records the one reviewed topology repair and fails if the repair count changes;
- verifies an identical replay as unchanged;
- records Treasury certification separately from the currently effective interval.

The importer is default-off, has no schedule, and does not yet change parcel Opportunity Zone status. The 2027 Treasury workbook remains `eligible` only; it is not a designation feed.

## Highest-value next slices

### 1. Parcel geometry and versioned OZ membership

Normalize the already-retained TCAD parcel polygon into a canonical geometry version. Intersect it with the frozen 2018 tract layer and retain relationship (`within`, `overlaps`, `touches`, `unresolved`), overlap ratio, point-on-surface result, source artifacts, algorithm version, and quality flags. Boundary cases stay in review. Only then may the dossier's Opportunity Zone gate move from `blocked` to a factual screening result.

### 2. Bastrop and Caldwell live assessor adapters

Treat each jurisdiction as a separately approved adapter/profile. Require supported machine access, rights metadata, fixed non-owner fields, immutable proof/replay, canonical parcel IDs, freshness rules, and shadow review. Do not copy Travis-specific city, schema, or scoring assumptions into core modules.

### 3. Independent value and risk evidence

Add approved sales/listing or operator-entered evidence, FEMA flood, access, zoning, utilities, and tax-distress sources. Keep assessor value observations separate from market-value estimates. Version every method and surface unknowns before any underwriting gate can pass.

### 4. Responsible-party and contact preparation

Add property-party roles and contact points only from an approved source with purpose and permitted-use metadata. Require role/authority evidence, match confidence, suppression, policy preflight, human approval, and audit. Contact preparation and outbound sending remain separate activations; neither affects opportunity score automatically.

### 5. Second-market proof

Choose one non-Texas county with a different disclosure and tax-sale regime. A successful pilot must use the same explorer, dossier, provenance, and geography contracts with market behavior supplied by manifests/adapters—not state-name branches in the core.

## Deployment gates

- Web remains the sole public origin and requires private access authentication.
- API remains domainless and reachable only on Railway's private network.
- Saved research requires explicit `RESEARCH_ORGANIZATION_ID`, `RESEARCH_ACTOR_ID`, a 32+ character server-only token, approved live display, and disabled outreach.
- Research mutations require same-origin JSON and strong quoted `If-Match` versions.
- Federal geography import requires its dedicated exact activation ID, private PostGIS, and durable private object storage.
- Geography display and parcel membership are separate approvals from raw import.
- No new source enters ranking or contact workflows until proof, replay, freshness, rights, and source-failure behavior pass.

## Scale seams

The current modular monolith deliberately scales by contract before it scales by service count:

- jurisdiction/source adapters remain isolated from the candidate and dossier contracts;
- cursor and dossier APIs are snapshot/version aware;
- federal geography is an independently runnable importer;
- raw artifacts are content-addressed and replayable;
- PostGIS spatial indexes support regional joins;
- organization keys and audit state are present before collaboration is added;
- export, contact, and outbound capabilities remain independently gated.

Extract a module only after measured workload, reliability, security, or ownership needs justify a separate service.
