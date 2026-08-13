# Security policy

This repository does not yet contain a deployed application. Security reports should not include real property-owner contact data, source-provider credentials, or tokens in public issues.

When GitHub private vulnerability reporting is enabled, use the repository's **Security → Report a vulnerability** flow. Until then, repository maintainers should establish a private reporting address before the first public deployment.

## Baseline requirements for launch

- Least-privilege, environment-specific service credentials
- Sealed production secrets and no secrets in Git, logs, fixtures, or browser bundles
- Authentication and authorization on every non-health application route
- Audit events for exports, contact-data access, deal-state changes, and administrative actions
- Dependency, container, and secret scanning in CI
- Encryption in transit and at rest where supported
- Documented incident response, backup restoration, credential rotation, and data-deletion procedures
- Source-specific handling rules for personal information and restricted records
- Encrypted, masked contact values with separately keyed HMAC lookup; never plain contact values or unsalted hashes in indexes, events, analytics, or logs
- Central suppression/permission enforcement at approval, queue, and provider handoff, including race and restore tests
- Exact-content human approval and fail-closed environment/channel kill switches for acquisition communication
- Signed, replay-protected, idempotent provider webhooks with isolated credentials and retained reconciliation evidence
- Short-lived signed upload links, malware scanning, authorization, access audit, classification, and retention for requested documents

## Outreach and fixture handling

Real contact values, message bodies, opt-out identifiers, provider payloads, calendar attendee data, and submitted due-diligence documents are restricted. They must not enter public issues, pull requests, fixtures, screenshots, browser telemetry, AI prompts, logs, or traces. Public tests use synthetic parties and provider events. A production incident or data-subject request must preserve only the minimum approved suppression tombstone needed to prevent accidental re-contact.
