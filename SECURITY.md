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
