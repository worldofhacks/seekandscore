# ADR 0003: Region packs and versioned policy/geography

- Status: accepted
- Date: 2026-08-12

## Context

Parcel identifiers, public-record access, foreclosure processes, zoning semantics, source cadence, and data rights vary across U.S. jurisdictions. Opportunity Zone designations also use different Census vintages and overlapping effective cohorts.

A Texas-specific core would become a national rewrite. A generic “is OZ” field would be legally and temporally wrong.

## Decision

Keep core identity, observation, enrichment, scoring, and deal workflows geography-neutral.

Local behavior is supplied through:

- versioned region packs declaring jurisdictions, capabilities, sources, schedules, mappings, reference points, approved score overrides, and compliance notes;
- source adapters implementing stable acquisition/parse contracts;
- versioned geography layers with FIPS/GEOID, boundary vintage, source, checksum, and effective interval;
- versioned federal/state/local policy records.

Opportunity Zone facts include designation round, Census vintage, tract GEOID, lifecycle status, authority, effective interval, rural flag, and membership-calculation version. Eligible/nominated is never promoted to effective without authoritative evidence.

## Consequences

### Positive

- New markets extend adapters/configuration rather than fork the application.
- Historical calculations remain reproducible after policy/geography changes.
- The UI can communicate provisional, effective, expired, overlapping, and uncertain status correctly.

### Negative

- Region pack schema and conformance tests add up-front work.
- Some local features will expose missing capabilities rather than uniform coverage.
- Over-generalization remains a risk until a dissimilar second market is implemented.

## Validation

The first non-Texas market is an architecture acceptance test. It must use the existing core without state/county conditionals; genuine new general capabilities require their own ADR and cross-region tests.
