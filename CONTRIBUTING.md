# Contributing

Seek and Score is currently planning-first. Contributions should strengthen an accepted milestone rather than widen the product surface.

## Before implementation

1. Read the [implementation plan](docs/IMPLEMENTATION_PLAN.md) and relevant ADRs.
2. Link work to an issue with explicit acceptance criteria.
3. For a new data source, document its authority, access method, terms, cadence, identifiers, retention/display rights, and failure behavior before writing an adapter.
4. For a new market, extend a region pack and adapter; do not add location checks to core domain code.
5. For a scoring change, create a new score-model version and regression fixture. Never rewrite historical scores in place.
6. For outreach, contact enrichment, templates, channels, calendars, or uploads, link the source-policy and legal/security review. New environments/channels remain disabled until their activation evidence and negative tests pass.

## Expected quality gates

- Formatting, linting, static analysis, unit tests, and migration checks pass.
- Ingestion is idempotent and replayable from an immutable fixture.
- Domain calculations are deterministic and use fixed units/rounding.
- New canonical facts retain field-level provenance.
- Geospatial changes include known-boundary fixtures.
- API changes update OpenAPI and generated client checks.
- User-visible estimates distinguish verified, estimated, preliminary, stale, and unknown values.
- Logs do not contain source credentials or unnecessary owner/contact data.
- Outreach fixtures contain only synthetic parties, masked endpoints, synthetic message bodies, and fake signed-webhook events.
- A recipient/content/policy change invalidates approval; a late suppression blocks provider handoff; webhook replays remain idempotent.

## Branches and commits

Use a short topic branch and focused commits. Pull requests should explain the user outcome, data or schema changes, operational risk, test evidence, and rollback plan.

## Security and data-access reports

Do not open a public issue containing credentials, private owner/contact data, or a reproducible vulnerability. Use the repository's private security-advisory flow once it is enabled.
