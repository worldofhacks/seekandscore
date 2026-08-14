# Region packs

Region packs describe local capabilities and configuration without putting county/state conditionals in core application code.

Each version should declare:

- stable jurisdiction identifiers and time zones;
- source instances, capability, rollout status, schedule, and source-policy reference;
- local property/use mappings;
- authoritative GIS layers and boundary vintages;
- named corridors/reference points;
- approved scoring-profile reference/overrides;
- outreach policy reference, rollout mode, and intentionally enabled purposes/channels;
- compliance/access notes;
- activation state (`development`, `shadow`, `review`, `active`, `suspended`).

Credentials never belong in region packs. Use secret-variable references resolved by the runtime.

The Central Texas pack records the first approved bounded reference-display source. Approval is scoped: the Travis TNR/TCAD adapter may collect and display its reviewed non-owner field allowlist with attribution and screening limitations, but may not export, redistribute, or use the feed for contact discovery. Environment activation and the ingestion kill switch remain independent controls.

Property location is only one outreach-policy input. Participant, sender, organization, contact-source, and campaign jurisdictions may also matter. A region pack may reference a reviewed policy but cannot declare a channel legal or bypass a stricter suppression/source/organization rule.
