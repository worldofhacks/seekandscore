# Open decisions

This log prevents unresolved business and source choices from becoming accidental engineering assumptions. Record a decision in an ADR when it changes architecture; close the item here with the decision date and evidence.

## Blocking before production data ingestion

| ID | Decision | Why it matters | Default until decided |
|---|---|---|---|
| D-001 | Active listing and sold-comparable provider/budget | Determines lawful access, refresh, fields, derived/display rights, and valuation quality | Manual CSV/import fixtures only |
| D-002 | Approved assessor/parcel access path for each launch county | Bulk/API/export availability is the first pipeline dependency | No automated adapter without rights record |
| D-003 | Court/recorder/trustee automation level | Access controls, document rights, CAPTCHA, costs, and reliability differ | Manual evidence import in MVP |
| D-004 | Map tile/geocoding provider | Pricing, attribution, cache/derived-data rights, and address accuracy | Provider abstraction; no production token |
| D-005 | Object storage provider and off-platform backup destination | Raw immutability, egress, lifecycle, and provider DR | S3-compatible interface only |
| D-006 | Authentication provider | Session/security model and Railway preview setup | One-organization OIDC/session abstraction |
| D-007 | Alert channels | Delivery implementation and legal/user-consent requirements | In-app plus log-only staging |
| D-008 | Initial RPO/RTO and single-node PostGIS acceptance | Determines backup frequency and managed HA timing | Proposed MVP RPO 24h/RTO 4h; not yet accepted |
| D-009 | Public repository license | Public visibility is not an open-source license; data rights are separate | No license selected |

## Blocking before score-v1 signoff

| ID | Decision | Required input |
|---|---|---|
| D-010 | Target acquisition budget bands and financing assumptions | available capital, debt terms, carrying-cost model |
| D-011 | Required return/margin by strategy | hold period, risk tolerance, target return |
| D-012 | Minimum Top-25 evidence per strategy | which access/zoning/value/ownership unknowns are disqualifying |
| D-013 | Positive component definitions and normalization | reviewed benchmark examples |
| D-014 | Risk caps and fatal-risk rules | title/access/flood/zoning/utility due-diligence policy |
| D-015 | Confidence thresholds and automatic/manual match levels | parcel/entity gold-set results |
| D-016 | Composition preferences for Top 25 | desired strategy diversity without hard quotas |
| D-017 | Material-event thresholds | price change, value shift, distress and zoning events |

## Blocking before owner outreach or deals

| ID | Decision | Why it matters |
|---|---|---|
| D-018 | Allowed contact-data providers and uses | privacy, terms, outreach law, audit |
| D-019 | Allowed communication channels and opt-out process | compliance and user trust |
| D-020 | Deal approval/authority model | prevent automated external actions |
| D-021 | Contact and deal-data retention | privacy and operational history |
| D-026 | Responsible-party roles and minimum authority evidence | avoid treating a router, broker, manager, or similarly named person as an authorized seller |
| D-027 | Campaign/jurisdiction legal-review owner, expiry, frequency limits, and escalation rules | safe production activation and change monitoring |
| D-028 | Email, calendar, and secure-upload providers | delivery, data location, webhook security, retention, cost, and portability |
| D-029 | Restricted-document classification and request packages | least collection, access, malware scan, retention, and due-diligence workflow |

## Expansion choices

| ID | Decision | Selection criteria |
|---|---|---|
| D-022 | First non-Texas market | dissimilar disclosure/foreclosure/data model, active OZ relevance, sufficient legal data access |
| D-023 | Managed HA PostGIS provider/timing | availability objective, volume, connection/replica needs, cost |
| D-024 | Vendor versus local adapters for national parcels/deeds/zoning | coverage, rights, price, freshness, identifiers, quality |
| D-025 | Single-user product versus collaborative/multi-tenant SaaS | authorization, audit, billing, isolation, support scope |

## Decisions already made

| ID | Decision | Rationale |
|---|---|---|
| A-001 | Modular monolith with separate API/worker/web processes | fastest coherent MVP with later extraction seams |
| A-002 | PostgreSQL + PostGIS is the canonical source of truth | spatial joins and transactional provenance/ranking |
| A-003 | Immutable raw artifacts and replay | parser evolution, auditability, source-history value |
| A-004 | Deterministic versioned scoring before ML | explainability and insufficient outcome labels |
| A-005 | Opportunity Zone cohorts/statuses are temporal | 2018/2027 overlap and provisional nomination lifecycle |
| A-006 | Region packs/adapters contain local behavior | prevent county-specific forks/core conditionals |
| A-007 | Railway hosts the MVP application plane | requested target, suitable service/worker primitives |
| A-008 | Single-node Railway PostGIS is MVP-only with explicit HA gate | Railway native HA does not cover community PostGIS image |
| A-009 | Acquisition outreach is a separate policy-gated engagement context | isolate sensitive contact/consent/suppression data and require human approval before provider handoff |
| A-010 | Every application environment is live-only and fails to an empty/error state | deployed fixtures or automatic substitute records can be mistaken for actionable leads |
| A-011 | Travis TNR/TCAD is approved only for bounded, attributed reference display of reviewed non-owner fields | exact service metadata supports informational use; export, redistribution, contact use, broadening, and valuation claims remain outside scope |
| A-012 | Database owner credentials live only on an isolated one-shot migration service | API/acquisition roles are audited least-privilege contracts, and research history is database-derived; see ADR 0007 |
