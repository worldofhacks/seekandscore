# ADR 0005: Policy-gated, human-approved acquisition outreach

- Status: accepted as architecture; channel activation remains gated
- Date: 2026-08-12

## Context

Acquisition work requires more than storing a phone number and an attempt. The platform must distinguish the property owner from managers, brokers, registered agents, trustees, attorneys, public officers, and unrelated people; preserve contact-data provenance and permitted use; honor suppressions; coordinate appointments; and request sensitive documents safely.

Mixing these responsibilities into deal notes or user-alert delivery would weaken authorization, audit, and future jurisdiction/provider isolation. Autonomous outreach would also create unacceptable identity, consent, privacy, discrimination, and regulatory risk.

## Decision

Create an `engagement` bounded context and PostgreSQL schema for contact points, permissions, suppressions, outreach cases, policy decisions, communications, appointments, information requests, and outcomes.

`identity` remains authoritative for entities and source-supported property-party roles. `deal` owns acquisition status, offers, and operator next actions. `delivery` owns alerts sent to Seek and Score users. These contexts exchange stable IDs and domain events rather than writing each other's tables.

All first contact is case-based, individually reviewed, and explicitly approved by a human. A fresh policy preflight is required immediately before any provider send. SMS, automated dialing, prerecorded/artificial voice, bulk campaigns, and unattended sequences are disabled. Environment and channel kill switches default off.

Appointment coordination and information requests become explicit aggregates. A scheduling label does not convert cold outreach into a transactional message. Contact response behavior may change workflow state but does not automatically affect opportunity ranking.

## Consequences

### Positive

- Contact sensitivity, suppressions, consent/permission, and audit have one owner.
- New providers and states can be added through adapters and versioned policy packs.
- Wrong-party corrections and opt-outs stop work across related cases.
- Scheduling and document exchange remain traceable instead of disappearing into notes.
- The app can begin as a manual system of record and enable narrow sends later without redesigning its model.

### Negative

- More states and records than a minimal CRM.
- Source-rights and legal review can block channel activation after the UI exists.
- Provider callbacks, suppressions, secure uploads, and calendars require ongoing operations and incident handling.
- The policy engine must be maintained and tested but still cannot replace legal judgment.

## Activation gate

No production channel is enabled until its campaign purpose, jurisdictions, contact sources, templates, policies, retention, security controls, abuse tests, and responsible legal reviewer are recorded. Each additional automated channel requires a new ADR rather than a configuration-only change.
