# Source inventory

This is the Phase 0 control document, not permission to automate any source. A source moves to `approved` only after its access mechanism, terms, retention/display/export rights, identifiers, cadence, sample fixture, and operational owner are recorded.

## Status vocabulary

- `discovery`: source identified; no access/rights conclusion
- `sampled`: representative artifact obtained and stored safely
- `rights_review`: access/retention/display/redistribution under review
- `approved`: adapter/manual process may be implemented for the declared use
- `shadow`: running without user-facing ranking/alerts
- `active`: approved for production facts/rankings
- `suspended`: disabled because of terms, quality, schema, auth, or operational concern
- `blocked`: missing decision, credential, contract, or supported access mechanism

## Central Texas launch inventory

| Jurisdiction | Capability | Candidate authority/source | MVP mechanism | Status | Primary unknown |
|---|---|---|---|---|---|
| Travis | assessor/parcel | Travis County TNR monthly TCAD ArcGIS layer | bounded paginated query | approved | Reference display only; export, redistribution, and owner/contact use prohibited by project policy |
| Bastrop | assessor/parcel | Bastrop CAD official certified/GIS ZIPs | official bulk download after disclaimer | rights_review | disclaimer scope, retention/display/export rights |
| Caldwell | assessor/parcel | Caldwell CAD annual public exports | official bulk download | rights_review | retention/display/export rights, geometry |
| Travis | tax delinquency/foreclosure | Travis County Tax Office daily CSV and sale pages | official bulk file; sale page later | rights_review | retention/display rights, event withdrawal/history |
| Bastrop | tax delinquency/foreclosure | county tax authority/sale authority | to determine | discovery | authority and publication method |
| Caldwell | tax delinquency/foreclosure | county tax authority/sale authority | to determine | discovery | authority and publication method |
| Travis | civil tax/real-estate cases | District Clerk | manual flag/import first | discovery | automation terms/access/document rights |
| launch counties | trustee/non-tax foreclosure | County Clerk/public notices | manual-assisted first | discovery | indexing, document rights, matching |
| launch counties | deeds/ownership | County Clerk/recorder | later phase | discovery | access cost and owner-history fields |
| launch counties | property-party authority | recorder, entity registry, court/probate, signed authorization, listing/agency source | manual verification first | discovery | role semantics, currency, authority scope, permitted use |
| launch counties | owner/representative contact points | approved provider and official/party-confirmed sources | manual entry/import only until approved | blocked | provider, terms, purpose, contact match, retention, jurisdiction/channel policy |
| launch counties | active listings | licensed feed/provider | manual import until selected | blocked | provider, contract, price, display rights |
| launch counties | sold comparables | licensed/public sources | manual/approved provider | blocked | Texas nondisclosure and licensing |
| federal/local | parcel geometry | CAD/county/local GIS | official download/service | discovery | authority, vintage, completeness |
| federal | flood | FEMA NFHL/Map Service Center | official bulk download/service | discovery | effective-layer update process and version tests |
| federal | Opportunity Zones | IRS/Treasury/CDFI + vintage-correct Census geometry | official files | discovery | 2010 join implementation and 2027 final publication lifecycle |
| local | zoning/city/ETJ | municipal/county GIS/planning | later/where authoritative | discovery | semantics, completeness, updates |
| local/state/federal | wildfire/wetlands/elevation | official agencies | later phase | discovery | layer selection and screening limits |
| local | roads/access/utilities | transport/local utility/planning | evidence signals only | discovery | legal-access versus physical-road distinction |

## Required source record

Exact researched endpoints and the first bounded operational contract are maintained in [`LIVE_INGESTION_RUNBOOK.md`](LIVE_INGESTION_RUNBOOK.md) and `config/ingestion/us-tx-central-texas-v1.yaml`.

Create one source-policy record containing:

```text
source name and authority
jurisdictions/capabilities
official URLs and support contact
access mechanism and authentication
terms/license URLs and accepted-at timestamp
retention, display, export and redistribution flags
required attribution
personal/restricted data classification
upstream identifiers and geographic vintage
publication and expected refresh cadence
rate/concurrency limits
sample artifact checksum/object URI
adapter/parser/config versions
source owner and incident path
kill switch and replay procedure
contact-point/property-party purpose and authority scope, when applicable
outreach eligibility, consent/permission requirements, and suppression handling, when applicable
```

## Adapter readiness checklist

- [ ] Official/supported access mechanism selected
- [ ] Terms and data rights reviewed for the exact use
- [ ] Representative artifacts cover normal and edge cases
- [ ] Stable upstream record identity established
- [ ] Geographic/identifier vintage recorded
- [ ] Parser runs offline and deterministically
- [ ] Three-run idempotency passes
- [ ] Schema drift quarantines instead of corrupting facts
- [ ] Rate limiting, retries, and last-good cursor tested
- [ ] Freshness SLA and health metrics configured
- [ ] Fixtures contain no credentials or unnecessary personal/licensed data
- [ ] Shadow output reviewed against source
- [ ] Production activation approved
- [ ] Contact or outreach use separately approved when the capability includes personal/contact data

The Travis TNR/TCAD record completed the access, exact ItemInfo, schema, bounded-query, immutable-storage, replay, attribution, and display-scope checks on August 13, 2026. Its approval is not transferable to TCAD's separate PDF map-download page, owner/contact fields, exports, bulk redistribution, or outreach.
