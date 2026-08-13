# ADR 0002: Immutable source artifacts and observations

- Status: accepted
- Date: 2026-08-12

## Context

Government, licensed, and local sources change schemas, correct records, disagree with one another, and publish on different schedules. Parser and resolution logic will also improve. Overwriting the only copy of a source result would make errors irrecoverable and historical rankings impossible to reproduce.

## Decision

Store fetched source bytes/documents in immutable object storage before parsing. Record checksums, retrieval/effective times, adapter/parser/config versions, rights metadata, and artifact URI.

Parsers emit append-only observations. A resolved fact selects or derives a current value while retaining links to every supporting/conflicting observation and the policy used. Reprocessing creates new derived versions; it never changes the raw artifact.

Important records use effective time and transaction/knowledge time.

## Consequences

### Positive

- Parsers, matching, enrichment, and scores can be replayed.
- Conflicts and source corrections remain visible.
- Historical ranking and discovery-latency analysis are possible.
- Data-quality incidents can be isolated and repaired from source artifacts.

### Negative

- Storage grows continuously and needs lifecycle/rights controls.
- Current-state queries require resolved facts/read models.
- Deletion/retention obligations need tombstone/redaction workflows without corrupting lineage.

## Invariants

- A successful fetch has a content hash and immutable artifact reference.
- Raw records and observations are never updated in place for a new source value.
- Every resolved fact and score input has lineage.
- Replay is idempotent for the same artifact and version set.
