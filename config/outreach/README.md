# Outreach policy packs

These files are versioned product controls, not legal opinions. A policy evaluates a proposed communication and returns `allowed`, `review_required`, or `blocked` with stable reasons, input hash, policy versions, time, and expiry.

Composition is restrictive:

```text
federal review baseline
  -> participant/sender/property state or territory overlays
    -> local overlay when applicable
      -> organization and source restrictions
        -> campaign purpose, channel, permission, and suppression
```

Any applicable block wins. Unknown jurisdiction, scope, source permission, party authority, consent/permission, template, or legal-review state must block or require review; it never falls through to a permissive default. Property location alone is insufficient to select policy.

Every pack declares:

- stable ID, schema/version, effective interval, and lifecycle status;
- jurisdiction and purposes/channels in scope;
- official authority references and the date reviewed;
- legal reviewer/decision reference and review expiry;
- required party/contact/source evidence and disclosures;
- local-time, frequency, suppression, consent/permission, and escalation rules;
- permitted transitions and stable reason codes;
- fixtures covering allowed, blocked, ambiguous, revoked, stale, and cross-jurisdiction cases.

No pack in this planning repository is approved for production. Enabling a state requires counsel-reviewed campaign facts, a source policy, abuse/privacy tests, and an activation record. Credentials and real contact data never belong here.
