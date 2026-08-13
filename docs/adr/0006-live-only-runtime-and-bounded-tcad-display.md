# ADR 0006: Live-only runtime and bounded TCAD reference display

- Status: accepted
- Date: 2026-08-13

## Context

The initial operator console used deterministic property fixtures to prove the API and user-interface contract. Those records were visually labeled, but any runtime fallback can still be mistaken for an actionable property lead when a live source is unavailable.

The first implemented source is Travis County TNR's TCAD-derived ArcGIS parcel layer. Its service ItemInfo attributes the data to Travis Central Appraisal District, describes monthly County assembly, and limits the layer to informational/reference use with approximate boundaries and no accuracy or completeness warranty. The ItemInfo does not state a service-query or reference-display prohibition. A separate TCAD page prohibits mining its downloadable PDF map folders; this integration does not access that page or those files. This is a product-scope decision, not a broad license determination.

## Decision

Application runtime is live-only in every environment:

- production code contains no fixture-backed candidate repository;
- the API accepts only `DATASET_MODE=live` and requires its live database in staging and production;
- the web process rejects non-live mode and requires the API in staging and production;
- an unavailable, unapproved, stale-withheld, or failed source produces an honest empty/error state, never substitute candidates;
- parser and provider fixtures may exist only under test paths and cannot be imported by runtime modules.

Approve source decisions `SRC-TCAD-TNR-REFERENCE-ACQUIRE-20260813-V1` and `SRC-TCAD-TNR-BOUNDED-DISPLAY-20260813-V1` for this exact scope:

- official Travis County TNR ArcGIS service only;
- fixed `DEL VALLE` and `MANOR` cohort and reviewed non-owner/contact field allowlist;
- paced, bounded queries and private content-addressed raw retention;
- attributed public reference display of parcel/site identifiers, acreage, geometry-derived location, and assessor observations;
- the visible limitation that boundaries are approximate and values are source observations, not a legal boundary, appraisal, underwriting conclusion, or offer;
- Opportunity Zone status remains unverified until a versioned federal spatial join completes.

Export, bulk redistribution, owner/contact collection, outreach, valuation/offer claims, and automatic geographic or field expansion are not approved. Each requires a separate source and product decision.

## Consequences

The platform can be empty when live data or its display gate is unavailable. That is an intentional integrity property. UI testing uses constructed test inputs rather than a deployed demo dataset. Adding a new county requires a new adapter, rights record, region pack, and activation rather than changing runtime mode.

The approval must be re-reviewed if the endpoint, ItemInfo, field allowlist, intended use, attribution, or provider terms change.
