# Product definition

## Product statement

Seek and Score is an operator-focused real-estate intelligence system. It continuously turns fragmented property, ownership, distress, market, and geospatial records into a small, explainable queue of opportunities and next actions.

It is not a listing portal and should not optimize for inventory volume or consumer browsing. Its value is prioritization: reduce thousands of parcels and changing records to the few decisions that deserve attention now.

## Primary user

The launch user is a single investor/operator who researches, contacts, underwrites, and potentially acquires properties. The system should minimize manual source-checking without hiding uncertainty or due-diligence obligations.

Future roles are deliberately anticipated but not required for MVP:

- Principal/investor: rankings, decisions, capital limits, approvals
- Analyst: research queue, source verification, comps, underwriting
- Acquisitions operator: owner/contact workflow, offers, follow-ups
- Administrator: adapters, data health, score models, access controls

The initial authorization model can be one organization with one administrator. Database rows should still carry `organization_id` where doing so avoids an expensive future tenancy migration, but multi-tenant billing and self-service onboarding are out of scope.

## North-star screen

The home screen must answer, in roughly five minutes:

- What are the 25 best opportunities now?
- What changed since the last review?
- Why is each opportunity ranked here?
- What evidence is verified, stale, estimated, conflicting, or unknown?
- What are the three biggest risks?
- What is the value range and acquisition-cost scenario?
- What is the next action?

A property detail view should communicate the core decision in about ten seconds, then allow progressively deeper inspection of financials, distress, development, GIS, ownership, sources, and history.

## Launch investment strategies

### Buildable and lifestyle land

Target acreage with legal/physical access, usable geometry, manageable hazards, utility/septic signals, privacy or lifestyle appeal, and future development optionality. Buildability and lifestyle are independent scores; neither may conceal access, flood, title, or utility uncertainty.

### Airport parking and commercial land bank

Screen approximately 1–10 acre parcels in the AUS/FM 973/SH-71/US-183/Old Bastrop Highway corridor for access, usable acreage, land basis, preliminary parking capacity, land cost per potential space, current-use feasibility, and longer-term commercial optionality.

All parking capacity and revenue outputs are scenario estimates marked **preliminary — civil, access, drainage, zoning, and operating verification required**.

### Event parking and redevelopment

Screen underutilized North Austin/Q2/Domain-area parcels for interim-use potential and redevelopment. This strategy must distinguish current legal use, potential use, and speculative future entitlement.

### Distressed and off-market acquisition

Detect tax delinquency, tax foreclosure, trustee-sale notices, long holds, absentee ownership, under-improvement, withdrawn/stale listings, and related distressed parcels. Use only supported public/licensed evidence and do not infer sensitive personal circumstances.

### Land banking

Rank parcels with strong basis, access, growth catalysts, holding-cost tolerance, liquidity, and multiple plausible exits. A growth narrative is not a substitute for a conservative current-use valuation.

### Auction

Present auction date, minimum bid, likely acquisition-cost range, redemption/title warnings, conservative value, risk buffer, and maximum recommended bid. Minimum bid must never be displayed as likely cost or guaranteed equity.

### Opportunity Zone development

Treat Opportunity Zone status as a policy-aware investment lens, not a magic score bonus. The system should identify parcels in or overlapping an effective designation, estimate development/substantial-improvement suitability, and model tax scenarios separately from property economics.

An eligible or state-nominated 2027 tract is a research signal until Treasury certification and the effective date. Parcel location alone never establishes that a taxpayer, fund, business, property, or project qualifies.

## Core user workflows

### Daily review

1. Open the daily brief.
2. Review new strong candidates, Top-25 movements, critical source changes, and stale-source warnings.
3. Inspect ranking explanations and evidence.
4. Watch, pass, or move a candidate into research.
5. Accept or replace the proposed next action.

### Property research

1. Start from ranking, feed, map, owner portfolio, or auction.
2. Review the concise thesis, value range, likely basis, risk flags, and confidence.
3. Drill into source observations and conflicts.
4. Resolve unknowns through research tasks.
5. Record notes, documents, comps, site visits, and decisions.

### Off-market acquisition

1. Identify a supported motivation/distress signal.
2. Resolve the record owner or source-supported manager/representative, role, authority scope, and related parcel portfolio with match confidence.
3. Verify the contact point, its source, permitted use, freshness, channel permission, and suppression state.
4. Declare a narrow outreach purpose and pass the versioned jurisdiction/source/channel policy preflight.
5. Human-review and individually approve the exact initial communication or record a manual attempt.
6. Classify the response, wrong-party report, opt-out, representation, delivery failure, or next action.
7. With affirmative participation, coordinate a meeting/site visit or issue a structured, secure information request.
8. Create opening, target, and walk-away price scenarios.
9. Advance the deal through due diligence, offer, negotiation, contract, close, pass, or loss.

See [Owner and representative outreach](OUTREACH_WORKFLOW.md) for the detailed workflow and activation gates.

### Auction

1. Import and resolve the auction inventory.
2. Reject unresolved or ineligible parcels to the research queue.
3. Review title/redemption/access/tax warnings.
4. Create conservative value and maximum-bid scenarios.
5. Complete registration and due-diligence checklist.
6. Record bidding and outcome for future calibration.

### New-region onboarding

1. Register country/state/county identifiers and boundary vintages.
2. Complete a source inventory and rights review.
3. Create a region pack with sources, cadence, capabilities, reference points, score overrides, and compliance notes.
4. Implement adapters against shared contracts.
5. Build a manually verified parcel-resolution and ranking benchmark.
6. Run in shadow mode before enabling alerts or Top-25 eligibility.

## Core product capabilities

- Canonical parcels and multi-parcel investment candidates
- Immutable raw source records and documents
- Field-level observations, resolved facts, conflicts, lineage, freshness, and confidence
- Parcel and owner/entity resolution with manual review and reversible decisions
- Spatial enrichment using versioned layers
- Active/off-market/auction valuation scenarios and comparable selection
- Deterministic signals, risk flags, and independent strategy underwriting
- Versioned overall and strategy rankings with stable movement explanations
- Top 25, map, filters, research queue, new-opportunity feed, and daily brief
- Watchlist, notes, tasks, status pipeline, owner portfolio, and CRM-lite workflow
- Responsible-party and authority resolution with contact-point provenance and reversible review
- Policy-gated, human-approved outreach cases, suppression, replies, scheduling, and secure information requests
- Source/data-health dashboard and freshness alerts
- Outcome capture for later calibration and prediction
- Optional AI summaries constrained to cited source evidence

## Explicit non-goals for MVP

- Consumer marketplace or Zillow replacement
- Nationwide simultaneous launch
- Automated purchase, bidding, owner contact, or offer sending
- Bulk campaigns, automated dialing, prerecorded/artificial voice, unattended sequences, or SMS without separately approved policy and permission controls
- Legal, title, tax, appraisal, engineering, environmental, or zoning conclusions
- A general-purpose CRM
- Opaque machine-learning ranking
- Millisecond “real time” claims for sources that publish daily or monthly
- Scraping a source merely because its records are publicly viewable
- Redis, search, or an LLM as a source of truth

## Success measures

### Product outcomes

- Qualified opportunities discovered per week
- Percentage of Top-25 candidates researched and contacted
- Offers submitted and off-market responses
- Acquisitions and discount to independently verified market value
- Actual versus predicted acquisition cost and return
- Time from material source event to actionable review

### Data outcomes

- Source success and freshness by jurisdiction
- Parcel-resolution precision/recall on a reviewed gold set
- Percentage of canonical fields backed by provenance
- Research-queue age and unresolved-record rate
- Duplicate parcel/event/alert rate after replay
- Estimate calibration and confidence coverage

### User outcome

After five minutes, the operator should have a materially better research and acquisition queue than they could obtain by independently checking listings, assessor data, tax records, foreclosure notices, and maps.

## Product guardrails

- Every Top-25 candidate passes minimum parcel, location, ownership, and value-data gates.
- Risks are structured and prominent, not buried in prose.
- Unknown and conflicting values remain visible.
- Opportunity Zone tax scenarios never inflate the base property value estimate.
- No outreach occurs without a human action and an allowed contact-data source.
- No contact point is eligible without a reviewed property-party role; a vendor match alone is insufficient.
- Opt-out, wrong-party, disputed-identity, and permission-revocation events stop pending work and invalidate unused approvals.
- Outreach response behavior may change deal workflow but never automatically changes opportunity ranking.
- Every score, estimate, and rank movement is reproducible from versioned inputs.
- AI text cites internal evidence and is clearly secondary to structured facts.
